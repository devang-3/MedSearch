#!/usr/bin/env python3
"""
Auto-generate typo benchmark from medicine CSV.

Usage:
    python eval/build_typo_benchmark.py
    python eval/build_typo_benchmark.py --limit 5000 --output eval/typo_benchmark.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from key import KEYBOARD_NEIGHBORS, brand_word, damerau_levenshtein
from paths import BENCHMARK_PATH, DATASET_PATH

# Well-known medicines — good typo / phonetic / prefix diversity.
SEED_MEDICINES = [
    "Augmentin 625 Duo Tablet",
    "Azithral 500 Tablet",
    "Crocin Advance Tablet",
    "Dolo 650 Tablet",
    "Allegra 120mg Tablet",
    "Combiflam Tablet",
    "Pan 40 Tablet",
    "Telma 40 Tablet",
    "Metformin Hydrochloride 500mg Tablet",
    "Atorvastatin 10mg Tablet",
    "Pantoprazole 40mg Tablet",
    "Montelukast 10mg Tablet",
    "Cetirizine Tablet",
    "Amoxicillin 500mg Capsule",
    "Ibuprofen 400mg Tablet",
    "Paracetamol 650mg Tablet",
    "Ascoril LS Syrup",
    "Benadryl Syrup",
    "Volini Gel",
    "Betadine Solution",
]

TYPO_TYPES = (
    "delete",
    "swap",
    "keyboard",
    "drop_vowel",
    "duplicate",
)


def load_medicine_names(path: Path, max_names: int | None = None) -> list[str]:
    names: list[str] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            if name:
                names.append(name)
                if max_names and len(names) >= max_names:
                    break
    return names


def build_brand_index(names: list[str]) -> dict[str, list[str]]:
    """Map brand token -> full medicine names."""
    index: dict[str, list[str]] = {}
    for name in names:
        token = brand_word(name)
        if not token or len(token) < 3:
            continue
        index.setdefault(token, []).append(name)
    return index


def typo_delete(word: str, rng: random.Random) -> str | None:
    if len(word) < 4:
        return None
    i = rng.randrange(len(word))
    return word[:i] + word[i + 1 :]


def typo_swap(word: str, rng: random.Random) -> str | None:
    if len(word) < 3:
        return None
    i = rng.randrange(len(word) - 1)
    chars = list(word)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def typo_keyboard(word: str, rng: random.Random) -> str | None:
    letters = [i for i, ch in enumerate(word) if ch.isalpha()]
    if not letters:
        return None
    i = rng.choice(letters)
    ch = word[i].lower()
    neighbors = list(KEYBOARD_NEIGHBORS.get(ch, ()))
    if not neighbors:
        return None
    rep = rng.choice(neighbors)
    if word[i].isupper():
        rep = rep.upper()
    return word[:i] + rep + word[i + 1 :]


def typo_drop_vowel(word: str, rng: random.Random) -> str | None:
    vowel_idx = [i for i, ch in enumerate(word.lower()) if ch in "aeiou"]
    if not vowel_idx:
        return None
    i = rng.choice(vowel_idx)
    return word[:i] + word[i + 1 :]


def typo_duplicate(word: str, rng: random.Random) -> str | None:
    if len(word) < 3:
        return None
    i = rng.randrange(len(word))
    return word[: i + 1] + word[i] + word[i + 1 :]


def generate_typo(word: str, typo_type: str, rng: random.Random) -> str | None:
    generators = {
        "delete": typo_delete,
        "swap": typo_swap,
        "keyboard": typo_keyboard,
        "drop_vowel": typo_drop_vowel,
        "duplicate": typo_duplicate,
    }
    fn = generators.get(typo_type)
    if fn is None:
        return None
    typo = fn(word, rng)
    if typo and typo != word and len(typo) >= 3:
        return typo
    return None


def build_brand_buckets(all_brands: list[str]) -> dict[tuple[str, int], list[str]]:
    """Group brands by (first char, length) for fast ambiguity checks."""
    buckets: dict[tuple[str, int], list[str]] = {}
    for brand in all_brands:
        if not brand:
            continue
        key = (brand[0], len(brand))
        buckets.setdefault(key, []).append(brand)
    return buckets


def is_ambiguous(
    typo: str,
    target_brand: str,
    brand_buckets: dict[tuple[str, int], list[str]],
    max_dist: int = 2,
) -> bool:
    """Drop typo if another brand is equally or closer in edit distance."""
    target_dl = damerau_levenshtein(typo, target_brand, max_dist=max_dist + 1)
    if target_dl > max_dist:
        return True

    typo_len = len(typo)
    first = target_brand[0] if target_brand else ""
    for length in range(typo_len - max_dist - 1, typo_len + max_dist + 2):
        for other in brand_buckets.get((first, length), ()):
            if other == target_brand:
                continue
            other_dl = damerau_levenshtein(typo, other, max_dist=max_dist + 1)
            if other_dl < target_dl:
                return True
            if other_dl == target_dl and other < target_brand:
                return True
    return False


def pick_canonical_target(brand: str, names: list[str]) -> str:
    """Prefer seed / shortest name for a brand token."""
    return sorted(names, key=lambda n: (len(n), n.lower()))[0]


def build_benchmark(
    names: list[str],
    *,
    seed_medicines: list[str],
    per_medicine: int = 8,
    rng: random.Random,
) -> list[dict]:
    brand_index = build_brand_index(names)
    all_brands = sorted(brand_index.keys())
    brand_buckets = build_brand_buckets(all_brands)

    targets: list[str] = []
    seen_targets: set[str] = set()
    for med in seed_medicines:
        if med in names and med not in seen_targets:
            targets.append(med)
            seen_targets.add(med)

    for brand, meds in brand_index.items():
        if len(targets) >= 200:
            break
        canonical = pick_canonical_target(brand, meds)
        if canonical not in seen_targets:
            targets.append(canonical)
            seen_targets.add(canonical)

    pairs: list[dict] = []
    seen_queries: set[str] = set()

    for target in targets:
        brand = brand_word(target)
        if not brand or len(brand) < 4:
            continue

        attempts = 0
        added = 0
        while added < per_medicine and attempts < per_medicine * 6:
            attempts += 1
            typo_type = rng.choice(TYPO_TYPES)
            typo = generate_typo(brand, typo_type, rng)
            if not typo:
                continue
            if typo in seen_queries:
                continue
            if is_ambiguous(typo, brand, brand_buckets):
                continue

            seen_queries.add(typo)
            pairs.append(
                {
                    "query": typo,
                    "target": target,
                    "brand": brand,
                    "typo_type": typo_type,
                }
            )
            added += 1

    return pairs


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build oracle typo benchmark")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--output", type=Path, default=BENCHMARK_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max CSV rows (0 = all)")
    parser.add_argument("--per-medicine", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)
    max_names = args.limit if args.limit > 0 else None
    names = load_medicine_names(args.dataset, max_names=max_names)
    print(f"Loaded {len(names):,} medicine names.", flush=True)

    pairs = build_benchmark(
        names,
        seed_medicines=SEED_MEDICINES,
        per_medicine=args.per_medicine,
        rng=rng,
    )
    write_jsonl(args.output, pairs)
    print(f"Wrote {len(pairs):,} benchmark pairs -> {args.output}")

    by_type: dict[str, int] = {}
    for p in pairs:
        by_type[p["typo_type"]] = by_type.get(p["typo_type"], 0) + 1
    print("By typo type:", dict(sorted(by_type.items())))


if __name__ == "__main__":
    main()
