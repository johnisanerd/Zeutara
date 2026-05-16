"""
Zeutara Signal Detection Engine - Signal Detectors

This is the core IP of the prototype. Each detector function takes a
Prospect and returns a Signal indicating whether the trigger fired.

Detectors are intentionally small, testable, and independent. A new
analyst can read any single detector in 30 seconds and understand
what it does. New signals are added by writing one function and
registering it in the dispatch dict at the bottom.

Each detector encodes a specific hypothesis about when a founder is
"in market" for execution help. The hypotheses are defended in the
paper; the code is the operational proof.
"""

from datetime import date, timedelta
from .models import Prospect, Signal
from .config import LANE_A_SIGNAL_WEIGHTS, LANE_B_SIGNAL_WEIGHTS


# ----------------------------------------------------------------------
# Lane A detectors (pre-seed / seed / Series A)
# ----------------------------------------------------------------------

def detect_recent_raise_60_to_180_days(p: Prospect) -> Signal:
    """
    Capital was deployed recently enough that pressure to use it is
    real (60+ days post-close), but recently enough that internal hiring
    hasn't caught up (under 180 days). This is the prime Zeutara wedge:
    money in the bank, founder still leading sales.
    """
    sig_id = "recent_raise_60_to_180_days"
    weight = LANE_A_SIGNAL_WEIGHTS[sig_id]

    if not p.last_round_date:
        return Signal(sig_id, False, weight, "no funding date on record", "system")

    days_since = (date.today() - p.last_round_date).days
    if 60 <= days_since <= 180:
        return Signal(
            sig_id, True, weight,
            f"raised {p.last_round_type or 'a round'} {days_since} days ago "
            f"(${p.last_round_amount_usd or 0:,})",
            "crunchbase",
        )
    return Signal(sig_id, False, weight, f"last round was {days_since} days ago (outside 60-180 window)", "crunchbase")


def detect_open_senior_role_stale(p: Prospect) -> Signal:
    """
    VP, Head of, or Director-level role posted >60 days ago and still open.
    Median time-to-fill for senior GTM roles at funded Series A is 30-45 days
    per recruiting benchmarks. >60 days open = the founder cannot close the
    hire internally. This is the most direct "execution gap" signal we get
    from public data.
    """
    sig_id = "open_senior_role_stale"
    weight = LANE_A_SIGNAL_WEIGHTS[sig_id]

    open_roles = p.raw_context.get("open_senior_roles", [])
    stale = [r for r in open_roles if r.get("days_open", 0) >= 60]

    if stale:
        roles_text = ", ".join(f"{r['title']} ({r['days_open']}d open)" for r in stale[:3])
        return Signal(sig_id, True, weight, f"stale senior role(s): {roles_text}", "predictleads")
    return Signal(sig_id, False, weight, "no senior roles open >60 days", "predictleads")


def detect_first_sales_hire_churned(p: Prospect) -> Signal:
    """
    First sales leader joined and departed within 6 months. Lemkin/SaaStr's
    long-running data point: ~70% of first-VP-Sales hires miss in year one.
    When this happens, the founder is back to leading sales and is unusually
    receptive to outside help that doesn't require re-hiring immediately.
    """
    sig_id = "first_sales_hire_churned"
    weight = LANE_A_SIGNAL_WEIGHTS[sig_id]

    churn_events = p.raw_context.get("sales_leader_churn", [])
    recent = [e for e in churn_events if e.get("tenure_months", 99) <= 6
              and e.get("departed_days_ago", 999) <= 120]

    if recent:
        e = recent[0]
        return Signal(
            sig_id, True, weight,
            f"first sales leader ({e.get('title', 'VP Sales')}) departed after "
            f"{e['tenure_months']}mo tenure, {e['departed_days_ago']}d ago",
            "linkedin",
        )
    return Signal(sig_id, False, weight, "no recent sales-leader churn detected", "linkedin")


