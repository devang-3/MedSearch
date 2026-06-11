"""Oracle rewards and ranking metrics for offline evaluation."""
from __future__ import annotations

from typing import Any


def normalize_name(name: str) -> str:
    return name.strip().lower()


def find_target_rank(ranked: list[dict[str, Any]], target: str) -> int | None:
    """1-based rank of target in combined list, or None if absent."""
    target_key = normalize_name(target)
    for idx, item in enumerate(ranked, start=1):
        if normalize_name(item.get("name", "")) == target_key:
            return idx
    return None


def oracle_reward(
    ranked: list[dict[str, Any]],
    target: str,
    *,
    mode: str = "graded",
) -> float:
    """
    Oracle reward from ranked suggestions vs known correct medicine.

    mode:
      - binary: 1.0 if rank 1 else 0.0
      - graded: 1.0 rank 1, 0.5 top-3, else 0.0
      - mrr: 1/rank or 0.0
    """
    rank = find_target_rank(ranked, target)
    if rank is None:
        return 0.0
    if mode == "mrr":
        return 1.0 / rank
    if mode == "binary":
        return 1.0 if rank == 1 else 0.0
    if rank == 1:
        return 1.0
    if rank <= 3:
        return 0.5
    return 0.0


def evaluate_rankings(
    episodes: list[dict[str, Any]],
) -> dict[str, float]:
    """
    Aggregate metrics from episode records with keys:
      target, ranked (list of dicts with name)
    """
    if not episodes:
        return {
            "count": 0,
            "top1": 0.0,
            "top3": 0.0,
            "mrr": 0.0,
            "mean_reward_graded": 0.0,
        }

    top1 = top3 = mrr = graded = 0.0
    for ep in episodes:
        ranked = ep["ranked"]
        target = ep["target"]
        rank = find_target_rank(ranked, target)
        if rank == 1:
            top1 += 1
        if rank is not None and rank <= 3:
            top3 += 1
        if rank is not None:
            mrr += 1.0 / rank
        graded += oracle_reward(ranked, target, mode="graded")

    n = len(episodes)
    return {
        "count": n,
        "top1": top1 / n,
        "top3": top3 / n,
        "mrr": mrr / n,
        "mean_reward_graded": graded / n,
    }
