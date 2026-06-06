import csv
import sys
from collections import defaultdict
from paths import DATASET_PATH
TRIGRAM_N = 3
SEP = "\x01"


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


def build_suffix_array(text):
    """Suffix array via prefix-doubling (O(n log n))."""
    n = len(text)
    if n == 0:
        return []

    sa = list(range(n))
    rank = [ord(c) for c in text]
    tmp = [0] * n
    k = 1
    while k < n:
        sa.sort(key=lambda i: (rank[i], rank[i + k] if i + k < n else -1))
        tmp[sa[0]] = 0
        for j in range(1, n):
            prev, cur = sa[j - 1], sa[j]
            prev_key = (rank[prev], rank[prev + k] if prev + k < n else -1)
            cur_key = (rank[cur], rank[cur + k] if cur + k < n else -1)
            tmp[cur] = tmp[prev] + (prev_key < cur_key)
        rank, tmp = tmp, rank
        k <<= 1
    return sa


class SubstringIndex:
    """
    Substring / contains search:
    - Trigram inverted index to filter candidates
    - Suffix array on concatenated corpus for exact substring lookup
    """

    def __init__(self):
        self.names = []
        self.trigram = defaultdict(set)
        self.text = ""
        self.sa = []
        self.doc_at = []

    def build(self, names, progress_every=50000):
        self.names = names
        self.trigram = defaultdict(set)

        chunks = []
        doc_at = []
        pos = 0

        for doc_id, name in enumerate(names):
            norm = normalize(name)
            for tri in set(trigrams(norm)):
                self.trigram[tri].add(doc_id)

            piece = norm + SEP
            for _ in piece:
                doc_at.append(doc_id)
            chunks.append(piece)
            pos += len(piece)

        self.text = "".join(chunks)
        self.doc_at = doc_at

        print("  building suffix array (may take 1–2 min)...", flush=True)
        self.sa = build_suffix_array(self.text)

        if progress_every:
            print(f"  indexed {len(names):,} names, text length {len(self.text):,}", flush=True)

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

    def _sa_range(self, pattern):
        """Binary search suffix array for all occurrences of pattern."""
        if not pattern or not self.sa:
            return []

        m = len(pattern)
        n = len(self.text)

        def suffix_at(sa_idx):
            start = self.sa[sa_idx]
            return self.text[start : start + m]

        lo, hi = 0, len(self.sa)
        while lo < hi:
            mid = (lo + hi) // 2
            if suffix_at(mid) < pattern:
                lo = mid + 1
            else:
                hi = mid
        left = lo

        hi = len(self.sa)
        while lo < hi:
            mid = (lo + hi) // 2
            if suffix_at(mid) <= pattern:
                lo = mid + 1
            else:
                hi = mid
        right = lo

        doc_ids = set()
        for i in range(left, right):
            start = self.sa[i]
            if start + m > n:
                continue
            doc = self.doc_at[start]
            if doc >= 0:
                doc_ids.add(doc)
        return doc_ids

    def search(self, query, limit=25):
        pattern = parse_pattern(query)
        if not pattern:
            return []

        sa_docs = self._sa_range(pattern)
        tri_docs = self._trigram_candidates(pattern)

        if tri_docs is None:
            pool = sa_docs if sa_docs else set(range(len(self.names)))
        else:
            pool = (tri_docs & sa_docs) if sa_docs else tri_docs

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
    index = SubstringIndex()
    index.build(names)
    return index


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    names = load_medicines_from_csv(DATASET_PATH)
    print(f"Loaded {len(names):,} medicine names. Building trigram + suffix-array index...")

    index = build_index(names)
    print("Substring index ready. Use *text* or plain text; empty line or 'quit' to exit.\n")

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