def detect_bridge_or_extension_round(p: Prospect) -> Signal:
    """
    Bridge rounds and extensions made up ~40% of seed/Series A activity in
    Carta's 2024 data. They are explicit signals that the company has not
    hit the metrics for the next priced round. Founders in this state are
    measurably more open to GTM help that compresses time-to-traction.
    """
    sig_id = "bridge_or_extension_round"
    weight = LANE_A_SIGNAL_WEIGHTS[sig_id]

    round_type = (p.last_round_type or "").lower()
    if any(token in round_type for token in ["bridge", "extension", "safe", "convertible"]):
        return Signal(
            sig_id, True, weight,
            f"most recent round is a {p.last_round_type}",
            "crunchbase",
        )
    return Signal(sig_id, False, weight, f"most recent round ({p.last_round_type}) is a priced round", "crunchbase")


def detect_founder_help_seeking_content(p: Prospect) -> Signal:
    """
    Founder LinkedIn content within 60 days mentioning hiring pain, scaling
    challenges, or fractional/advisory help. Highest-intent public signal we
    can capture short of an inbound inquiry.
    """
    sig_id = "founder_help_seeking_content"
    weight = LANE_A_SIGNAL_WEIGHTS[sig_id]

    posts = p.raw_context.get("recent_founder_posts", [])
    keywords = [
        "fractional", "advisor", "advisory", "help scaling", "hiring is hard",
        "looking for a", "any recs", "any recommendations", "need a great",
        "struggling with", "GTM help", "sales help", "marketing help",
    ]

    matches = []
    for post in posts:
        text = post.get("text", "").lower()
        hits = [k for k in keywords if k in text]
        if hits and post.get("days_ago", 999) <= 60:
            matches.append((post, hits))

    if matches:
        post, hits = matches[0]
        snippet = post["text"][:120].replace("\n", " ")
        return Signal(
            sig_id, True, weight,
            f"founder posted {post.get('days_ago', '?')}d ago (matched: {hits[0]}): \"{snippet}...\"",
            "apify_linkedin",
        )
    return Signal(sig_id, False, weight, "no help-seeking content in last 60 days", "apify_linkedin")


def detect_runway_pressure_stale_round(p: Prospect) -> Signal:
    """
    Time since last round > 18 months at seed or > 24 months at Series A.
    With Carta showing median seed-to-A wait stretched to ~25 months and
    Series A-to-B to 2.8 years in 2025, this band catches companies that
    are in runway-pressure territory before a "graceful" raise window.
    """
    sig_id = "runway_pressure_stale_round"
    weight = LANE_A_SIGNAL_WEIGHTS[sig_id]

    if not p.last_round_date:
        return Signal(sig_id, False, weight, "no funding date on record", "system")

    days_since = (date.today() - p.last_round_date).days

    threshold = 540 if p.stage == "seed" else 730 if p.stage == "series_a" else None
    if threshold is None:
        return Signal(sig_id, False, weight, f"stage {p.stage} not evaluated for runway pressure", "system")

    if days_since >= threshold:
        return Signal(
            sig_id, True, weight,
            f"{days_since}d since last {p.stage} round (threshold: {threshold}d)",
            "crunchbase",
        )
    return Signal(sig_id, False, weight, f"{days_since}d since last round (below threshold)", "crunchbase")


def detect_hiring_stalled_post_raise(p: Prospect) -> Signal:
    """
    Headcount growth in 6mo post-raise is < 30% of the expected ramp.
    Funded Series A typically grows 80-150% in 12mo (Carta historical).
    A company that has barely grown after a recent raise is showing
    visible execution drag.
    """
    sig_id = "hiring_stalled_post_raise"
    weight = LANE_A_SIGNAL_WEIGHTS[sig_id]

    if not (p.headcount and p.headcount_6mo_ago and p.last_round_date):
        return Signal(sig_id, False, weight, "missing headcount or funding history", "system")

    days_since = (date.today() - p.last_round_date).days
    if days_since > 365:
        return Signal(sig_id, False, weight, "last round >365d ago, not applicable", "system")

    growth_pct = (p.headcount - p.headcount_6mo_ago) / max(p.headcount_6mo_ago, 1)
    if growth_pct < 0.15:    # <15% growth in 6mo post-raise = stalled
        return Signal(
            sig_id, True, weight,
            f"headcount grew only {growth_pct*100:.0f}% in 6mo post-raise "
            f"({p.headcount_6mo_ago} -> {p.headcount})",
            "linkedin",
        )
    return Signal(sig_id, False, weight, f"headcount growth {growth_pct*100:.0f}% in 6mo (above threshold)", "linkedin")


