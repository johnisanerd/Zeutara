# Production API Integration Plan

This document specifies how the three live data sources (PredictLeads,
Crunchbase, Apify) are wired into the engine when moving beyond the
bundled-fixture demo path.

The integration code is intentionally **not** wired in the prototype
because:
1. The brief specifies under 15 minutes from clone to first output for
   the reviewer. Signing up for three API providers and seeding API keys
   blows that budget.
2. The brief specifies one component, runnable, with a clear list of what
   comes next. Wiring three APIs end-to-end is beyond the scope of "one
   component."
3. Defending vendor choices with cost data is the more important signal
   for the assessment; the live integration is mechanical from there.

---

## Three sources, three roles

Each source covers a distinct signal category. There is intentional
overlap on funding events between PredictLeads and Crunchbase because
funding is the highest-signal trigger and redundancy reduces single-vendor
risk.

| Source | Role | Annual cost at expected volume | Replacement risk |
|---|---|---|---|
| **PredictLeads** | Job openings, news events (financing, layoffs, leadership change, pivot), employee count over time | $13K-43K/yr per Vendr (avg $28K, 1 verified purchase); single-dataset access from ~$6K/yr | Medium. Closest substitute is Ocean.io but signal coverage is narrower. |
| **Crunchbase Pro** | Funding rounds, total raised, stage classification, founders | $588/yr ($49/mo annual) Pro tier; $2,388/yr Business tier with 5K row exports/mo | Low. PitchBook is the obvious substitute but at ~$30K/user/yr (Vendr median) for use cases Zeutara does not need. |
| **Apify** | LinkedIn scraping (company headcount, founder posts, employee changes), Glassdoor reviews, news scraping | $199/mo Scale tier; ~$0.20/compute-unit (typical 5K-company pass: $50-100/mo) | Medium. Bright Data is the alternative ($8/GB residential; $1.50-2.50 per 1K Web Scraper API requests). |

**Total monthly run cost at Zeutara's expected volume of 5,000-10,000
tracked prospects**: $850-2,500/month including the AI personalization
layer (Claude Sonnet 4.6 inference at ~$50-200/mo).

---

## PredictLeads integration

### What it provides
- **Job Openings dataset**: per-domain list of open roles with title, posted
  date, location, and (critically) days-open. This powers `open_senior_role_stale`,
  `multiple_senior_roles_open`, and `hiring_stalled_post_raise`.
- **News Events dataset**: 29 categorized events including financing,
  acquisition, layoff, leadership change, partnership, product launch,
  market expansion, lawsuit. Powers `recent_layoff_event`, `board_or_lead_investor_change`,
  `strategic_announcement_event`.
- **Financing dataset**: backup source for funding events; cross-validates
  Crunchbase.

### Endpoint pattern
```
GET https://predictleads.com/api/v3/companies/{domain}/job_openings
GET https://predictleads.com/api/v3/companies/{domain}/news_events
GET https://predictleads.com/api/v3/companies/{domain}/financing_events

Headers:
  X-Api-Key: <key>
  X-Api-Token: <token>
```

### Wiring in the engine
The function `fetch_from_predictleads(domain)` in `src/data_loaders.py`
is the integration point. The skeleton is in place; production version
makes the three GET requests in parallel and assembles the response
dict that maps directly into `Prospect.raw_context`.

Rate limits: 100 free API calls/month on the free tier (sufficient for
testing); paid tiers have generous request budgets at the $6K+/yr level.

### Failure mode
If PredictLeads is unavailable or rate-limited, fall back to Apify
scrapers for LinkedIn job pages and Crunchbase News RSS for financing
events. Quality degrades but the pipeline still runs.

---

## Crunchbase integration

### What it provides
- Funding round history per company (date, type, amount, lead investor)
- Total raised, stage classification
- Founder names and LinkedIn URLs
- Industry tagging

This is the primary source for the `last_round_date`, `last_round_type`,
`last_round_amount_usd`, `total_raised_usd`, and `stage` fields of `Prospect`.

### Endpoint pattern
Crunchbase Pro tier ($49/mo annual) provides limited API access; the
Business tier ($199/mo annual) raises export limits to 5K rows/month and
enables more programmatic use. For >50K records/month, the Enterprise
API kicks in at $50K+/yr (Vendr median), which Zeutara does not need at
the prototype-validation stage.

```
GET https://api.crunchbase.com/api/v4/searches/organizations
  Body: {
    "query": [{"type": "predicate", "field_id": "stage", "operator_id": "in",
               "values": ["seed", "series_a"]}],
    "field_ids": ["uuid", "name", "founded_on", "funding_total",
                  "last_funding_at", "last_funding_type", "num_employees_enum",
                  "headquarters_regions"]
  }
  Headers:
    X-cb-user-key: <key>
```

