import csv
import sys
from collections import defaultdict
from paths import DATASET_PATH
TRIGRAM_N = 3


def normalize(text):
    return text.lower().strip()


def parse_pattern(query):
    """Turn *cillin* or cillin into plain substring pattern."""
    q = query.strip()
    if q.startswith("*"):
        q = q[1:]
    if q.endswith("*"):
        q = q[:-1]
    return normalize(q)


def trigrams(text, n=TRIGRAM_N):
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


class TrigramSubstringIndex:
    """
    Substring / contains search using inverted trigram index only.
    Fast build (~seconds); query: intersect postings then verify with `in`.
    """

    def __init__(self):
        self.names = []
        self.trigram = defaultdict(set)

    def build(self, names):
        self.names = names
        self.trigram = defaultdict(set)
        for doc_id, name in enumerate(names):
            norm = normalize(name)
            for tri in set(trigrams(norm)):
                self.trigram[tri].add(doc_id)

    def _trigram_candidates(self, pattern):
        if len(pattern) < TRIGRAM_N:
            return None

        lists = []
        for tri in trigrams(pattern):
            docs = self.trigram.get(tri)
            if not docs:
                return set()
            lists.append(docs)

        common = set(lists[0])
        for docs in lists[1:]:
            common &= docs
        return common

    def search(self, query, limit=25):
        pattern = parse_pattern(query)
        if not pattern:
            return []

        tri_docs = self._trigram_candidates(pattern)
        if tri_docs is None:
            pool = range(len(self.names))
        else:
            pool = tri_docs

        ranked = []
        for doc_id in pool:
            name = self.names[doc_id]
            norm = normalize(name)
            pos = norm.find(pattern)
            if pos < 0:
                continue
            ranked.append((pos, len(norm), name))

        ranked.sort(key=lambda x: (x[0], x[1], x[2]))

        seen = set()
        results = []
        for pos, _ln, name in ranked:
            if name in seen:
                continue
            seen.add(name)
            results.append((pos, name))
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
    index = TrigramSubstringIndex()
    index.build(names)
    return index


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    names = load_medicines_from_csv(DATASET_PATH)
    print(f"Loaded {len(names):,} medicine names. Building trigram substring index...")

    index = build_index(names)
    print("Trigram substring index ready. Use *text* or plain text; empty line or 'quit' to exit.\n")

    while True:
        try:
            query = input("Contains> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query or query.lower() in ("quit", "exit", "q"):
            break

        pattern = parse_pattern(query)
        results = index.search(query, limit=25)
        if not results:
            print(f"  No names containing [{pattern}].\n")
            continue

        print(f"  {len(results)} match(es) for [{pattern}]:")
        for i, (pos, name) in enumerate(results, 1):
            print(f"    {i:2}. @{pos:3} {name}")
        print()


if __name__ == "__main__":
    main()
