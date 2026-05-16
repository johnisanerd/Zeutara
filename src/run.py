"""
Zeutara Signal Detection Engine - CLI

Usage:
    python -m src.run --lane A
    python -m src.run --lane B
    python -m src.run --lane both --out-dir ./output

Default: runs both lanes against bundled fixture data, prints a console
summary, writes ranked CSV + JSON to ./output/.

This is the single command the reviewer runs to verify the prototype.
"""

import argparse
import sys
from pathlib import Path

from .pipeline import run_pipeline, write_csv, write_json, summarize


def format_console_summary(lane: str, summary: dict, sample_lines: list[str]) -> str:
    """Human-readable summary block for stdout."""
    bp = summary["by_priority"]
    lines = [
        "",
        "=" * 72,
        f"  LANE {lane}: {summary['total_prospects']} prospects evaluated",
        "=" * 72,
        f"  HOT     {bp['HOT']:>3}  (partner reviews within 24h)",
        f"  WARM    {bp['WARM']:>3}  (analyst processes within 72h)",
        f"  COOL    {bp['COOL']:>3}  (quarterly nurture)",
        f"  EXCLUDED{bp['EXCLUDED']:>3}  (off-ICP, no signals)",
        "",
        f"  Actionable (HOT + WARM): {summary['actionable_count']}",
        f"  Avg score of actionable: {summary['avg_score_actionable']}/100",
        "",
        "  Top 3 by score:",
    ]
    for r in summary["top_3_companies"]:
        lines.append(f"    [{r['priority']:<5}] {r['score']:>3}/100  {r['name']}")
    lines.append("")
    lines.append("  Sample of highest-scoring prospect's signals:")
    lines.extend([f"    {ln}" for ln in sample_lines])
    lines.append("=" * 72)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Zeutara Signal Detection Engine: rank venture-backed "
                    "companies by likelihood of being 'in market' for "
                    "execution-architecture consulting today."
    )
    parser.add_argument(
        "--lane", choices=["A", "B", "both"], default="both",
        help="Which buyer lane to score against. A = pre-seed/seed/Series A "
             "founders with execution gaps. B = growth-stage operators at "
             "structural inflection. Default: both."
    )
    parser.add_argument(
        "--source", choices=["fixture", "live"], default="fixture",
        help="Data source. fixture = bundled demo data (no API keys). "
             "live = call PredictLeads/Crunchbase/Apify (not implemented "
             "in this prototype). Default: fixture."
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("./output"),
        help="Directory for ranked CSV/JSON output. Default: ./output"
    )
    args = parser.parse_args()

    lanes = ["A", "B"] if args.lane == "both" else [args.lane]

    for lane in lanes:
        scored = run_pipeline(lane=lane, source=args.source)
        summary = summarize(scored)

        # Show the top prospect's fired signals as a "show your work" sample.
        sample_lines = []
        if scored and scored[0].priority != "EXCLUDED":
            top = scored[0]
            sample_lines.append(f"  {top.prospect.company_name} (score {top.score}, lane {top.lane}):")
            for s in sorted(top.signals, key=lambda x: x.weight, reverse=True):
                if s.fired:
                    sample_lines.append(f"    + {s.weight:>2}  {s.signal_id}")
                    sample_lines.append(f"          {s.evidence}")

        print(format_console_summary(lane, summary, sample_lines))

        out_csv = args.out_dir / f"ranked_lane_{lane}.csv"
        out_json = args.out_dir / f"ranked_lane_{lane}.json"
        write_csv(scored, out_csv)
        write_json(scored, out_json)
        print(f"\n  Wrote: {out_csv}")
        print(f"  Wrote: {out_json}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
