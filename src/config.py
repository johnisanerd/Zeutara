"""
Zeutara Signal Detection Engine - Configuration

Defines ICP criteria, signal weights, and scoring thresholds for the two
buyer lanes Zeutara targets:

  Lane A: Pre-seed / Seed / Series A founders with execution gaps
  Lane B: Growth-stage operators at structural inflection points

Each lane has its own signal weights because the triggers that indicate
"in market right now" are different for a $2M ARR founder still leading
sales vs. a $40M ARR CEO whose VP of Sales just resigned.

Changing any constant in this file changes the prospect ranking.
This is intentional: the analyst on duty tunes these weights based on
which signals are actually predicting closed-won.
"""

from dataclasses import dataclass
from typing import Literal

Lane = Literal["A", "B"]


# ----------------------------------------------------------------------
# ICP DEFINITIONS
# ----------------------------------------------------------------------
# These are intentionally sharper than the brief's "founders in the
# pre-seed, seed, and Series A space." Sharper ICP = better signal-to-noise.

LANE_A_ICP = {
    "stages": ["seed", "series_a"],          # Pre-seed excluded: too early for retainer economics
    "min_total_raised_usd": 1_500_000,        # Filters tinkerers
    "max_total_raised_usd": 25_000_000,       # Above this they hire in-house
    "min_headcount": 5,
    "max_headcount": 60,
    "geographies": ["United States", "Canada"],
    "disqualifiers": [
        "publicly traded",
        "acquired",
        "shut_down",
        "series_b_or_later",
    ],
}

LANE_B_ICP = {
    "stages": ["series_b", "series_c", "series_d", "growth"],
    "min_total_raised_usd": 25_000_000,
    "max_total_raised_usd": 250_000_000,      # Above this they hire McKinsey
    "min_headcount": 60,
    "max_headcount": 600,
    "geographies": ["United States", "Canada"],
    "disqualifiers": [
        "publicly traded",
        "acquired",
        "shut_down",
        "pre_series_b",
    ],
}


# ----------------------------------------------------------------------
# SIGNAL WEIGHTS
# ----------------------------------------------------------------------
# Each signal contributes to a 0-100 priority score. Weights are calibrated
# to Zeutara's "execution gap at moment of strain" thesis: signals that
# indicate active deployment pressure or visible execution failure score
# highest.
#
# Lane A signals lean toward post-funding deployment pressure and missing
# senior hires. Lane B signals lean toward executive turnover and
# governance inflection.

LANE_A_SIGNAL_WEIGHTS = {
    # The single highest-signal trigger: recent raise + slow hiring.
    # Capital is sitting on the balance sheet; founder is the bottleneck.
    "recent_raise_60_to_180_days": 22,

    # Open VP/Director role > 60 days = execution gap is visible to
    # the founder and they have failed to close it internally.
    "open_senior_role_stale": 20,

    # First sales hire churn within 6 months. Lemkin/SaaStr: ~70% of first
    # VP Sales hires fail in 12 months. This is the failed-VP-hire reset moment.
    "first_sales_hire_churned": 18,

    # Bridge round, extension, or SAFE post-priced round. Carta 2024 data:
    # ~40% of seed and Series A activity is bridge. Founder is between rounds,
    # often without time to scale the GTM motion in-house.
    "bridge_or_extension_round": 14,

    # Founder LinkedIn content mentioning hiring pain, scaling pain,
    # or fractional help.
    "founder_help_seeking_content": 10,

    # Time since last round > 18mo seed / > 24mo Series A: runway pressure.
    "runway_pressure_stale_round": 8,

    # Hiring velocity < 30% of expected post-funding ramp.
    "hiring_stalled_post_raise": 8,
}