### Wiring in the engine
The function `fetch_from_crunchbase(domain)` in `src/data_loaders.py`.
Production version uses the search endpoint to enumerate the universe,
then per-company GET for funding round details. Results map directly to
`Prospect` fields.

### Rate limit handling
Pro tier: 200 calls/day. Business tier: significantly higher (exact
number gated behind contract). For Zeutara's 5,000-10,000 prospect
universe refreshed weekly, the Business tier is appropriate.

---

## Apify integration

### What it provides
Apify is a marketplace of pre-built scrapers ("actors") that handle the
operationally annoying parts of LinkedIn data extraction:

| Actor | Purpose | Approximate cost per 1K records |
|---|---|---|
| `apify/linkedin-company-scraper` | Company page: headcount over time, location, industry | $1-3 |
| `apify/linkedin-profile-scraper` | Individual profile: experience history, current role | $2-5 |
| `apify/linkedin-posts-scraper` | Profile posts with date and text | $3-8 |
| `johnvc/glassdoor-reviews-api` | Company reviews for qualitative signals (`companyUrls` in; `overallRating`, `pros`, `cons` out) | $4 |

### Endpoint pattern
```
POST https://api.apify.com/v2/acts/{actor_id}/run-sync
  Headers:
    Authorization: Bearer <token>
  Body:
    { "startUrls": [{"url": "..."}], "maxItems": 50 }
```

### Wiring in the engine
The function `fetch_linkedin_signals_via_apify(domain, founder_urls)` in
`src/data_loaders.py`. Production version calls four actors in parallel
and assembles results into the `raw_context` fields:
- `recent_founder_posts` from `linkedin-posts-scraper` on each founder URL
- `executive_departures` and `sales_leader_churn` derived from
  `linkedin-profile-scraper` runs on key roles
- Headcount-over-time from `linkedin-company-scraper`

### Compliance and risk
LinkedIn data scraping is a contested space. Apify actors are operated
by third parties and their compliance posture varies. The two relevant
constraints:

1. **LinkedIn ToS**: scraping employee data violates LinkedIn's Terms of
   Service. Public scraping of public profile data has favorable legal
   precedent (hiQ Labs v. LinkedIn, 9th Cir., 2022) but is not without
   risk.
2. **GDPR**: personal data of EU residents requires a documented
   Legitimate Interest Assessment. The engine respects this by limiting
   geography to US/Canada in the default ICP.

Zeutara should review the compliance posture of each Apify actor before
production use and document the legitimate interest basis for each
data category.

---

## CRM sync (Attio)

This sits downstream of the engine and is not implemented in the prototype.
Specification:

- Output of each engine run (`output/ranked_lane_{A,B}.json`) is the input
- Each `ScoredProspect` becomes an Attio Company record plus a related
  "Signal Set" record capturing the fired signals at this point in time
- Score changes over time create a history (useful for tuning weights
  later)
- Records tagged `priority=HOT` trigger a Slack notification to the
  founding partner; `WARM` enters the standard analyst queue
- API: `POST https://api.attio.com/v2/objects/companies/records`

---

## Outreach sync (Instantly)

Also downstream of the engine and not implemented in the prototype.
Specification:

- Only `WARM` and `HOT` prospects flow to Instantly (after analyst review)
- Each prospect carries its fired-signal evidence as custom variables
  that the personalization layer (Claude Sonnet 4.6) consumes
- One sending pool per lane (separate domain reputation by ICP)
- API: `POST https://api.instantly.ai/api/v2/leads`

---

## Cost model summary at 5K-10K prospects tracked

| Component | Monthly cost | Annual cost | Notes |
|---|---|---|---|
| PredictLeads (single dataset) | $500-700 | $6K-8.4K | Job openings primary, news events bundled |
| Crunchbase Pro | $49 | $588 | Funding events |
| Apify Scale | $199 | $2,388 | LinkedIn + Glassdoor scraping |
| Claude Sonnet 4.6 API | $50-200 | $600-2.4K | Personalization + classification |
| Workflow orchestration (n8n self-hosted) | $5-20 | $60-240 | Server only |
| **Total** | **$803-1,168** | **$9.6K-13.6K** | |

Add the outbound stack (Instantly, HeyReach, Attio) and the all-in cost
is roughly $1,500-2,500/month, which is under 5% of a single $50K
retainer engagement.
