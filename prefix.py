import csv
import sys
from paths import DATASET_PATH


class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end_of_word = False


class PrefixTree:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        word = word.lower().strip()
        if not word:
            return

        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end_of_word = True

    def _dfs(self, node, prefix, suggestions, limit):
        if len(suggestions) >= limit:
            return
        if node.is_end_of_word:
            suggestions.append(prefix)

        for char in sorted(node.children):
            if len(suggestions) >= limit:
                return
            self._dfs(node.children[char], prefix + char, suggestions, limit)

    def get_suggestions(self, prefix, limit=20):
        node = self.root
        prefix = prefix.lower().strip()
        if not prefix:
            return []

        for char in prefix:
            if char not in node.children:
                return []
            node = node.children[char]

        suggestions = []
        self._dfs(node, prefix, suggestions, limit)
        return suggestions


def load_medicines_from_csv(path):
    names = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if name:
                names.append(name)
    return names


def build_trie(names):
    trie = PrefixTree()
    for name in names:
        trie.insert(name)
    return trie


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    names = load_medicines_from_csv(DATASET_PATH)
    print(f"Loaded {len(names):,} medicine names. Building trie...")

    trie = build_trie(names)
    print("Trie ready. Type a prefix to search (empty line or 'quit' to exit).\n")

    while True:
        try:
            prefix = input("Prefix> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prefix or prefix.lower() in ("quit", "exit", "q"):
            break

        results = trie.get_suggestions(prefix, limit=25)
        if not results:
            print("  No matches.\n")
            continue

        print(f"  {len(results)} match(es)" + (" (showing up to 25)" if len(results) == 25 else "") + ":")
        for i, name in enumerate(results, 1):
            print(f"    {i:2}. {name}")
        print()


if __name__ == "__main__":
    main()