# ----------------------------------------------------------------------
# Lane B detectors (growth-stage structural inflection)
# ----------------------------------------------------------------------

def detect_c_level_departure_90d(p: Prospect) -> Signal:
    """
    C-level executive (CRO, CFO, CMO, COO) departed within 90 days. Highest-
    signal trigger for structural inflection at growth stage: revenue
    architecture, capital allocation, or operations are explicitly in motion.
    """
    sig_id = "c_level_departure_90d"
    weight = LANE_B_SIGNAL_WEIGHTS[sig_id]

    departures = p.raw_context.get("executive_departures", [])
    c_level_titles = ["CRO", "CFO", "CMO", "COO", "CEO", "Chief Revenue", "Chief Financial",
                      "Chief Marketing", "Chief Operating", "President"]

    recent = [
        d for d in departures
        if any(t.lower() in d.get("title", "").lower() for t in c_level_titles)
        and d.get("departed_days_ago", 999) <= 90
    ]

    if recent:
        d = recent[0]
        return Signal(
            sig_id, True, weight,
            f"{d['title']} departed {d['departed_days_ago']}d ago",
            "linkedin",
        )
    return Signal(sig_id, False, weight, "no C-level departures in last 90 days", "linkedin")


def detect_recent_layoff_event(p: Prospect) -> Signal:
    """
    Layoff event in the last 90 days. Carries restructure signal:
    functional reorganization usually follows a layoff and creates a
    window for "execution architecture" engagements.
    """
    sig_id = "recent_layoff_event"
    weight = LANE_B_SIGNAL_WEIGHTS[sig_id]

    events = p.raw_context.get("news_events", [])
    layoff_events = [e for e in events if e.get("category") == "layoff"
                     and e.get("days_ago", 999) <= 90]

    if layoff_events:
        e = layoff_events[0]
        return Signal(
            sig_id, True, weight,
            f"layoff announced {e['days_ago']}d ago: {e.get('headline', '')}",
            "predictleads",
        )
    return Signal(sig_id, False, weight, "no layoff events in last 90 days", "predictleads")


def detect_multiple_senior_roles_open(p: Prospect) -> Signal:
    """
    Three or more "Head of" or "VP of" roles open simultaneously =
    explicit restructure of the leadership team. The board has likely
    asked for an org redesign; Zeutara's window is before the new
    heads of are seated.
    """
    sig_id = "multiple_senior_roles_open"
    weight = LANE_B_SIGNAL_WEIGHTS[sig_id]

    open_roles = p.raw_context.get("open_senior_roles", [])
    senior_open = [r for r in open_roles
                   if any(t in r.get("title", "").lower() for t in ["head of", "vp ", "vice president"])]

    if len(senior_open) >= 3:
        roles_text = ", ".join(r["title"] for r in senior_open[:5])
        return Signal(
            sig_id, True, weight,
            f"{len(senior_open)} senior roles open simultaneously: {roles_text}",
            "predictleads",
        )
    return Signal(sig_id, False, weight, f"only {len(senior_open)} senior roles open", "predictleads")


def detect_board_or_lead_investor_change(p: Prospect) -> Signal:
    """
    New board member, new lead investor, or board observer change in the
    last 120 days. Governance cadence shifts almost always trigger
    revenue-architecture or capital-allocation rework.
    """
    sig_id = "board_or_lead_investor_change"
    weight = LANE_B_SIGNAL_WEIGHTS[sig_id]

    events = p.raw_context.get("news_events", [])
    governance = [e for e in events
                  if e.get("category") in ("board_change", "new_lead_investor")
                  and e.get("days_ago", 999) <= 120]

    if governance:
        e = governance[0]
        return Signal(sig_id, True, weight, f"{e['category']} {e['days_ago']}d ago: {e.get('headline', '')}", "predictleads")
    return Signal(sig_id, False, weight, "no governance changes in last 120 days", "predictleads")


def detect_strategic_announcement_event(p: Prospect) -> Signal:
    """
    Pivot, product discontinuation, or material market expansion in the
    last 90 days. From PredictLeads' news event taxonomy.
    """
    sig_id = "strategic_announcement_event"
    weight = LANE_B_SIGNAL_WEIGHTS[sig_id]

    events = p.raw_context.get("news_events", [])
    strategic = [e for e in events
                 if e.get("category") in ("pivot", "product_launch", "market_expansion", "discontinuation")
                 and e.get("days_ago", 999) <= 90]

    if strategic:
        e = strategic[0]
        return Signal(sig_id, True, weight, f"{e['category']} {e['days_ago']}d ago: {e.get('headline', '')}", "predictleads")
    return Signal(sig_id, False, weight, "no strategic announcements in last 90 days", "predictleads")


