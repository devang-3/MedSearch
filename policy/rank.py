"""Weighted merge of per-algorithm candidate lists."""
from __future__ import annotations

from typing import Any

from policy.features import ALGO_KEYS

ARM_NAMES = (
    "prefix_boost",
    "keyboard_boost",
    "metaphone_boost",
    "fuzzy_boost",
    "balanced",
)

# Weights per algo key for each arm preset.
ARM_WEIGHTS: list[list[float]] = [
    [3.0, 0.5, 0.5, 0.5, 0.5],  # prefix_boost
    [0.5, 0.5, 3.0, 0.5, 0.5],  # keyboard_boost
    [0.5, 0.5, 0.5, 3.0, 0.5],  # metaphone_boost
    [0.5, 3.0, 0.5, 0.5, 0.5],  # fuzzy_boost
    [1.0, 1.0, 1.0, 1.0, 1.0],  # balanced
]

SOURCE_LABELS = {
    "prefix": "Prefix",
    "fuzzy_ngram": "Fuzzy n-gram",
    "keyboard_dl": "Keyboard DL",
    "double_metaphone": "Double Metaphone",
    "substring": "Substring (trigram)",
}


def _brand_word(text: str) -> str:
    for word in text.lower().split():
        if word and word[0].isalpha():
            return word
    return ""


def _strong_prefix_match(query: str, name: str) -> bool:
    """True when query is a clear prefix of the medicine brand token."""
    q = query.strip().lower()
    if len(q) < 2:
        return False
    brand = _brand_word(name)
    if not brand:
        return False
    if brand.startswith(q):
        return True
    if q.startswith(brand) and len(brand) >= 3:
        return True
    return False


def merge_candidates(
    query: str,
    algo_results: dict[str, list[dict[str, Any]]],
    arm: int | str = "balanced",
    *,
    limit: int = 10,
    pin_prefix: bool = True,
) -> tuple[list[dict[str, Any]], int, str]:
    """
    Score candidates by weighted reciprocal rank across algorithms.

    Returns (combined, arm_index, arm_name).
    """
    if isinstance(arm, str):
        if arm not in ARM_NAMES:
            raise ValueError(f"Unknown arm: {arm}")
        arm_index = ARM_NAMES.index(arm)
    else:
        arm_index = int(arm) % len(ARM_NAMES)

    weights = ARM_WEIGHTS[arm_index]
    scores: dict[str, float] = {}
    best_source: dict[str, str] = {}
    best_detail: dict[str, str] = {}

    for algo_idx, algo_key in enumerate(ALGO_KEYS):
        weight = weights[algo_idx]
        if weight <= 0:
            continue
        for rank, item in enumerate(algo_results.get(algo_key, [])):
            name = item.get("name", "")
            if not name:
                continue
            contribution = weight / (rank + 1)
            scores[name] = scores.get(name, 0.0) + contribution
            if name not in best_source or contribution > 0:
                best_source[name] = SOURCE_LABELS[algo_key]
                best_detail[name] = item.get("detail", "")

    ranked_names = sorted(scores.keys(), key=lambda n: (-scores[n], n.lower()))

    if pin_prefix:
        pinned = [n for n in ranked_names if _strong_prefix_match(query, n)]
        if pinned:
            pinned_set = set(pinned)
            ranked_names = pinned + [n for n in ranked_names if n not in pinned_set]

    combined: list[dict[str, Any]] = []
    for name in ranked_names[:limit]:
        combined.append(
            {
                "name": name,
                "detail": best_detail.get(name, ""),
                "source": best_source.get(name, ""),
                "score": round(scores[name], 4),
            }
        )

    return combined, arm_index, ARM_NAMES[arm_index]
