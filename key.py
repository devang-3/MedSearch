import csv
import sys
from collections import Counter, defaultdict
from paths import DATASET_PATH
DEFAULT_N = 3

# QWERTY horizontal neighbors (lowercase)
_QWERTY_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
KEYBOARD_NEIGHBORS = defaultdict(set)
for _row in _QWERTY_ROWS:
    for _i, _ch in enumerate(_row):
        if _i > 0:
            KEYBOARD_NEIGHBORS[_ch].add(_row[_i - 1])
        if _i + 1 < len(_row):
            KEYBOARD_NEIGHBORS[_ch].add(_row[_i + 1])


def normalize(text):
    return text.lower().strip()


def brand_word(name):
    for word in normalize(name).split():
        if word and word[0].isalpha():
            return word
    return ""


def dose_token(text):
    for w in normalize(text).split():
        if any(c.isdigit() for c in w):
            return w
    return ""


def dose_match_rank(query, name):
    qd = dose_token(query)
    if not qd:
        return 0
    nd = dose_token(name)
    if not nd:
        return 2
    return damerau_levenshtein(qd, nd, max_dist=3)


def brand_prefix_rank(query, name):
    """Prefer candidates whose brand shares query prefix (e.g. asprin → aspirin)."""
    bq, bn = brand_word(query), brand_word(name)
    if not bq or not bn:
        return 2
    if bq == bn:
        return 0
    n = min(3, len(bq))
    if bn.startswith(bq[:n]) or bq.startswith(bn[:n]):
        return 1
    return 2


def keyboard_sub_cost(a, b):
    """Substitution cost: 0 same, 0.5 adjacent keys, 1.0 otherwise."""
    if a == b:
        return 0.0
    if b in KEYBOARD_NEIGHBORS.get(a, ()):
        return 0.5
    return 1.0


def damerau_levenshtein(a, b, max_dist=None):
    """Damerau–Levenshtein: insert, delete, substitute, transpose adjacent."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if max_dist is not None and abs(la - lb) > max_dist:
        return max_dist + 1
    if la == 0:
        return lb
    if lb == 0:
        return la

    da = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        da[i][0] = i
    for j in range(lb + 1):
        da[0][j] = j

    for i in range(1, la + 1):
        row_min = da[i][0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            best = min(da[i - 1][j] + 1, da[i][j - 1] + 1, da[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                best = min(best, da[i - 2][j - 2] + 1)
            da[i][j] = best
            row_min = min(row_min, best)
        if max_dist is not None and row_min > max_dist:
            return max_dist + 1

    result = da[la][lb]
    if max_dist is not None and result > max_dist:
        return max_dist + 1
    return result


def keyboard_damerau_levenshtein(a, b, max_cost=None):
    """Weighted DL: cheaper substitution when keys are QWERTY neighbors."""
    if a == b:
        return 0.0
    la, lb = len(a), len(b)
    if la == 0:
        return float(lb)
    if lb == 0:
        return float(la)

    da = [[0.0] * (lb + 1) for _ in range(la + 1)]
    for i in range(1, la + 1):
        da[i][0] = float(i)
    for j in range(1, lb + 1):
        da[0][j] = float(j)

    for i in range(1, la + 1):
        row_min = da[i][0]
        for j in range(1, lb + 1):
            sub = keyboard_sub_cost(a[i - 1], b[j - 1])
            best = min(da[i - 1][j] + 1.0, da[i][j - 1] + 1.0, da[i - 1][j - 1] + sub)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                best = min(best, da[i - 2][j - 2] + 1.0)
            da[i][j] = best
            row_min = min(row_min, best)
        if max_cost is not None and row_min > max_cost:
            return max_cost + 1.0

    result = da[la][lb]
    if max_cost is not None and result > max_cost:
        return max_cost + 1.0
    return result


def char_ngrams(text, n=DEFAULT_N):
    text = f"  {normalize(text)}  "
    if len(text) < n:
        return set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def default_max_distance(query):
    n = len(normalize(query))
    if n <= 4:
        return 2
    if n <= 12:
        return 3
    return min(6, max(3, n // 4))


class KeyboardSearchIndex:
    """N-gram candidate filter + Damerau–Levenshtein / keyboard-weighted ranking."""

    def __init__(self, n=DEFAULT_N):
        self.n = n
        self.names = []
        self.inverted = defaultdict(set)

    def build(self, names):
        self.names = names
        self.inverted = defaultdict(set)
        for doc_id, name in enumerate(names):
            for gram in char_ngrams(name, self.n):
                self.inverted[gram].add(doc_id)

    def search(self, query, limit=25, max_dist=None):
        query_norm = normalize(query)
        if not query_norm:
            return []

        if max_dist is None:
            max_dist = default_max_distance(query)

        query_grams = char_ngrams(query_norm, self.n)
        if not query_grams:
            return []

        votes = Counter()
        for gram in query_grams:
            for doc_id in self.inverted.get(gram, ()):
                votes[doc_id] += 1

        if not votes:
            return []

        brand_q = brand_word(query)
        pool_size = min(len(votes), limit * 50)
        ranked = []
        for doc_id, _ in votes.most_common(pool_size):
            name = self.names[doc_id]
            full = normalize(name)
            bn = brand_word(name)
            if brand_q and bn:
                brand_dl = damerau_levenshtein(brand_q, bn, max_dist=max_dist + 2)
                kb = keyboard_damerau_levenshtein(
                    brand_q, bn, max_cost=float(max_dist) + 2.0
                )
            else:
                brand_dl = damerau_levenshtein(query_norm, full, max_dist=max_dist + 4)
                kb = keyboard_damerau_levenshtein(
                    query_norm, full, max_cost=float(max_dist) + 4.0
                )
            if brand_dl > max_dist + 1:
                continue
            dose_r = dose_match_rank(query, name)
            prefix_r = brand_prefix_rank(query, name)
            ranked.append((brand_dl, prefix_r, dose_r, kb, len(full), name))

        ranked.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4], x[5]))

        seen = set()
        results = []
        for brand_dl, _pfx, _dose, kb, _ln, name in ranked:
            if name in seen:
                continue
            seen.add(name)
            results.append((brand_dl, kb, name))
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


def build_index(names, n=DEFAULT_N):
    index = KeyboardSearchIndex(n=n)
    index.build(names)
    return index


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    names = load_medicines_from_csv(DATASET_PATH)
    print(f"Loaded {len(names):,} medicine names. Building n-gram index...")

    index = build_index(names)
    print(
        "Keyboard-aware search ready (Damerau–Levenshtein + QWERTY weights).\n"
        "Type a query; empty line or 'quit' to exit.\n"
    )

    while True:
        try:
            query = input("Query> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query or query.lower() in ("quit", "exit", "q"):
            break

        max_dist = default_max_distance(query)
        results = index.search(query, limit=25, max_dist=max_dist)
        if not results:
            print(f"  No matches within Damerau–Levenshtein ~{max_dist}.\n")
            continue

        print(f"  Top {len(results)} match(es):")
        for i, (dl, kb, name) in enumerate(results, 1):
            print(f"    {i:2}. [DL={dl} kb={kb:.1f}] {name}")
        print()


if __name__ == "__main__":
    main()
