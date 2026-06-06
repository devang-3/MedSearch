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


def metaphone(word):
    """
    Metaphone phonetic encoding (Lawrence Philips).
    Variable-length code (up to ~4 significant phonetic chars).
    """
    word = "".join(c for c in word.upper() if c.isalpha())
    if not word:
        return ""

    # Drop leading silent consonants / special starts
    if word[:2] in ("KN", "GN", "PN", "WR"):
        word = word[1:]
    elif word[:2] == "AE":
        word = word[1:]
    elif word[0] == "X":
        word = "S" + word[1:]

    n = len(word)
    i = 0
    meta = []

    def at(pos, *parts):
        for part in parts:
            end = pos + len(part)
            if word[pos:end] == part:
                return True
        return False

    def get(pos):
        return word[pos] if 0 <= pos < n else ""

    while i < n:
        if len(meta) >= 4:
            break

        ch = get(i)
        prev = get(i - 1)
        nxt = get(i + 1)
        nxt2 = get(i + 2)

        if ch in "AEIOU":
            if i == 0:
                meta.append(ch)
        elif ch == "B":
            if not (prev == "M" and get(i + 1) == ""):
                meta.append("B")
        elif ch == "C":
            if at(i, "CIA"):
                meta.append("X")
            elif nxt == "H":
                if not (prev == "S" and nxt2 in "IO"):
                    meta.append("X")
            elif nxt in "EIY":
                meta.append("S")
            else:
                meta.append("K")
        elif ch == "D":
            if nxt == "G" and nxt2 in "EIY":
                meta.append("J")
                i += 1
            else:
                meta.append("T")
        elif ch == "F":
            meta.append("F")
        elif ch == "G":
            if nxt == "H":
                if not (nxt2 in "EIY" or (i + 3 < n and get(i + 3) in "EIY")):
                    meta.append("K")
                i += 1
            elif nxt in "EIY":
                meta.append("J")
            elif not (nxt == "N" and get(i + 2) == "E" and get(i + 3) == "D"):
                if nxt == "N" and (i + 2 >= n or get(i + 2) not in "EIY"):
                    meta.append("K")
                elif nxt != "N":
                    meta.append("K")
        elif ch == "H":
            if (i == 0 or prev in "AEIOU") and nxt not in "AEIOU":
                meta.append("H")
        elif ch == "J":
            meta.append("J")
        elif ch == "K":
            if i == 0 or prev != "C":
                meta.append("K")
        elif ch == "L":
            meta.append("L")
        elif ch == "M":
            meta.append("M")
        elif ch == "N":
            meta.append("N")
        elif ch == "P":
            if nxt == "H":
                meta.append("F")
                i += 1
            else:
                meta.append("P")
        elif ch == "Q":
            meta.append("K")
        elif ch == "R":
            meta.append("R")
        elif ch == "S":
            if at(i, "SH"):
                meta.append("X")
                i += 1
            elif at(i, "SIO", "SIA"):
                meta.append("X")
            else:
                meta.append("S")
        elif ch == "T":
            if at(i, "TIA", "TIO"):
                meta.append("X")
            elif at(i, "TCH"):
                i += 2
            elif nxt == "H":
                meta.append("0")
                i += 1
            else:
                meta.append("T")
        elif ch == "V":
            meta.append("F")
        elif ch == "W":
            if nxt in "AEIOU":
                meta.append("W")
        elif ch == "X":
            meta.append("KS")
        elif ch == "Y":
            if nxt in "AEIOU":
                meta.append("Y")
        elif ch == "Z":
            meta.append("S")

        i += 1

    return "".join(meta)


def brand_match_rank(query, name):
    """Lower is better when sharing a Metaphone bucket."""
    bq = brand_word(query).lower()
    bn = brand_word(name).lower()
    if not bq or not bn:
        return 3
    if bq == bn:
        return 0
    if bn.startswith(bq) or bq.startswith(bn):
        return 1
    return 2


class MetaphoneIndex:
    """Inverted index: Metaphone code -> medicine names (brand token encoded)."""

    def __init__(self):
        self.inverted = defaultdict(list)

    def build(self, names):
        self.inverted = defaultdict(list)
        for name in names:
            brand = brand_word(name)
            if not brand:
                continue
            code = metaphone(brand)
            if code:
                self.inverted[code].append(name)

    def search(self, query, limit=25):
        brand = brand_word(query)
        if not brand:
            return []

        code = metaphone(brand)
        hits = [(code, name) for name in self.inverted.get(code, ())]

        hits.sort(
            key=lambda x: (brand_match_rank(query, x[1]), len(normalize(x[1])), x[1])
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


def build_index(names):
    index = MetaphoneIndex()
    index.build(names)
    return index


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    names = load_medicines_from_csv(DATASET_PATH)
    print(f"Loaded {len(names):,} medicine names. Building Metaphone index...")

    index = build_index(names)
    codes = len(index.inverted)
    print(f"Metaphone index ready ({codes:,} codes). Type a query; empty line or 'quit' to exit.\n")

    while True:
        try:
            query = input("Query> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query or query.lower() in ("quit", "exit", "q"):
            break

        brand = brand_word(query)
        code = metaphone(brand) if brand else ""
        results = index.search(query, limit=25)
        if not results:
            print(f"  No Metaphone matches for code [{code}].\n")
            continue

        print(f"  Metaphone({brand}) = {code} — {len(results)} match(es):")
        for i, (match_code, name) in enumerate(results, 1):
            print(f"    {i:2}. [{match_code}] {name}")
        print()


if __name__ == "__main__":
    main()
