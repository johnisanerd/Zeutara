"""
Zeutara Signal Detection Engine - Data Models

Defines the core data structures: Prospect, Signal, ScoredProspect.

These are the types that flow through the pipeline:
   raw company data  →  Prospect
   detected triggers →  Signal
   scored output     →  ScoredProspect

Keep models small and serializable. The full pipeline must round-trip
through JSON for storage in Attio (the recommended CRM) and for the
"sync to outreach" handoff.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timezone
from typing import Literal, Optional
import json

Stage = Literal[
    "pre_seed", "seed", "series_a", "series_b",
    "series_c", "series_d", "growth", "public", "acquired"
]

Lane = Literal["A", "B"]
Priority = Literal["HOT", "WARM", "COOL", "EXCLUDED"]


@dataclass
class Prospect:
    """
    A target company being evaluated.

    Fields are populated by the ingestion + enrichment layers from
    Crunchbase, LinkedIn, PredictLeads, and Apify scrapes. In the bundled
    fixture data, these are pre-populated from a CSV.
    """
    # Identity
    company_id: str
    company_name: str
    domain: str

    # Stage & capital
    stage: Stage
    total_raised_usd: int
    last_round_date: Optional[date] = None
    last_round_type: Optional[str] = None       # "seed", "series_a", "bridge", "extension"
    last_round_amount_usd: Optional[int] = None

    # Operations
    headcount: Optional[int] = None
    headcount_6mo_ago: Optional[int] = None     # for hiring velocity calc
    hq_country: Optional[str] = None
    hq_city: Optional[str] = None
    industry: Optional[str] = None

    # Founder / executive context
    founder_names: list[str] = field(default_factory=list)
    founder_linkedin_urls: list[str] = field(default_factory=list)

    # Free-form: raw text from news, posts, scrape results.
    # Stored so signal detectors can re-evaluate without re-fetching.
    raw_context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Serialize dates as ISO strings for JSON.
        if self.last_round_date:
            d["last_round_date"] = self.last_round_date.isoformat()
        return d


@dataclass
class Signal:
    """
    A single trigger that fired on a prospect.

    Each Signal carries the evidence (so the analyst can audit) and the
    weight contribution (so scoring is transparent).
    """
    signal_id: str                 # e.g. "recent_raise_60_to_180_days"
    fired: bool
    weight: int                    # contribution to total score
    evidence: str                  # human-readable: "Raised $8M Series A on 2026-02-14"
    source: str                    # "crunchbase", "linkedin", "apify", "predictleads", "fixture"
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["detected_at"] = self.detected_at.isoformat()
        return d


@dataclass
class ScoredProspect:
    """
    The output of the engine: a prospect with all fired signals attached,
    a final score, and a routing decision.
    """
    prospect: Prospect
    lane: Lane
    signals: list[Signal]
    score: int                     # 0-100
    priority: Priority
    rationale: str                 # one-line summary for the human reviewer

    def to_dict(self) -> dict:
        return {
            "prospect": self.prospect.to_dict(),
            "lane": self.lane,
            "signals": [s.to_dict() for s in self.signals if s.fired],
            "score": self.score,
            "priority": self.priority,
            "rationale": self.rationale,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)
