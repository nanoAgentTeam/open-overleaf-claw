#!/usr/bin/env python3
"""
Batch runner for E2E evaluation cases.

Usage examples:
  # Run all cases
  python tests/scripts/run_batch.py

  # Run specific cases (substring match on filename)
  python tests/scripts/run_batch.py w03 w05 r01

  # Run only W-series or R-series cases
  python tests/scripts/run_batch.py --filter w
  python tests/scripts/run_batch.py --filter r

  # Skip LLM judge (judge runs by default)
  python tests/scripts/run_batch.py --no-judge

  # Parallel execution (3 concurrent agents)
  python tests/scripts/run_batch.py --workers 3
"""

import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime

import yaml

# Allow importing sibling scripts
sys.path.insert(0, str(Path(__file__).parent))
from run_eval import run_evaluation

# ── helpers ──────────────────────────────────────────────────────────────────

STATUS_ICON = {"completed": "✅", "timeout": "⏱️", "error": "❌"}


def discover_cases(cases_dir: Path, patterns: list[str] | None, filter_prefix: str | None) -> list[Path]:
    """Return sorted list of case YAML paths matching the given filters."""
    all_cases = sorted(cases_dir.glob("*.yaml"))
    if patterns:
        return [c for c in all_cases if any(p.lower() in c.stem.lower() for p in patterns)]
    if filter_prefix:
        return [c for c in all_cases if c.stem.lower().startswith(filter_prefix.lower())]
    return all_cases


# ── core task ─────────────────────────────────────────────────────────────────

async def run_one(
    case_path: Path,
    root: str,
    with_judge: bool,
    semaphore: asyncio.Semaphore,
    batch_timestamp: str | None = None,
) -> dict:
    """Run a single case (and optionally its judge evaluation) under the semaphore."""
    async with semaphore:
        result = await run_evaluation(str(case_path), root, batch_timestamp=batch_timestamp)

        if with_judge and result.get("archive_dir"):
            from judge_eval import JudgeEvaluator  # lazy import (requires litellm)

            with open(case_path, "r", encoding="utf-8") as f:
                case_config = yaml.safe_load(f)

            archive_dir: Path = result["archive_dir"]
            session_id: str = result["session_id"]
            # After archiving, the session lives inside the archive workspace
            session_dir = archive_dir / "workspace" / session_id / ".bot"
            report_path = archive_dir / "evaluation.md"

            judge = JudgeEvaluator()
            await judge.evaluate(session_dir, case_config,
                                 archive_dir=archive_dir, report_path=report_path)
            result["judge_report"] = str(report_path)

        return result


# ── batch orchestrator ────────────────────────────────────────────────────────

async def run_batch(cases: list[Path], root: str, with_judge: bool, workers: int) -> None:
    semaphore = asyncio.Semaphore(workers)
    # All cases in this batch share a single timestamp directory
    batch_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    sep = "=" * 64
    print(f"\n{sep}")
    print(f"  E2E Batch Run — {len(cases)} case(s), {workers} worker(s)"
          + ("  + judge" if with_judge else ""))
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Archive: tests/runs/{batch_timestamp}/")
    print(f"{sep}\n")

    tasks = [run_one(c, root, with_judge, semaphore, batch_timestamp=batch_timestamp) for c in cases]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── summary table ────────────────────────────────────────────────────────
    results = []
    for case_path, res in zip(cases, raw_results):
        if isinstance(res, Exception):
            results.append({
                "case": case_path.stem,
                "status": "error",
                "elapsed_sec": 0.0,
                "error": str(res),
            })
        else:
            results.append(res)

    print(f"\n{sep}")
    print("  SUMMARY")
    print(sep)

    col_case    = 35
    col_mode    = 7
    col_status  = 12
    col_time    = 7

    header = f"  {'Case':<{col_case}} {'Mode':<{col_mode}} {'Status':<{col_status}} {'Time':>{col_time}}"
    print(header)
    print(f"  {'-'*col_case} {'-'*col_mode} {'-'*col_status} {'-'*col_time}")

    counts = {"completed": 0, "timeout": 0, "error": 0}

    for r in results:
        status   = r.get("status", "error")
        icon     = STATUS_ICON.get(status, "❓")
        elapsed  = r.get("elapsed_sec", 0.0)
        case     = r.get("case", r.get("project_id", "?"))
        counts[status] = counts.get(status, 0) + 1

        mode      = r.get("mode", "NORMAL")
        judge_tag = "  [judged]" if r.get("judge_report") else ""
        print(f"  {icon} {case:<{col_case-2}} {mode:<{col_mode}} {status:<{col_status}} {elapsed:>{col_time-1}.1f}s{judge_tag}")

    print(f"\n  Total {len(results)}  |  "
          f"✅ {counts['completed']}  "
          f"⏱️  {counts['timeout']}  "
          f"❌ {counts['error']}")
    print(f"{sep}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch runner for E2E evaluation cases.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "cases", nargs="*",
        help="Case name patterns to run (e.g. w03 w05 r01). Omit to run all.",
    )
    parser.add_argument(
        "--filter", choices=["r", "w"], dest="filter_prefix",
        help="Filter by category: r (research cases) or w (writing cases)",
    )
    parser.add_argument(
        "--no-judge", action="store_true",
        help="Skip LLM judge evaluation (judge runs by default)",
    )
    parser.add_argument(
        "--workers", type=int, default=1, metavar="N",
        help="Number of concurrent cases to run (default: 1 = sequential)",
    )
    parser.add_argument(
        "--root", default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--cases-dir", default="tests/cases",
        help="Directory containing YAML case files (default: tests/cases)",
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()
    cases_dir = (root / args.cases_dir).resolve()

    if not cases_dir.exists():
        print(f"[Batch] Cases directory not found: {cases_dir}")
        sys.exit(1)

    cases = discover_cases(
        cases_dir,
        patterns=args.cases or None,
        filter_prefix=args.filter_prefix,
    )

    if not cases:
        print("[Batch] No matching cases found.")
        sys.exit(0)

    print(f"[Batch] Cases to run ({len(cases)}):")
    for c in cases:
        print(f"  {c.name}")

    with_judge = not args.no_judge
    asyncio.run(run_batch(cases, str(root), with_judge, args.workers))


if __name__ == "__main__":
    main()
