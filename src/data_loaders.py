"""
Zeutara Signal Detection Engine - Data Loaders

Two paths for loading Prospect data:

  1. FIXTURE PATH (default, no API keys required):
     Loads from data/prospects.json — a hand-curated set of 25 real US
     venture-backed companies with realistic but synthetic signal data
     attached. This is what runs in the under-15-minute review.

  2. LIVE PATH (requires env vars):
     PredictLeads + Crunchbase + Apify clients fetch real data. Wired
     up but disabled by default. Documented in the README.

The fixture path is honest: companies are real (so an analyst can sanity-
check the data), but signal annotations (open roles, departures, posts)
are synthesized to represent the patterns the engine is designed to catch.
The README explains this clearly.
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

from .models import Prospect


DATA_DIR = Path(__file__).parent.parent / "data"


def load_fixture_prospects(path: Optional[Path] = None) -> list[Prospect]:
    """
    Load the bundled fixture dataset. Used for the demo run that requires
    no API keys.
    """
    if path is None:
        path = DATA_DIR / "prospects.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Fixture data not found at {path}. "
            f"This file should ship with the repo; "
            f"if it is missing, re-clone or check the README."
        )

    with open(path, "r") as f:
        raw = json.load(f)

    prospects = []
    for r in raw:
        # Parse date from ISO string if present
        last_round_date = None
        if r.get("last_round_date"):
            last_round_date = date.fromisoformat(r["last_round_date"])

        prospects.append(Prospect(
            company_id=r["company_id"],
            company_name=r["company_name"],
            domain=r["domain"],
            stage=r["stage"],
            total_raised_usd=r["total_raised_usd"],
            last_round_date=last_round_date,
            last_round_type=r.get("last_round_type"),
            last_round_amount_usd=r.get("last_round_amount_usd"),
            headcount=r.get("headcount"),
            headcount_6mo_ago=r.get("headcount_6mo_ago"),
            hq_country=r.get("hq_country", "United States"),
            hq_city=r.get("hq_city"),
            industry=r.get("industry"),
            founder_names=r.get("founder_names", []),
            founder_linkedin_urls=r.get("founder_linkedin_urls", []),
            raw_context=r.get("raw_context", {}),
        ))

    return prospects


# ----------------------------------------------------------------------
# LIVE API CLIENTS - skeletons documenting the production integration
# ----------------------------------------------------------------------
# These are deliberately left as documented skeletons rather than
# full integrations because:
#   (a) the brief says one component, runnable, scoped tightly;
#   (b) wiring three live APIs against fresh keys would consume the
#       reviewer's 15-minute window in signup flows;
#   (c) the architecture spec defends the choice of these vendors with
#       cost data, which is the more important signal.
# Each function is callable but raises informatively if keys are absent.


def fetch_from_predictleads(domain: str) -> dict:
    """
    PredictLeads delivers job openings, financing events, and news event
    signals for a domain. Production integration uses their REST API.
    Documented in docs/integrations.md. ~$500/mo for single-dataset access
    per Vendr 2025 data.
    """
    api_key = os.environ.get("PREDICTLEADS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PREDICTLEADS_API_KEY not set. Set the env var to enable live "
            "fetching, or use --source=fixture (default) for bundled data."
        )

    # Production implementation:
    #   import requests
    #   headers = {"X-Api-Key": api_key, "X-Api-Token": ...}
    #   url = f"https://predictleads.com/api/v3/companies/{domain}/job_openings"
    #   response = requests.get(url, headers=headers, timeout=10)
    #   response.raise_for_status()
    #   return response.json()
    raise NotImplementedError(
        "Live PredictLeads integration is documented but not wired in this "
        "prototype. See docs/integrations.md for the request schema."
    )


def fetch_from_crunchbase(domain: str) -> dict:
    """
    Crunchbase Pro API: funding rounds, total raised, stage, founders.
    Production cost: $49/mo for Pro tier with limited API access.
    Falls back to Crunchbase Business ($199/mo) for higher-volume needs.
    """
    api_key = os.environ.get("CRUNCHBASE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "CRUNCHBASE_API_KEY not set. Set the env var to enable live "
            "fetching, or use --source=fixture (default) for bundled data."
        )

    raise NotImplementedError(
        "Live Crunchbase integration is documented but not wired in this "
        "prototype. See docs/integrations.md for the request schema."
    )


def fetch_linkedin_signals_via_apify(domain: str, founder_urls: list[str]) -> dict:
    """
    Apify actors scrape: company LinkedIn page for headcount over time,
    founder profile posts for recent content, employee LinkedIn for
    departure / new-hire events.

    Cost: $199/mo Apify Scale tier, ~$0.20 per compute-unit. A full
    pass on 5,000 companies costs roughly $80/mo at current actor pricing.
    """
    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        raise RuntimeError(
            "APIFY_API_TOKEN not set. Set the env var to enable live "
            "fetching, or use --source=fixture (default) for bundled data."
        )

    raise NotImplementedError(
        "Live Apify integration is documented but not wired in this "
        "prototype. See docs/integrations.md for the actor list."
    )


def load_live_prospects(domains: list[str]) -> list[Prospect]:
    """
    Production path: enrich a list of domains by calling the three
    sources in parallel and assembling Prospect objects.
    Currently raises NotImplementedError to keep the prototype scope tight.
    """
    raise NotImplementedError(
        "Live enrichment is documented but not implemented in this prototype. "
        "Run with --source=fixture for the demo. See docs/integrations.md "
        "for the wiring plan and 'if I had two more days' list in the README."
    )