LANE_B_SIGNAL_WEIGHTS = {
    # C-level departure: highest-signal inflection at growth stage.
    "c_level_departure_90d": 25,

    # Layoffs in last 90 days. Functional restructure usually follows.
    "recent_layoff_event": 20,

    # Multiple "Head of X" or "VP of X" roles open simultaneously
    # = active restructure of leadership team.
    "multiple_senior_roles_open": 18,

    # New board member or new lead investor (governance cadence shift).
    "board_or_lead_investor_change": 12,

    # Pivot announcement, product line discontinuation, or material
    # market expansion (PredictLeads news event categories).
    "strategic_announcement_event": 10,

    # > 24 months since last round with no recent traction news.
    "stale_capital_no_traction": 8,

    # Founder/CEO posting about scaling pain at growth stage.
    "ceo_help_seeking_content": 7,
}


# ----------------------------------------------------------------------
# SCORING THRESHOLDS
# ----------------------------------------------------------------------
# A prospect's score is summed across signals that fire, then capped at 100.
# These thresholds drive routing decisions: HOT goes to a partner for same-day
# review, WARM goes into the standard analyst queue, COOL stays in nurture.

PRIORITY_THRESHOLDS = {
    "HOT": 50,    # Partner reviews within 24h, custom message
                  # ~3 substantial signals firing = "in market right now"
    "WARM": 30,   # Analyst processes within 72h, template + light personalization
                  # ~2 substantial signals = worth pursuing
    "COOL": 12,   # Quarterly nurture, no immediate action
                  # 1 signal = on the radar, not actionable
    # Below 12 = excluded entirely. Re-evaluate on next signal refresh.
}


# ----------------------------------------------------------------------
# DISQUALIFIERS (hard filters, applied before scoring)
# ----------------------------------------------------------------------
HARD_DISQUALIFIERS = {
    "max_total_raised_usd_global": 500_000_000,    # Too large, McKinsey territory
    "min_total_raised_usd_global": 250_000,         # Too early, no retainer budget
    "blocked_industries": [
        "cannabis",                                  # Banking/payment friction
        "adult_content",
        "gambling",
        "weapons_manufacturing",
    ],
    "blocked_geographies": [
        # Lanes are explicitly US/Canada in this build. Expand only after
        # GDPR posture is documented.
        "Russia",
        "Iran",
        "North Korea",
        "Syria",
    ],
}


# ----------------------------------------------------------------------
# DATA SOURCES (referenced by enrichment layer)
# ----------------------------------------------------------------------
# In production, each source maps to an API client. In the bundled-data
# prototype, these are documentation only.

DATA_SOURCES = {
    "funding_events": {
        "primary": "Crunchbase Pro API",
        "fallback": "PredictLeads Financing dataset",
        "cost_monthly_usd": 49,
    },
    "job_postings": {
        "primary": "PredictLeads Job Openings dataset",
        "fallback": "Apify LinkedIn Jobs scraper",
        "cost_monthly_usd": 500,
    },
    "executive_changes": {
        "primary": "Apify LinkedIn employment-change scraper",
        "fallback": "PredictLeads news event API",
        "cost_monthly_usd": 199,
    },
    "headcount_tracking": {
        "primary": "PredictLeads Employee Count dataset",
        "fallback": "Apify LinkedIn company-size scraper",
        "cost_monthly_usd": 0,  # included with PredictLeads bundle
    },
    "founder_content": {
        "primary": "Apify LinkedIn post scraper",
        "fallback": "manual analyst review",
        "cost_monthly_usd": 0,  # shared Apify quota
    },
    "ai_personalization": {
        "primary": "Claude Sonnet 4.6 ($3/$15 per 1M tokens)",
        "fallback": "Claude Haiku 4.5 for classification",
        "cost_monthly_usd": 100,  # estimated at ~10K personalized messages
    },
}


@dataclass(frozen=True)
class ScoringConfig:
    """Bundle the configuration for a given lane."""
    lane: Lane
    icp: dict
    weights: dict


def get_lane_config(lane: Lane) -> ScoringConfig:
    if lane == "A":
        return ScoringConfig(lane="A", icp=LANE_A_ICP, weights=LANE_A_SIGNAL_WEIGHTS)
    elif lane == "B":
        return ScoringConfig(lane="B", icp=LANE_B_ICP, weights=LANE_B_SIGNAL_WEIGHTS)
    else:
        raise ValueError(f"Unknown lane: {lane}. Must be 'A' or 'B'.")
