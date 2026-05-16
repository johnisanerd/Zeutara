# Zeutara Signal Detection Engine

> A prototype of the load-bearing component in Zeutara's BD pipeline:
> a signal-driven engine that ranks venture-backed companies by their
> likelihood of being "in market" for execution-architecture consulting
> *right now*.

This is the prototype deliverable for the Zeutara analyst assessment.
The architecture spec and defending paper live alongside this repo.

---

## Why this component

Zeutara's positioning is "execution architecture for founders at structural
inflection points." That pitch only works if Zeutara shows up at the moment
of strain. Every other component of the BD pipeline (enrichment, messaging,
qualification, outreach, CRM) is downstream of correctly identifying *who
is in market today*. If signal detection is wrong, the rest of the pipeline
amplifies the wrong work.

That is why the signal engine is the load-bearing component, and that is
why this is the one component built end-to-end.

The defending paper makes the full case in writing.

---

## Quick start (under 3 minutes from clone to first output)

Requirements: Python 3.10+ standard library only. Zero pip installs needed
for the demo path.

```bash
git clone <repo-url>
cd zeutara-signal-engine

# Run the engine against bundled fixture data, both lanes.
python -m src.run

# Run only Lane A (pre-seed / seed / Series A founders).
python -m src.run --lane A

# Run only Lane B (growth-stage operators).
python -m src.run --lane B

# Run the test suite.
python -m unittest discover tests
```

Outputs land in `./output/`:
- `ranked_lane_A.csv` and `ranked_lane_B.csv` for human review in Excel
- `ranked_lane_A.json` and `ranked_lane_B.json` for downstream CRM/outreach sync

---

## What you should see

Running `python -m src.run` against the 25-company bundled fixture
produces output like this:

```
========================================================================
  LANE A: 25 prospects evaluated
========================================================================
  HOT       2  (partner reviews within 24h)
  WARM      1  (analyst processes within 72h)
  COOL      3  (quarterly nurture)
  EXCLUDED 19  (off-ICP, no signals)

  Top 3 by score:
    [HOT  ]  52/100  Modal Labs
    [HOT  ]  52/100  Resend
    [WARM ]  46/100  Dust

  Sample of highest-scoring prospect's signals:
      Modal Labs (score 52, lane A):
        + 22  recent_raise_60_to_180_days
              raised Series A 94 days ago ($16,000,000)
        + 20  open_senior_role_stale
              stale senior role(s): VP of Sales (78d open), Head of Marketing (65d open)
        + 10  founder_help_seeking_content
              founder posted 12d ago (matched: fractional): ...
```

The engine evaluates each of 25 real US venture-backed companies against
the relevant lane's ICP filter, runs 7-8 signal detectors per lane, sums
weighted contributions, and routes into HOT/WARM/COOL/EXCLUDED buckets.

The output is what the analyst opens Monday morning: a ranked queue of
prospects with the specific signal evidence attached. Partner attention
goes to HOT, analyst time goes to WARM, the rest stays in nurture.

---

## What the engine does (and what it does not)

**It does:**
- Apply hard ICP filters (stage, capital raised, headcount, geography,
  blocked industries) before any scoring runs
- Score each in-ICP prospect against 7-8 signal detectors for the relevant
  lane (Lane A or Lane B)
- Output a transparent, auditable rationale for every score (analyst can
  see exactly which signals fired and why)
- Route prospects into priority buckets via configurable thresholds
- Emit both CSV and JSON, ready for sync to a CRM (Attio recommended) or
  an outreach platform (Instantly recommended)

**It does not (in this prototype):**
- Fetch live data from PredictLeads, Crunchbase, or Apify. The integration
  layer is documented in `docs/integrations.md` and the API client
  signatures are in `src/data_loaders.py`, but the network calls are not
  wired so the reviewer's 15-minute window is not consumed by signup flows
- Write to a CRM. The JSON output is structured for an Attio sync but the
  sync itself is downstream
- Generate outreach messages. That is the next component in the architecture
  and is handled by a separate module not built here

The "if I had two more days" list at the bottom of this README is honest
about what comes next.

---

## Architecture

```
                     ┌───────────────────────────────┐
                     │   data/prospects.json         │
                     │   (or live API integrations,  │
                     │    documented in docs/)       │
                     └──────────────┬────────────────┘
                                    │
                                    ▼
                     ┌───────────────────────────────┐
                     │   src/data_loaders.py         │
                     │   - load_fixture_prospects()  │
                     │   - fetch_from_predictleads() │ ← documented, not wired
                     │   - fetch_from_crunchbase()   │ ← documented, not wired
                     │   - fetch_linkedin_signals()  │ ← documented, not wired
                     └──────────────┬────────────────┘
                                    │
                                    ▼
                     ┌───────────────────────────────┐
                     │   src/scoring.py              │
                     │   1. in_icp() hard filter     │
                     │   2. run all lane detectors   │
                     │   3. sum weights, cap at 100  │
                     │   4. assign priority bucket   │
                     └──────────────┬────────────────┘
                                    │
                          ┌─────────┴──────────┐
                          ▼                    ▼
                  ┌──────────────┐    ┌──────────────────┐
                  │ src/signals  │    │  src/config      │
                  │ 15 detectors │    │  ICP definitions │
                  │ 8 Lane A,    │    │  weight tables   │
                  │ 7 Lane B     │    │  thresholds      │
                  └──────────────┘    └──────────────────┘
                                    │
                                    ▼
                     ┌───────────────────────────────┐
                     │   src/pipeline.py             │
                     │   orchestration + output      │
                     └──────────────┬────────────────┘
                                    │
                                    ▼
                     output/ranked_lane_{A,B}.{csv,json}
```

