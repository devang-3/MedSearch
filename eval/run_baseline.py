#!/usr/bin/env python3
"""
Evaluate fixed merge vs LinUCB policy on typo benchmark.

Usage:
    python eval/build_typo_benchmark.py --limit 5000
    python eval/run_baseline.py --limit 5000
    python eval/run_baseline.py --policy linucb --state policy/state.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.oracle import evaluate_rankings, oracle_reward
from eval.runner import rank_with_policy, search_algorithms_sync
from paths import BENCHMARK_PATH, EVAL_RESULTS_PATH, POLICY_STATE_PATH
from policy.bandit import load_policy
from search_engines import SearchEngines


def load_benchmark(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_eval(
    engines: SearchEngines,
    benchmark: list[dict],
    *,
    policy: str,
    state_path: Path | None = None,
    per_algo: int = 15,
    combined_limit: int = 10,
    explore: bool = False,
) -> dict:
    bandit = load_policy(state_path) if policy == "linucb" else None
    episodes: list[dict] = []
    arm_counts: dict[str, int] = {}

    t0 = time.perf_counter()
    for row in benchmark:
        query = row["query"]
        target = row["target"]
        algo_results = search_algorithms_sync(engines, query, per_algo=per_algo)
        ranked, meta = rank_with_policy(
            query,
            algo_results,
            policy=policy,
            bandit=bandit,
            explore=explore,
            combined_limit=combined_limit,
        )
        reward = oracle_reward(ranked, target, mode="graded")
        arm_name = str(meta.get("arm_name", policy))
        arm_counts[arm_name] = arm_counts.get(arm_name, 0) + 1
        episodes.append(
            {
                "query": query,
                "target": target,
                "ranked": ranked,
                "reward": reward,
                "arm": meta.get("arm"),
                "arm_name": arm_name,
            }
        )

    elapsed = time.perf_counter() - t0
    metrics = evaluate_rankings(episodes)
    metrics["policy"] = policy
    metrics["elapsed_sec"] = round(elapsed, 2)
    metrics["arm_counts"] = arm_counts
    metrics["top1_pct"] = round(metrics["top1"] * 100, 1)
    metrics["top3_pct"] = round(metrics["top3"] * 100, 1)
    metrics["mrr_pct"] = round(metrics["mrr"] * 100, 1)
    return {"metrics": metrics, "episodes": episodes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate merge policy on typo benchmark")
    parser.add_argument("--benchmark", type=Path, default=BENCHMARK_PATH)
    parser.add_argument("--policy", choices=("fixed", "balanced", "linucb"), default="fixed")
    parser.add_argument("--state", type=Path, default=POLICY_STATE_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max medicines to index (0 = all)")
    parser.add_argument("--per-algo", type=int, default=15)
    parser.add_argument("--combined", type=int, default=10)
    parser.add_argument("--output", type=Path, default=EVAL_RESULTS_PATH)
    parser.add_argument("--explore", action="store_true")
    args = parser.parse_args()

    if not args.benchmark.exists():
        print(f"Benchmark not found: {args.benchmark}", file=sys.stderr)
        print("Run: python eval/build_typo_benchmark.py", file=sys.stderr)
        sys.exit(1)

    benchmark = load_benchmark(args.benchmark)
    print(f"Benchmark: {len(benchmark):,} pairs")

    names = None
    if args.limit > 0:
        from prefix import load_medicines_from_csv
        from paths import DATASET_PATH

        names = load_medicines_from_csv(DATASET_PATH)[: args.limit]
        print(f"Indexing first {args.limit:,} medicines only.")

    print("Building search indexes...")
    engines = SearchEngines.build(names)

    result = run_eval(
        engines,
        benchmark,
        policy=args.policy,
        state_path=args.state if args.policy == "linucb" else None,
        per_algo=args.per_algo,
        combined_limit=args.combined,
        explore=args.explore,
    )
    metrics = result["metrics"]

    print(f"\nPolicy: {metrics['policy']}")
    print(f"Pairs:  {metrics['count']}")
    print(f"Top-1:  {metrics['top1_pct']}%")
    print(f"Top-3:  {metrics['top3_pct']}%")
    print(f"MRR:    {metrics['mrr_pct']}%")
    print(f"Graded reward: {metrics['mean_reward_graded']:.3f}")
    print(f"Time:   {metrics['elapsed_sec']}s")
    if metrics.get("arm_counts"):
        print("Arm usage:", metrics["arm_counts"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": str(args.benchmark),
        "policy": args.policy,
        "metrics": metrics,
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
