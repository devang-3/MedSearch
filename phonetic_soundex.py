import csv
import sys
from collections import defaultdict
from paths import DATASET_PATH


def normalize(text):
    return text.lower().strip()


def brand_word(name):
    """First alphabetic token used for phonetic encoding."""
    for word in normalize(name).split():
        if word and word[0].isalpha():
            return word.upper()
    return ""


def soundex(word):
    """American Soundex: one letter + three digits (e.g. Robert -> R163)."""
    word = "".join(c for c in word.upper() if c.isalpha())
    if not word:
        return ""

    def digit(c):
        if c in "BFPV":
            return "1"
        if c in "CGJKQSXZ":
            return "2"
        if c in "DT":
            return "3"
        if c in "L":
            return "4"
        if c in "MN":
            return "5"
        if c in "R":
            return "6"
        return ""

    code = word[0]
    prev = digit(word[0])

    for ch in word[1:]:
        if ch in "AEIOUYHW":
            prev = ""
            continue
        d = digit(ch)
        if d and d != prev:
            code += d
        prev = d if d else prev

    return (code + "000")[:4]


def brand_match_rank(query, name):
    """Lower is better when sharing a Soundex bucket."""
    bq = brand_word(query).lower()
    bn = brand_word(name).lower()
    if not bq or not bn:
        return 3
    if bq == bn:
        return 0
    if bn.startswith(bq) or bq.startswith(bn):
        return 1
    return 2


def soundex_neighbors(code):
    """Codes at Hamming distance 1 (looser phonetic match)."""
    if len(code) != 4:
        return {code} if code else set()

    neighbors = {code}
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if ch != code[0]:
            neighbors.add(ch + code[1:])
    for i in range(1, 4):
        for d in "012345678":
            if d != code[i]:
                neighbors.add(code[:i] + d + code[i + 1 :])
    return neighbors


class SoundexIndex:
    """Inverted index: Soundex code -> medicine names (brand token encoded)."""

    def __init__(self, fuzzy_neighbors=False):
        self.fuzzy_neighbors = fuzzy_neighbors
        self.inverted = defaultdict(list)

    def build(self, names):
        self.inverted = defaultdict(list)
        for name in names:
            brand = brand_word(name)
            if not brand:
                continue
            code = soundex(brand)
            self.inverted[code].append(name)

    def search(self, query, limit=25):
        brand = brand_word(query)
        if not brand:
            return []

        code = soundex(brand)
        codes = soundex_neighbors(code) if self.fuzzy_neighbors else {code}

        hits = []
        for c in codes:
            hits.extend((c, name) for name in self.inverted.get(c, ()))

        hits.sort(
            key=lambda x: (x[0] != code, brand_match_rank(query, x[1]), len(normalize(x[1])), x[1])
        )

        seen = set()
        results = []
        for c, name in hits:
            if name in seen:
                continue
            seen.add(name)
            results.append((c, name))
            if len(results) >= limit:
                break
        return results


def load_medicines_from_csv(path):
    names = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if name:
                names.append(name)
    return names


def build_index(names, fuzzy_neighbors=False):
    index = SoundexIndex(fuzzy_neighbors=fuzzy_neighbors)
    index.build(names)
    return index


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    names = load_medicines_from_csv(DATASET_PATH)
    print(f"Loaded {len(names):,} medicine names. Building Soundex index...")

    index = build_index(names)
    codes = len(index.inverted)
    print(f"Soundex index ready ({codes:,} codes). Type a query; empty line or 'quit' to exit.\n")

    while True:
        try:
            query = input("Query> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query or query.lower() in ("quit", "exit", "q"):
            break

        brand = brand_word(query)
        code = soundex(brand) if brand else ""
        results = index.search(query, limit=25)
        if not results:
            print(f"  No Soundex matches for code [{code}].\n")
            continue

        print(f"  Soundex({brand}) = {code} — {len(results)} match(es):")
        for i, (match_code, name) in enumerate(results, 1):
            tag = "" if match_code == code else "~"
            print(f"    {i:2}. [{match_code}{tag}] {name}")
        print()


if __name__ == "__main__":
    main()
