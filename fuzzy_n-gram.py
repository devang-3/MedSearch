import csv
import sys
from collections import Counter, defaultdict
from paths import DATASET_PATH
DEFAULT_N = 3


def char_ngrams(text, n=DEFAULT_N):
    """Character n-grams with padding for edge characters."""
    text = f"  {text.lower().strip()}  "
    if len(text) < n:
        return set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


class NGramFuzzyIndex:
    """Fuzzy search via inverted character n-gram index + Jaccard ranking."""

    def __init__(self, n=DEFAULT_N):
        self.n = n
        self.names = []
        self.doc_grams = []
        self.inverted = defaultdict(set)

    def build(self, names):
        self.names = names
        self.doc_grams = []
        self.inverted = defaultdict(set)

        for doc_id, name in enumerate(names):
            grams = char_ngrams(name, self.n)
            self.doc_grams.append(grams)
            for gram in grams:
                self.inverted[gram].add(doc_id)

    def search(self, query, limit=25, min_jaccard=0.2):
        query_grams = char_ngrams(query, self.n)
        if not query_grams:
            return []

        # Vote: candidates sharing at least one query n-gram
        votes = Counter()
        for gram in query_grams:
            for doc_id in self.inverted.get(gram, ()):
                votes[doc_id] += 1

        if not votes:
            return []

        # Rank top candidates by Jaccard similarity on n-gram sets
        pool_size = min(len(votes), limit * 40)
        ranked = []
        for doc_id, _ in votes.most_common(pool_size):
            doc_grams = self.doc_grams[doc_id]
            inter = len(query_grams & doc_grams)
            union = len(query_grams | doc_grams)
            score = inter / union if union else 0.0
            if score >= min_jaccard:
                ranked.append((score, self.names[doc_id]))

        ranked.sort(key=lambda x: (-x[0], x[1]))
        seen = set()
        results = []
        for score, name in ranked:
            if name in seen:
                continue
            seen.add(name)
            results.append((score, name))
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
    index = NGramFuzzyIndex(n=n)
    index.build(names)
    return index


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    names = load_medicines_from_csv(DATASET_PATH)
    print(f"Loaded {len(names):,} medicine names. Building {DEFAULT_N}-gram index...")

    index = build_index(names)
    print(
        "N-gram index ready. Type a query (typos OK); empty line or 'quit' to exit.\n"
    )

    while True:
        try:
            query = input("Query> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query or query.lower() in ("quit", "exit", "q"):
            break

        results = index.search(query, limit=25)
        if not results:
            print("  No fuzzy matches.\n")
            continue

        print(f"  Top {len(results)} match(es):")
        for i, (score, name) in enumerate(results, 1):
            print(f"    {i:2}. [{score:.2f}] {name}")
        print()


if __name__ == "__main__":
    main()