---

## What the signals are, and why

Each detector encodes a specific hypothesis about when a founder or
operator is genuinely "in market" for execution help. The two lanes have
different signals because the triggers that indicate market-readiness for
a $2M ARR founder still leading sales are different from the triggers for
a $40M ARR CEO whose VP of Sales just resigned.

### Lane A detectors (pre-seed / seed / Series A)

| Signal | Weight | Hypothesis |
|---|---|---|
| `recent_raise_60_to_180_days` | 22 | Capital deployed, internal hiring not caught up. Carta 2024 data: 40%+ of seed/Series A activity is bridge rounds, meaning thousands of funded companies are between rounds and deploying capital. |
| `open_senior_role_stale` | 20 | VP/Director role open >60 days. Median time-to-fill for senior GTM at funded Series A is 30-45 days. Stale = visible execution gap. |
| `first_sales_hire_churned` | 18 | First VP Sales departed within 6 months. Lemkin/SaaStr long-running data: ~70% of first VP Sales hires miss in year one. |
| `bridge_or_extension_round` | 14 | Bridge/SAFE/extension as most recent round = explicit signal the company has not hit metrics for the next priced round. |
| `founder_help_seeking_content` | 10 | Founder LinkedIn content (last 60d) mentioning hiring pain, fractional, advisory. Highest-intent public signal short of inbound. |
| `runway_pressure_stale_round` | 8 | >18mo since seed or >24mo since Series A with no new round. With Carta showing median seed→A wait of ~25 months, this band catches genuine runway pressure. |
| `hiring_stalled_post_raise` | 8 | <15% headcount growth in 6mo post-raise. Funded Series A typically grows 80-150% in 12mo. |

### Lane B detectors (growth-stage)

| Signal | Weight | Hypothesis |
|---|---|---|
| `c_level_departure_90d` | 25 | C-level (CRO, CFO, CMO, COO) departed in 90d. Highest-signal inflection at growth stage. |
| `recent_layoff_event` | 20 | Layoff in 90d → functional restructure typically follows. |
| `multiple_senior_roles_open` | 18 | 3+ "Head of" or "VP of" roles open simultaneously = explicit leadership rebuild. |
| `board_or_lead_investor_change` | 12 | Governance cadence shift; revenue architecture rework often follows. |
| `strategic_announcement_event` | 10 | Pivot, product line discontinuation, market expansion. |
| `stale_capital_no_traction` | 8 | >24mo since round + no recent traction news = next-raise narrative not writing itself. |
| `ceo_help_seeking_content` | 7 | CEO posting about scaling pain, org design, exec rebuild. |

---

## What is real and what is synthesized in the fixture data

The bundled `data/prospects.json` contains 25 real US venture-backed
companies (Modal, Hex, Vercel, Resend, Anyscale, Hightouch, etc.) with
their real stages and approximate funding history.

The signal-level annotations attached to each company in
`raw_context` (open senior roles, executive departures, founder posts,
news events) are **synthesized to represent the patterns the engine is
designed to catch**. They are not scraped from those companies' actual
data. This is intentional and disclosed.

The reason: the live integrations to PredictLeads, Crunchbase, and
LinkedIn-via-Apify are documented in `docs/integrations.md` with the
request schemas and cost model, but wiring them against fresh API keys
would consume the reviewer's 15-minute window. The fixture path proves
the engine works on realistically structured data without requiring the
reviewer to sign up for three vendors.

In production, the fixture path is replaced by the live path. The
detector logic is unchanged because both paths populate the same
`Prospect` data structure.

---

## Repo layout

```
zeutara-signal-engine/
├── src/
│   ├── config.py          # ICP definitions, signal weights, thresholds
│   ├── models.py          # Prospect, Signal, ScoredProspect dataclasses
│   ├── signals.py         # 15 signal detectors, one function each
│   ├── scoring.py         # ICP filter + weight summation + routing
│   ├── pipeline.py        # End-to-end orchestration
│   ├── data_loaders.py    # Fixture loader + documented API clients
│   └── run.py             # CLI entry point
├── data/
│   └── prospects.json     # 25 fixture companies, real + synthesized signals
├── docs/
│   └── integrations.md    # Production API wiring plan (PredictLeads,
│                          # Crunchbase, Apify) with cost model
├── tests/
│   └── test_signals.py    # 23 tests covering every detector + the pipeline
├── examples/
│   └── sample_output.txt  # What you should see after a fresh run
└── README.md
```

