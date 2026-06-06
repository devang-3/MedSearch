import csv
import sys
from paths import DATASET_PATH


def normalize(text):
    return text.lower().strip()


def index_key(name):
    """Brand token used as BK-tree key (first word of medicine name)."""
    words = normalize(name).split()
    return words[0] if words else ""


def dose_token(text):
    for w in normalize(text).split():
        if any(c.isdigit() for c in w):
            return w
    return ""


def levenshtein(a, b, max_dist=None):
    """Edit distance; returns max_dist + 1 early if distance would exceed max_dist."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la < lb:
        a, b, la, lb = b, a, lb, la
    if max_dist is not None and la - lb > max_dist:
        return max_dist + 1

    if lb == 0:
        return la

    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            v = min(ins, delete, sub)
            cur.append(v)
            row_min = min(row_min, v)
        if max_dist is not None and row_min > max_dist:
            return max_dist + 1
        prev = cur
    return prev[lb]


class BKNode:
    __slots__ = ("key", "entries", "children")

    def __init__(self, word):
        self.key = index_key(word)
        self.entries = [word]
        self.children = {}


class BKTree:
    """BK-tree on medicine brand keys; each node may hold several full names."""

    def __init__(self):
        self.root = None
        self.size = 0

    def insert(self, word):
        word = word.strip()
        if not word:
            return

        key = index_key(word)
        if not key:
            return

        if self.root is None:
            self.root = BKNode(word)
            self.size += 1
            return

        node = self.root
        while True:
            dist = levenshtein(key, node.key)
            if dist == 0:
                if word not in node.entries:
                    node.entries.append(word)
                    self.size += 1
                return
            child = node.children.get(dist)
            if child is None:
                node.children[dist] = BKNode(word)
                self.size += 1
                return
            node = child

    def _search(self, node, query_key, max_dist, results):
        # Exact distance required for BK-tree triangle-inequality pruning.
        dist = levenshtein(query_key, node.key)
        if dist <= max_dist:
            for name in node.entries:
                results.append((dist, name))

        low = dist - max_dist
        high = dist + max_dist
        for edge_dist, child in node.children.items():
            if low <= edge_dist <= high:
                self._search(child, query_key, max_dist, results)

    def search(self, query, max_dist=None, limit=25):
        query = query.strip()
        if not query or self.root is None:
            return []

        query_key = index_key(query)
        if not query_key:
            return []

        if max_dist is None:
            max_dist = default_max_distance(query_key)

        results = []
        self._search(self.root, query_key, max_dist, results)

        qn = normalize(query)
        brand_q = index_key(query)
        q_dose = dose_token(query)
        ranked = []
        for key_dist, name in results:
            nk = index_key(name)
            brand_dist = levenshtein(brand_q, nk, max_dist=max_dist + 2)
            dose_dist = (
                0
                if not q_dose
                else levenshtein(q_dose, dose_token(name), max_dist=max_dist + 2)
                if dose_token(name)
                else max_dist + 2
            )
            full_dist = levenshtein(qn, normalize(name), max_dist=max_dist + 12)
            ranked.append((key_dist, brand_dist, dose_dist, full_dist, len(qn), name))

        ranked.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4], x[5]))
        seen = set()
        unique = []
        for key_dist, _brand, _dose, _full, _nlen, name in ranked:
            if name in seen:
                continue
            seen.add(name)
            unique.append((key_dist, name))
            if len(unique) >= limit:
                break
        return unique


def default_max_distance(query_key):
    n = len(query_key)
    if n <= 4:
        return 2
    if n <= 12:
        return 3
    return min(5, max(3, n // 5))


def load_medicines_from_csv(path):
    names = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if name:
                names.append(name)
    return names


def build_tree(names, progress_every=25000):
    tree = BKTree()
    total = len(names)
    for i, name in enumerate(names, 1):
        tree.insert(name)
        if progress_every and i % progress_every == 0:
            print(f"  inserted {i:,} / {total:,} ...", flush=True)
    return tree


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    names = load_medicines_from_csv(DATASET_PATH)
    print(f"Loaded {len(names):,} medicine names. Building BK-tree (may take a few minutes)...")

    tree = build_tree(names)
    print(f"BK-tree ready ({tree.size:,} entries). Type a query; empty line or 'quit' to exit.\n")

    while True:
        try:
            query = input("Query> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query or query.lower() in ("quit", "exit", "q"):
            break

        max_dist = default_max_distance(index_key(query))
        results = tree.search(query, max_dist=max_dist, limit=25)
        if not results:
            print(f"  No matches within edit distance {max_dist}.\n")
            continue

        print(f"  Top {len(results)} match(es) (max edit distance {max_dist}):")
        for i, (dist, name) in enumerate(results, 1):
            print(f"    {i:2}. [d={dist}] {name}")
        print()


if __name__ == "__main__":
    main()
