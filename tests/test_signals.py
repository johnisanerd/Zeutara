"""
Tests for the Zeutara signal engine.

Goal: every detector has at least one positive-case and one negative-case
test, and the scoring pipeline is tested end-to-end on the fixture data.

These run with stdlib unittest, no pytest dependency. The reviewer
runs them with `python -m unittest discover tests`.
"""

import unittest
from datetime import date, timedelta

from src.models import Prospect
from src.signals import (
    detect_recent_raise_60_to_180_days,
    detect_open_senior_role_stale,
    detect_first_sales_hire_churned,
    detect_bridge_or_extension_round,
    detect_founder_help_seeking_content,
    detect_c_level_departure_90d,
    detect_multiple_senior_roles_open,
    detect_recent_layoff_event,
)
from src.scoring import score_prospect, in_icp
from src.signals import LANE_A_DETECTORS, LANE_B_DETECTORS
from src.pipeline import run_pipeline


def make_prospect(**overrides) -> Prospect:
    """Helper for building minimal prospects in tests."""
    defaults = {
        "company_id": "test-001",
        "company_name": "Test Co",
        "domain": "test.com",
        "stage": "series_a",
        "total_raised_usd": 15_000_000,
        "last_round_date": date.today() - timedelta(days=90),
        "last_round_type": "Series A",
        "last_round_amount_usd": 15_000_000,
        "headcount": 25,
        "headcount_6mo_ago": 20,
        "hq_country": "United States",
        "industry": "SaaS",
        "founder_names": ["Test Founder"],
        "founder_linkedin_urls": [],
        "raw_context": {},
    }
    defaults.update(overrides)
    return Prospect(**defaults)


class TestRecentRaise(unittest.TestCase):
    def test_fires_within_window(self):
        p = make_prospect(last_round_date=date.today() - timedelta(days=90))
        s = detect_recent_raise_60_to_180_days(p)
        self.assertTrue(s.fired)
        self.assertEqual(s.weight, 22)

    def test_does_not_fire_too_recent(self):
        p = make_prospect(last_round_date=date.today() - timedelta(days=30))
        s = detect_recent_raise_60_to_180_days(p)
        self.assertFalse(s.fired)

    def test_does_not_fire_too_old(self):
        p = make_prospect(last_round_date=date.today() - timedelta(days=300))
        s = detect_recent_raise_60_to_180_days(p)
        self.assertFalse(s.fired)


class TestOpenSeniorRole(unittest.TestCase):
    def test_fires_with_stale_role(self):
        p = make_prospect(raw_context={"open_senior_roles": [
            {"title": "VP of Sales", "days_open": 75}
        ]})
        s = detect_open_senior_role_stale(p)
        self.assertTrue(s.fired)

    def test_does_not_fire_with_fresh_role(self):
        p = make_prospect(raw_context={"open_senior_roles": [
            {"title": "VP of Sales", "days_open": 30}
        ]})
        s = detect_open_senior_role_stale(p)
        self.assertFalse(s.fired)


class TestFirstSalesHireChurn(unittest.TestCase):
    def test_fires_on_short_tenure_departure(self):
        p = make_prospect(raw_context={"sales_leader_churn": [
            {"title": "VP Sales", "tenure_months": 5, "departed_days_ago": 60}
        ]})
        s = detect_first_sales_hire_churned(p)
        self.assertTrue(s.fired)

    def test_does_not_fire_on_long_tenure(self):
        p = make_prospect(raw_context={"sales_leader_churn": [
            {"title": "VP Sales", "tenure_months": 14, "departed_days_ago": 60}
        ]})
        s = detect_first_sales_hire_churned(p)
        self.assertFalse(s.fired)


class TestBridgeRound(unittest.TestCase):
    def test_fires_on_bridge(self):
        p = make_prospect(last_round_type="Bridge")
        s = detect_bridge_or_extension_round(p)
        self.assertTrue(s.fired)

    def test_fires_on_extension(self):
        p = make_prospect(last_round_type="Series A Extension")
        s = detect_bridge_or_extension_round(p)
        self.assertTrue(s.fired)

    def test_does_not_fire_on_priced_round(self):
        p = make_prospect(last_round_type="Series A")
        s = detect_bridge_or_extension_round(p)
        self.assertFalse(s.fired)


