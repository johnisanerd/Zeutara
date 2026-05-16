"""
Zeutara Signal Detection Engine - Scoring & Routing

Takes a Prospect plus the signals that fired on it, produces a
ScoredProspect with priority routing.

Two responsibilities:
  1. Score: sum of fired-signal weights, capped at 100
  2. Route: HOT / WARM / COOL / EXCLUDED based on thresholds in config

ICP disqualifiers are applied here, not in the signal layer. A
prospect failing hard filters short-circuits to EXCLUDED without
even running detectors.
"""

from .config import (
    LANE_A_ICP, LANE_B_ICP, HARD_DISQUALIFIERS, PRIORITY_THRESHOLDS,
)
from .models import Prospect, Signal, ScoredProspect


def in_icp(prospect: Prospect, lane: str) -> tuple[bool, str]:
    """
    Hard filter against ICP definition. Returns (passes, reason).
    The reason is logged so the analyst can audit exclusions.
    """
    icp = LANE_A_ICP if lane == "A" else LANE_B_ICP

    if prospect.stage not in icp["stages"]:
        return False, f"stage {prospect.stage} not in lane {lane} ({icp['stages']})"

    if prospect.total_raised_usd < icp["min_total_raised_usd"]:
        return False, f"total raised ${prospect.total_raised_usd:,} below minimum"

    if prospect.total_raised_usd > icp["max_total_raised_usd"]:
        return False, f"total raised ${prospect.total_raised_usd:,} above maximum"

    if prospect.headcount is not None:
        if prospect.headcount < icp["min_headcount"]:
            return False, f"headcount {prospect.headcount} below minimum"
        if prospect.headcount > icp["max_headcount"]:
            return False, f"headcount {prospect.headcount} above maximum"

    if prospect.hq_country and prospect.hq_country not in icp["geographies"]:
        return False, f"geography {prospect.hq_country} not in target list"

    # Global hard filters
    if prospect.total_raised_usd > HARD_DISQUALIFIERS["max_total_raised_usd_global"]:
        return False, "above global cap (McKinsey territory)"

    if prospect.industry and prospect.industry.lower() in [
        i.lower() for i in HARD_DISQUALIFIERS["blocked_industries"]
    ]:
        return False, f"industry {prospect.industry} blocked"

    return True, "passes ICP"


def assign_priority(score: int) -> str:
    """Map a numeric score to a routing bucket."""
    if score >= PRIORITY_THRESHOLDS["HOT"]:
        return "HOT"
    if score >= PRIORITY_THRESHOLDS["WARM"]:
        return "WARM"
    if score >= PRIORITY_THRESHOLDS["COOL"]:
        return "COOL"
    return "EXCLUDED"


def build_rationale(prospect: Prospect, signals: list[Signal], score: int, priority: str) -> str:
    """
    One-line summary the analyst sees in their queue. Designed to make
    the "why is this prospect here" answer obvious in under 5 seconds.
    """
    fired = [s for s in signals if s.fired]
    if not fired:
        return f"{prospect.company_name}: no signals fired (score 0)"

    top_two = sorted(fired, key=lambda s: s.weight, reverse=True)[:2]
    top_evidence = "; ".join(s.evidence for s in top_two)
    return (
        f"{prospect.company_name} | {priority} ({score}/100) | "
        f"{len(fired)} signals | top: {top_evidence}"
    )


def score_prospect(prospect: Prospect, lane: str, detectors: dict) -> ScoredProspect:
    """
    The core entry point. Runs all detectors for the given lane against
    the prospect, sums fired weights, applies thresholds, returns a
    ScoredProspect ready for human review.
    """
    passes, reason = in_icp(prospect, lane)
    if not passes:
        return ScoredProspect(
            prospect=prospect,
            lane=lane,
            signals=[],
            score=0,
            priority="EXCLUDED",
            rationale=f"{prospect.company_name}: excluded ({reason})",
        )

    signals = [detector(prospect) for detector in detectors.values()]
    fired = [s for s in signals if s.fired]
    raw_score = sum(s.weight for s in fired)
    score = min(raw_score, 100)
    priority = assign_priority(score)
    rationale = build_rationale(prospect, signals, score, priority)

    return ScoredProspect(
        prospect=prospect,
        lane=lane,
        signals=signals,
        score=score,
        priority=priority,
        rationale=rationale,
    )
