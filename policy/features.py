"""Context features for contextual bandit merge policy."""
from __future__ import annotations

import re
from typing import Any

ALGO_KEYS = (
    "prefix",
    "fuzzy_ngram",
    "keyboard_dl",
    "double_metaphone",
    "substring",
)

FEATURE_NAMES = (
    "bias",
    "query_len_norm",
    "has_prefix_hit",
    "prefix_count_norm",
    "min_keyboard_dl_norm",
    "keyboard_count_norm",
    "max_fuzzy_score",
    "metaphone_hit",
    "substring_hit",
    "query_has_digits",
    "query_has_space",
)

FEATURE_DIM = len(FEATURE_NAMES)


def _parse_keyboard_dl(detail: str) -> float | None:
    if not detail.startswith("DL="):
        return None
    part = detail.split()[0]
    try:
        return float(part.replace("DL=", ""))
    except ValueError:
        return None


def _parse_fuzzy_score(detail: str) -> float | None:
    if not detail.startswith("score "):
        return None
    try:
        return float(detail.replace("score ", ""))
    except ValueError:
        return None


def extract_features(query: str, algo_results: dict[str, list[dict[str, Any]]]) -> list[float]:
    """Return fixed-length feature vector for LinUCB."""
    q = query.strip().lower()
    qlen = len(q)

    prefix_items = algo_results.get("prefix", [])
    keyboard_items = algo_results.get("keyboard_dl", [])
    fuzzy_items = algo_results.get("fuzzy_ngram", [])
    metaphone_items = algo_results.get("double_metaphone", [])
    substring_items = algo_results.get("substring", [])

    has_prefix_hit = 1.0 if prefix_items else 0.0
    prefix_count = float(len(prefix_items))

    dl_values = []
    for item in keyboard_items:
        dl = _parse_keyboard_dl(item.get("detail", ""))
        if dl is not None:
            dl_values.append(dl)
    min_dl = min(dl_values) if dl_values else 6.0
    keyboard_count = float(len(keyboard_items))

    fuzzy_scores = []
    for item in fuzzy_items:
        score = _parse_fuzzy_score(item.get("detail", ""))
        if score is not None:
            fuzzy_scores.append(score)
    max_fuzzy = max(fuzzy_scores) if fuzzy_scores else 0.0

    return [
        1.0,
        min(qlen / 20.0, 1.0),
        has_prefix_hit,
        min(prefix_count / 8.0, 1.0),
        min(min_dl / 6.0, 1.0),
        min(keyboard_count / 8.0, 1.0),
        max_fuzzy,
        1.0 if metaphone_items else 0.0,
        1.0 if substring_items else 0.0,
        1.0 if re.search(r"\d", q) else 0.0,
        1.0 if " " in q else 0.0,
    ]


def features_as_dict(query: str, algo_results: dict[str, list[dict]]) -> dict[str, float]:
    values = extract_features(query, algo_results)
    return dict(zip(FEATURE_NAMES, values))