---

## Tuning the engine

Three things you change to tune the engine without touching detector code:

1. **`LANE_A_ICP` / `LANE_B_ICP`** in `src/config.py` — change who qualifies
   for each lane (stage, capital range, headcount, geography).
2. **Signal weight tables** in `src/config.py` — change which signals carry
   the most weight. Add a new signal by writing a detector function in
   `src/signals.py` and registering it in `LANE_A_DETECTORS` or
   `LANE_B_DETECTORS`.
3. **`PRIORITY_THRESHOLDS`** in `src/config.py` — change what score lands
   in HOT vs WARM vs COOL.

All three are deliberately data, not code: the analyst on duty tunes them
based on which signals are actually predicting closed-won engagements.

---

## Design choices worth flagging

1. **Pure-Python stdlib, no dependencies for the demo path.** Every pip
   install is a chance for the reviewer to hit a version conflict in their
   15-minute window. The live integration layer will pull in `requests`
   and similar, but the demo runs on Python 3.10+ alone.

2. **Detectors are pure functions.** Each detector takes a `Prospect` and
   returns a `Signal`. No side effects, no shared state, trivially
   testable. A second engineer can add a new signal without reading any
   other module.

3. **The fixture data is real companies with synthesized signal
   annotations**, not invented companies with realistic-looking data. This
   keeps the reviewer's sanity check honest: they can look up Modal Labs,
   verify the stage and approximate funding history is accurate, then
   evaluate whether the signal patterns are the right things to look for.

4. **Two lanes share one engine.** The detector functions are different,
   the ICP filters are different, the weights are different, but the
   pipeline, scoring math, models, and output formats are the same.
   Adding a Lane C (e.g., bootstrapped at $5-15M ARR) requires only adding
   one ICP dict, one weight table, and one detector dict.

5. **Output is both CSV and JSON, and both are human-meaningful.** An
   analyst should be able to triage from the CSV alone. The JSON is for
   the next stage of the pipeline (Attio sync, Instantly campaign trigger).

---

## If I had two more days

In rough priority order:

1. **Wire one live API end-to-end.** PredictLeads job-openings endpoint
   first, because it produces the strongest single signal (`open_senior_role_stale`)
   and the API is well-documented with a 100-call-free monthly tier for
   testing. This alone proves the architecture is production-shaped, not
   just demo-shaped.

2. **Add hallucination guard for the founder-content detector.** Currently
   it keyword-matches LinkedIn post text. A second-pass LLM call (Claude
   Haiku 4.5, ~$1/$5 per 1M tokens) should classify whether the post
   *actually* indicates help-seeking vs. someone using the word "fractional"
   in another context. Cost: roughly $0.001 per classification, so under
   $50/mo at 50K posts evaluated.

3. **Backtest the weights against closed-won history.** The weights here
   are calibrated to Zeutara's "execution gap at moment of strain" thesis,
   not to real conversion data because Zeutara has not shared its history
   with me. With 30-60 closed deals as ground truth, the weights should be
   refit using a simple logistic regression on which signals predicted
   close. The structure of the engine supports this; the data is what is
   missing.

4. **Add a "near-miss" output bucket.** Prospects that scored 8-11
   (just below COOL threshold) are interesting from a learning standpoint
   because tuning down any one threshold pulls them into the queue.
   Output them to a separate file for weekly weight-review.

5. **Add LinkedIn DM and Twitter/X content scraping as additional signal
   sources.** Right now `founder_help_seeking_content` reads from LinkedIn
   posts only. Twitter/X is where many founders actually post hiring pain
   in 2026.

6. **Build the messaging-generation component** (next load-bearing piece
   downstream). Take a HOT-priority `ScoredProspect`, generate a 60-word
   personalized opening message via Claude Sonnet 4.6 grounded in the
   specific fired signals. Cost: ~$0.01 per message. Output ready for
   Instantly campaign import.

7. **Add a feedback loop.** When a prospect closes or rejects, the
   `ScoredProspect` snapshot at time-of-outreach should be archived to
   `data/outcomes.jsonl`. This is the ground truth for the backtest in
   item 3 above.

---

## AI tooling used

- **Claude (Anthropic)**: drafted the architecture, generated detector
  scaffolding, paired on the scoring logic, and reviewed the test
  coverage. Every detector function was reviewed and edited by hand
  before commit; no detector ships as raw model output.
- **Web search (via OpenAI)**: gathered 2024-2026 vendor pricing
  (PredictLeads, Crunchbase, Apollo, Clay, Instantly, HeyReach),
  deliverability benchmarks (Validity 2025, Instantly 2026), and Carta
  graduation rate data. Sources are cited in the defending paper.