class TestFounderHelpSeeking(unittest.TestCase):
    def test_fires_on_keyword_match(self):
        p = make_prospect(raw_context={"recent_founder_posts": [
            {"text": "We are struggling with our first GTM hire. Any recs?", "days_ago": 10}
        ]})
        s = detect_founder_help_seeking_content(p)
        self.assertTrue(s.fired)

    def test_does_not_fire_on_old_post(self):
        p = make_prospect(raw_context={"recent_founder_posts": [
            {"text": "Looking for a fractional advisor", "days_ago": 120}
        ]})
        s = detect_founder_help_seeking_content(p)
        self.assertFalse(s.fired)


class TestLaneBDetectors(unittest.TestCase):
    def test_c_level_departure_fires(self):
        p = make_prospect(stage="series_b", raw_context={"executive_departures": [
            {"title": "CRO", "departed_days_ago": 45}
        ]})
        s = detect_c_level_departure_90d(p)
        self.assertTrue(s.fired)

    def test_layoff_fires(self):
        p = make_prospect(stage="series_c", raw_context={"news_events": [
            {"category": "layoff", "headline": "Co lays off 20%", "days_ago": 30}
        ]})
        s = detect_recent_layoff_event(p)
        self.assertTrue(s.fired)

    def test_multiple_senior_roles_fires_at_three(self):
        p = make_prospect(stage="series_b", raw_context={"open_senior_roles": [
            {"title": "VP of Sales", "days_open": 20},
            {"title": "VP of Marketing", "days_open": 25},
            {"title": "Head of Customer Success", "days_open": 18},
        ]})
        s = detect_multiple_senior_roles_open(p)
        self.assertTrue(s.fired)

    def test_multiple_senior_roles_does_not_fire_at_two(self):
        p = make_prospect(stage="series_b", raw_context={"open_senior_roles": [
            {"title": "VP of Sales", "days_open": 20},
            {"title": "VP of Marketing", "days_open": 25},
        ]})
        s = detect_multiple_senior_roles_open(p)
        self.assertFalse(s.fired)


class TestICPFilters(unittest.TestCase):
    def test_series_b_excluded_from_lane_a(self):
        p = make_prospect(stage="series_b", total_raised_usd=70_000_000, headcount=120)
        passes, reason = in_icp(p, "A")
        self.assertFalse(passes)
        self.assertIn("stage", reason)

    def test_series_a_passes_lane_a(self):
        p = make_prospect(stage="series_a", total_raised_usd=15_000_000, headcount=25)
        passes, _ = in_icp(p, "A")
        self.assertTrue(passes)

    def test_overcap_company_excluded(self):
        p = make_prospect(stage="series_d", total_raised_usd=600_000_000, headcount=500)
        passes, reason = in_icp(p, "B")
        self.assertFalse(passes)


class TestScoringAndRouting(unittest.TestCase):
    def test_hot_priority_assigned(self):
        p = make_prospect(
            last_round_date=date.today() - timedelta(days=90),
            last_round_type="Bridge",
            raw_context={
                "open_senior_roles": [{"title": "VP Sales", "days_open": 80}],
                "sales_leader_churn": [{"title": "VP Sales", "tenure_months": 4, "departed_days_ago": 30}],
            }
        )
        result = score_prospect(p, "A", LANE_A_DETECTORS)
        # 22 (raise) + 20 (open role) + 18 (sales churn) + 14 (bridge) = 74
        # HOT threshold is 50.
        self.assertEqual(result.priority, "HOT")
        self.assertGreaterEqual(result.score, 50)

    def test_excluded_when_off_icp(self):
        p = make_prospect(stage="series_c", total_raised_usd=200_000_000, headcount=300)
        result = score_prospect(p, "A", LANE_A_DETECTORS)
        self.assertEqual(result.priority, "EXCLUDED")


class TestEndToEndPipeline(unittest.TestCase):
    def test_fixture_pipeline_runs_both_lanes(self):
        for lane in ("A", "B"):
            scored = run_pipeline(lane=lane, source="fixture")
            self.assertGreater(len(scored), 0)
            # First entry should be highest score
            self.assertGreaterEqual(scored[0].score, scored[-1].score)

    def test_fixture_produces_hot_prospects(self):
        scored_a = run_pipeline(lane="A", source="fixture")
        hot = [sp for sp in scored_a if sp.priority == "HOT"]
        self.assertGreater(len(hot), 0,
            "Fixture data is designed to produce at least one HOT Lane A prospect. "
            "If this fails, either the fixture data or the weights have changed."
        )


if __name__ == "__main__":
    unittest.main()