def detect_stale_capital_no_traction(p: Prospect) -> Signal:
    """
    >24 months since last round and no recent traction news. Capital is
    deployed and the next raise narrative isn't writing itself.
    """
    sig_id = "stale_capital_no_traction"
    weight = LANE_B_SIGNAL_WEIGHTS[sig_id]

    if not p.last_round_date:
        return Signal(sig_id, False, weight, "no funding date on record", "system")

    days_since = (date.today() - p.last_round_date).days
    if days_since < 730:
        return Signal(sig_id, False, weight, f"{days_since}d since round (below 730d threshold)", "crunchbase")

    events = p.raw_context.get("news_events", [])
    has_traction = any(e.get("category") in ("revenue_milestone", "customer_announcement", "product_launch")
                       and e.get("days_ago", 999) <= 180
                       for e in events)

    if not has_traction:
        return Signal(
            sig_id, True, weight,
            f"{days_since}d since last round, no traction news in 180 days",
            "predictleads",
        )
    return Signal(sig_id, False, weight, f"{days_since}d since round but recent traction news present", "predictleads")


def detect_ceo_help_seeking_content(p: Prospect) -> Signal:
    """
    CEO posting about scaling pain, hiring challenges, or organizational
    complexity. Same logic as Lane A founder content but pitched to
    growth-stage operator vocabulary.
    """
    sig_id = "ceo_help_seeking_content"
    weight = LANE_B_SIGNAL_WEIGHTS[sig_id]

    posts = p.raw_context.get("recent_founder_posts", [])
    keywords = [
        "org design", "scaling pains", "exec team", "leadership team",
        "reorg", "fractional", "interim", "advisor", "operating cadence",
        "executive search", "governance",
    ]

    matches = []
    for post in posts:
        text = post.get("text", "").lower()
        hits = [k for k in keywords if k in text]
        if hits and post.get("days_ago", 999) <= 60:
            matches.append((post, hits))

    if matches:
        post, hits = matches[0]
        snippet = post["text"][:120].replace("\n", " ")
        return Signal(
            sig_id, True, weight,
            f"CEO posted {post.get('days_ago', '?')}d ago (matched: {hits[0]}): \"{snippet}...\"",
            "apify_linkedin",
        )
    return Signal(sig_id, False, weight, "no help-seeking content in last 60 days", "apify_linkedin")


# ----------------------------------------------------------------------
# Detector registry
# ----------------------------------------------------------------------
# To add a new signal: write the function, add to the dict below.
# Adding a signal also requires adding its weight to config.py.

LANE_A_DETECTORS = {
    "recent_raise_60_to_180_days": detect_recent_raise_60_to_180_days,
    "open_senior_role_stale": detect_open_senior_role_stale,
    "first_sales_hire_churned": detect_first_sales_hire_churned,
    "bridge_or_extension_round": detect_bridge_or_extension_round,
    "founder_help_seeking_content": detect_founder_help_seeking_content,
    "runway_pressure_stale_round": detect_runway_pressure_stale_round,
    "hiring_stalled_post_raise": detect_hiring_stalled_post_raise,
}

LANE_B_DETECTORS = {
    "c_level_departure_90d": detect_c_level_departure_90d,
    "recent_layoff_event": detect_recent_layoff_event,
    "multiple_senior_roles_open": detect_multiple_senior_roles_open,
    "board_or_lead_investor_change": detect_board_or_lead_investor_change,
    "strategic_announcement_event": detect_strategic_announcement_event,
    "stale_capital_no_traction": detect_stale_capital_no_traction,
    "ceo_help_seeking_content": detect_ceo_help_seeking_content,
}


def get_detectors_for_lane(lane: str) -> dict:
    if lane == "A":
        return LANE_A_DETECTORS
    elif lane == "B":
        return LANE_B_DETECTORS
    else:
        raise ValueError(f"Unknown lane: {lane}")
