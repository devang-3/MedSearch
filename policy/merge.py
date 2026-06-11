"""Merge per-algorithm results using fixed order or LinUCB policy."""
from __future__ import annotations

from typing import Any

from policy.bandit import LinUCBPolicy
from policy.features import extract_features
from policy.rank import ARM_NAMES, merge_candidates

MERGE_MODES = ("auto", "fixed", "linucb", "balanced")


def fixed_merge(
    algo_results: dict[str, list[dict[str, Any]]],
    limit: int,
) -> list[dict[str, Any]]:
    """Legacy priority merge: prefix -> fuzzy -> keyboard -> metaphone -> substring."""
    order = [
        "prefix",
        "fuzzy_ngram",
        "keyboard_dl",
        "double_metaphone",
        "substring",
    ]
    labels = {
        "prefix": "Prefix",
        "fuzzy_ngram": "Fuzzy n-gram",
        "keyboard_dl": "Keyboard DL",
        "double_metaphone": "Double Metaphone",
        "substring": "Substring (trigram)",
    }
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in order:
        for item in algo_results.get(key, []):
            name = item.get("name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            combined.append(
                {
                    "name": name,
                    "detail": item.get("detail", ""),
                    "source": labels[key],
                }
            )
            if len(combined) >= limit:
                return combined
    return combined


def rank_with_policy(
    query: str,
    algo_results: dict[str, list[dict[str, Any]]],
    *,
    mode: str = "fixed",
    bandit: LinUCBPolicy | None = None,
    arm: int | str | None = None,
    explore: bool = False,
    combined_limit: int = 10,
    include_features: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Rank combined suggestions.

    mode: fixed | linucb | balanced | arm
    """
    meta: dict[str, Any] = {"mode": mode}

    if mode == "fixed":
        combined = fixed_merge(algo_results, combined_limit)
        meta["arm_name"] = "fixed"
        return combined, meta

    features = extract_features(query, algo_results)
    if include_features:
        meta["features"] = features

    if mode == "linucb":
        if bandit is None:
            raise ValueError("bandit required for linucb mode")
        chosen_arm = bandit.select(features, explore=explore)
        meta["arm"] = chosen_arm
        meta["arm_name"] = ARM_NAMES[chosen_arm]
    elif mode == "arm":
        chosen_arm = arm if arm is not None else "balanced"
        meta["arm"] = chosen_arm
        meta["arm_name"] = (
            ARM_NAMES[chosen_arm] if isinstance(chosen_arm, int) else str(chosen_arm)
        )
    else:
        chosen_arm = "balanced"
        meta["arm_name"] = "balanced"

    combined, arm_index, arm_name = merge_candidates(
        query,
        algo_results,
        chosen_arm,
        limit=combined_limit,
    )
    meta["arm"] = arm_index
    meta["arm_name"] = arm_name
    return combined, meta


def resolve_merge_mode(requested: str, *, policy_available: bool) -> str:
    """Map auto/fixed/linucb to concrete merge mode."""
    mode = (requested or "auto").strip().lower()
    if mode == "auto":
        return "linucb" if policy_available else "fixed"
    if mode not in MERGE_MODES:
        return "linucb" if policy_available else "fixed"
    if mode == "linucb" and not policy_available:
        return "fixed"
    return mode
