"""
Zeutara Signal Detection Engine - Pipeline

Orchestrates: load prospects → score each → split into priority buckets →
emit ranked queue.

Two output formats:
  1. ranked CSV for analyst review (sorted by score desc)
  2. JSON for downstream sync to CRM (Attio) or outreach (Instantly)
"""

import csv
import json
from pathlib import Path

from .data_loaders import load_fixture_prospects
from .scoring import score_prospect
from .signals import get_detectors_for_lane
from .models import ScoredProspect


def run_pipeline(lane: str, source: str = "fixture") -> list[ScoredProspect]:
    """
    End-to-end run for a single lane.
    Returns the scored, sorted list (highest priority first).
    """
    if source == "fixture":
        prospects = load_fixture_prospects()
    else:
        # Live path is documented in data_loaders.py but not wired
        # in this prototype scope.
        raise NotImplementedError(
            f"Source '{source}' not implemented in prototype. Use 'fixture'."
        )

    detectors = get_detectors_for_lane(lane)
    scored = [score_prospect(p, lane, detectors) for p in prospects]

    # Sort descending by score; EXCLUDED sinks to the bottom.
    scored.sort(key=lambda sp: (sp.score, len([s for s in sp.signals if s.fired])), reverse=True)
    return scored


def write_csv(scored: list[ScoredProspect], out_path: Path) -> None:
    """Write a flat CSV the analyst can open in Excel/Numbers."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "priority", "score", "company_name", "stage", "total_raised_usd",
            "headcount", "lane", "fired_signals_count",
            "top_signal", "top_signal_evidence", "rationale",
        ])
        for sp in scored:
            fired = [s for s in sp.signals if s.fired]
            top = max(fired, key=lambda s: s.weight) if fired else None
            writer.writerow([
                sp.priority,
                sp.score,
                sp.prospect.company_name,
                sp.prospect.stage,
                sp.prospect.total_raised_usd,
                sp.prospect.headcount,
                sp.lane,
                len(fired),
                top.signal_id if top else "",
                top.evidence if top else "",
                sp.rationale,
            ])


def write_json(scored: list[ScoredProspect], out_path: Path) -> None:
    """Write structured JSON ready for downstream CRM/outreach sync."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [sp.to_dict() for sp in scored]
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)


def summarize(scored: list[ScoredProspect]) -> dict:
    """Aggregate stats for the console summary."""
    by_priority = {"HOT": 0, "WARM": 0, "COOL": 0, "EXCLUDED": 0}
    for sp in scored:
        by_priority[sp.priority] += 1

    actionable = [sp for sp in scored if sp.priority in ("HOT", "WARM")]
    avg_score_actionable = (
        sum(sp.score for sp in actionable) / len(actionable)
        if actionable else 0
    )

    return {
        "total_prospects": len(scored),
        "by_priority": by_priority,
        "actionable_count": len(actionable),
        "avg_score_actionable": round(avg_score_actionable, 1),
        "top_3_companies": [
            {"name": sp.prospect.company_name, "score": sp.score, "priority": sp.priority}
            for sp in scored[:3]
        ],
    }
