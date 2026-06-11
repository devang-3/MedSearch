#!/usr/bin/env python3
"""
Automated LinUCB training loop with oracle rewards.

Usage:
    # Step 1 — build benchmark (fast dev subset)
    python eval/build_typo_benchmark.py --limit 5000

    # Step 2 — baseline (know X%)
    python eval/run_baseline.py --limit 5000 --policy fixed

    # Step 3 — train + eval
    python eval/train_bandit_loop.py --limit 5000 --episodes 1500

    # Step 4 — eval trained policy
    python eval/run_baseline.py --limit 5000 --policy linucb
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.oracle import evaluate_rankings, oracle_reward
from eval.runner import rank_with_policy, search_algorithms_sync
from eval.run_baseline import load_benchmark, run_eval
from paths import BENCHMARK_PATH, EVAL_RESULTS_PATH, POLICY_STATE_PATH
from policy.bandit import LinUCBPolicy, load_policy, save_policy
from policy.features import extract_features
from search_engines import SearchEngines


def train_loop(
    engines: SearchEngines,
    benchmark: list[dict],
    policy: LinUCBPolicy,
    *,
    episodes: int,
    per_algo: int = 15,
    combined_limit: int = 10,
    reward_mode: str = "graded",
    log_every: int = 200,
    rng: random.Random,
) -> list[dict]:
    """Shuffle-sample training episodes with oracle reward updates."""
    history: list[dict] = []

    for ep in range(1, episodes + 1):
        row = rng.choice(benchmark)
        query = row["query"]
        target = row["target"]

        algo_results = search_algorithms_sync(engines, query, per_algo=per_algo)
        features = extract_features(query, algo_results)
        arm = policy.select(features, explore=True)
        ranked, meta = rank_with_policy(
            query,
            algo_results,
            policy="arm",
            arm=arm,
            combined_limit=combined_limit,
        )
        reward = oracle_reward(ranked, target, mode=reward_mode)
        policy.update(features, arm, reward)

        if ep % log_every == 0 or ep == 1:
            rank = next(
                (
                    i + 1
                    for i, item in enumerate(ranked)
                    if item.get("name", "").lower() == target.lower()
                ),
                None,
            )
            history.append(
                {
                    "episode": ep,
                    "reward": reward,
                    "arm": meta.get("arm_name"),
                    "target_rank": rank,
                    "query": query,
                    "target": target,
                }
            )
            print(
                f"  ep {ep:5d}  reward={reward:.1f}  arm={meta.get('arm_name')}  "
                f"rank={rank or '-'}  q={query!r}",
                flush=True,
            )

    return history


def main() -> None:
    parser = argparse.ArgumentParser(description="Train LinUCB on typo benchmark")
    parser.add_argument("--benchmark", type=Path, default=BENCHMARK_PATH)
    parser.add_argument("--state", type=Path, default=POLICY_STATE_PATH)
    parser.add_argument("--output", type=Path, default=EVAL_RESULTS_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max medicines to index")
    parser.add_argument("--episodes", type=int, default=2000)
    parser.add_argument("--per-algo", type=int, default=15)
    parser.add_argument("--combined", type=int, default=10)
    parser.add_argument("--reward-mode", choices=("graded", "binary", "mrr"), default="graded")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true", help="Load existing policy state")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Train from scratch (ignore existing policy/state.json)",
    )
    parser.add_argument("--log-every", type=int, default=200)
    args = parser.parse_args()

    if not args.benchmark.exists():
        print(f"Benchmark not found: {args.benchmark}", file=sys.stderr)
        print("Run: python eval/build_typo_benchmark.py", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)
    benchmark = load_benchmark(args.benchmark)
    print(f"Benchmark: {len(benchmark):,} pairs")

    names = None
    if args.limit > 0:
        from prefix import load_medicines_from_csv
        from paths import DATASET_PATH

        names = load_medicines_from_csv(DATASET_PATH)[: args.limit]
        print(f"Indexing first {args.limit:,} medicines.")

    print("Building search indexes...")
    t_build = time.perf_counter()
    engines = SearchEngines.build(names)
    print(f"Index build: {time.perf_counter() - t_build:.1f}s\n")

    print("=== Before training (fixed merge) ===")
    before = run_eval(
        engines,
        benchmark,
        policy="fixed",
        per_algo=args.per_algo,
        combined_limit=args.combined,
    )
    bm = before["metrics"]
    print(
        f"Fixed  top-1={bm['top1_pct']}%  top-3={bm['top3_pct']}%  "
        f"MRR={bm['mrr_pct']}%\n"
    )

    if args.fresh:
        policy = LinUCBPolicy()
        print("Training fresh LinUCB policy (ignoring saved state).\n")
    elif args.resume and args.state.exists():
        policy = load_policy(args.state)
        print(f"Resumed policy from {args.state} ({policy.total_updates} prior updates)\n")
    else:
        policy = LinUCBPolicy()

    print(f"=== Training LinUCB ({args.episodes} episodes) ===")
    t_train = time.perf_counter()
    train_history = train_loop(
        engines,
        benchmark,
        policy,
        episodes=args.episodes,
        per_algo=args.per_algo,
        combined_limit=args.combined,
        reward_mode=args.reward_mode,
        log_every=args.log_every,
        rng=rng,
    )
    train_sec = time.perf_counter() - t_train
    save_policy(policy, args.state)
    print(f"\nSaved policy -> {args.state} ({policy.total_updates} total updates)")
    print(f"Training time: {train_sec:.1f}s\n")

    print("=== After training (LinUCB, greedy) ===")
    after = run_eval(
        engines,
        benchmark,
        policy="linucb",
        state_path=args.state,
        per_algo=args.per_algo,
        combined_limit=args.combined,
        explore=False,
    )
    am = after["metrics"]
    print(
        f"LinUCB top-1={am['top1_pct']}%  top-3={am['top3_pct']}%  "
        f"MRR={am['mrr_pct']}%\n"
    )

    delta_top1 = round(am["top1_pct"] - bm["top1_pct"], 1)
    summary = {
        "benchmark": str(args.benchmark),
        "episodes": args.episodes,
        "reward_mode": args.reward_mode,
        "before_fixed": bm,
        "after_linucb": am,
        "improvement": {
            "top1_pct_points": delta_top1,
            "top3_pct_points": round(am["top3_pct"] - bm["top3_pct"], 1),
            "mrr_pct_points": round(am["mrr_pct"] - bm["mrr_pct"], 1),
        },
        "policy_state": str(args.state),
        "total_updates": policy.total_updates,
        "train_sec": round(train_sec, 1),
        "train_samples": train_history[-5:],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("=== Summary ===")
    print(f"Top-1:  {bm['top1_pct']}% -> {am['top1_pct']}%  ({delta_top1:+.1f} pts)")
    print(f"Results -> {args.output}")


if __name__ == "__main__":
    main()
