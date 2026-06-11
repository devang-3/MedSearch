"""Run search matchers and merge policy for offline eval."""
from __future__ import annotations

from typing import Any

from policy.bandit import LinUCBPolicy
from policy.merge import rank_with_policy as _rank_with_mode
from search_engines import SearchEngines


def search_algorithms_sync(
    engines: SearchEngines,
    query: str,
    per_algo: int = 15,
) -> dict[str, list[dict[str, Any]]]:
    """Run all matchers synchronously (faster for tight training loops)."""
    q = query.strip()
    if not q:
        return {k: [] for k in (
            "prefix", "fuzzy_ngram", "keyboard_dl", "double_metaphone", "substring"
        )}

    return {
        "prefix": engines._search_prefix(q, per_algo),
        "fuzzy_ngram": engines._search_fuzzy(q, per_algo),
        "keyboard_dl": engines._search_keyboard(q, per_algo),
        "double_metaphone": engines._search_dmetaphone(q, per_algo),
        "substring": engines._search_substring(q, per_algo),
    }


def rank_with_policy(
    query: str,
    algo_results: dict[str, list[dict[str, Any]]],
    *,
    policy: str = "fixed",
    bandit: LinUCBPolicy | None = None,
    arm: int | str | None = None,
    explore: bool = False,
    combined_limit: int = 10,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Eval wrapper: policy= fixed | linucb | balanced | arm."""
    if policy == "fixed":
        mode = "fixed"
    elif policy == "linucb":
        mode = "linucb"
    elif policy == "arm":
        mode = "arm"
    else:
        mode = "balanced"

    combined, meta = _rank_with_mode(
        query,
        algo_results,
        mode=mode,
        bandit=bandit,
        arm=arm,
        explore=explore,
        combined_limit=combined_limit,
    )
    meta["policy"] = policy
    return combined, meta
