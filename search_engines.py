"""Load and query all medicine search engines for the web UI."""
from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alternatives import AlternativeIndex
from paths import BASE_DIR, DATASET_PATH, POLICY_STATE_PATH
from policy.bandit import LinUCBPolicy, load_policy
from policy.merge import rank_with_policy, resolve_merge_mode


def _load_module(module_name: str, filename: str):
    path = BASE_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class SearchEngines:
    names: list[str]
    name_by_lower: dict[str, str]
    prefix: Any
    fuzzy: Any
    keyboard: Any
    substring: Any
    dmetaphone: Any
    alternatives: AlternativeIndex
    merge_mode: str = "auto"
    bandit: LinUCBPolicy | None = None
    _pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=5))

    @classmethod
    def build(
        cls,
        names: list[str] | None = None,
        *,
        merge_mode: str = "auto",
        policy_path: Path | None = None,
    ) -> "SearchEngines":
        if names is None:
            prefix_mod = _load_module("prefix", "prefix.py")
            names = prefix_mod.load_medicines_from_csv(DATASET_PATH)

        print(f"Loaded {len(names):,} medicine names.", flush=True)

        prefix_mod = _load_module("prefix", "prefix.py")
        print("  [1/6] Prefix trie...", flush=True)
        trie = prefix_mod.build_trie(names)

        fuzzy_mod = _load_module("fuzzy_ngram", "fuzzy_n-gram.py")
        print("  [2/6] Fuzzy n-gram index...", flush=True)
        fuzzy_idx = fuzzy_mod.build_index(names)

        key_mod = _load_module("key", "key.py")
        print("  [3/6] Keyboard / Damerau–Levenshtein index...", flush=True)
        key_idx = key_mod.build_index(names)

        dm_mod = _load_module("double_metaphone", "double_metaphone.py")
        print("  [4/6] Double Metaphone index...", flush=True)
        dm_idx = dm_mod.build_index(names)

        sub_mod = _load_module("substring_trigram", "sub-string-tri.py")
        print("  [5/6] Substring index (trigram)...", flush=True)
        sub_idx = sub_mod.build_index(names)

        print("  [6/6] Alternatives index (composition)...", flush=True)
        alt_idx = AlternativeIndex.build(DATASET_PATH, name_filter=names)

        bandit: LinUCBPolicy | None = None
        state_path = policy_path or POLICY_STATE_PATH
        if state_path.exists():
            bandit = load_policy(state_path)
            print(f"  Loaded LinUCB policy ({bandit.total_updates} updates).", flush=True)

        resolved = resolve_merge_mode(merge_mode, policy_available=bandit is not None)
        print(f"  Merge mode: {resolved}", flush=True)
        print("All search engines ready.\n", flush=True)
        return cls(
            names=names,
            name_by_lower={n.lower(): n for n in names},
            prefix=trie,
            fuzzy=fuzzy_idx,
            keyboard=key_idx,
            substring=sub_idx,
            dmetaphone=dm_idx,
            alternatives=alt_idx,
            merge_mode=resolved if merge_mode != "auto" else merge_mode,
            bandit=bandit,
        )

    def _display_name(self, name: str) -> str:
        return self.name_by_lower.get(name.lower(), name)

    def _search_prefix(self, query: str, limit: int) -> list[dict]:
        raw = self.prefix.get_suggestions(query, limit=limit)
        return [
            {"name": self._display_name(n), "detail": "prefix match"} for n in raw
        ]

    def _search_fuzzy(self, query: str, limit: int) -> list[dict]:
        min_j = 0.15 if len(query) >= 4 else 0.2
        raw = self.fuzzy.search(query, limit=limit, min_jaccard=min_j)
        return [
            {"name": self._display_name(n), "detail": f"score {s:.2f}"}
            for s, n in raw
        ]

    def _search_keyboard(self, query: str, limit: int) -> list[dict]:
        if len(query) < 2:
            return []
        raw = self.keyboard.search(query, limit=limit)
        return [
            {"name": self._display_name(n), "detail": f"DL={dl} kb={kb:.1f}"}
            for dl, kb, n in raw
        ]

    def _search_substring(self, query: str, limit: int) -> list[dict]:
        if len(query) < 2:
            return []
        raw = self.substring.search(query, limit=limit)
        return [
            {"name": self._display_name(n), "detail": f"at position {pos}"}
            for pos, n in raw
        ]

    def _search_dmetaphone(self, query: str, limit: int) -> list[dict]:
        if len(query) < 2:
            return []
        raw = self.dmetaphone.search(query, limit=limit)
        return [
            {
                "name": self._display_name(n),
                "detail": f"{'primary' if pri else 'alternate'} [{code}]",
            }
            for code, pri, n in raw
        ]

    def search_all(
        self,
        query: str,
        per_algo: int = 8,
        combined_limit: int = 10,
        *,
        merge: str | None = None,
        debug: bool = False,
    ) -> dict:
        q = query.strip()
        if not q:
            return {"query": "", "combined": [], "algorithms": {}}

        algos = {
            "prefix": lambda: self._search_prefix(q, per_algo),
            "fuzzy_ngram": lambda: self._search_fuzzy(q, per_algo),
            "keyboard_dl": lambda: self._search_keyboard(q, per_algo),
            "substring": lambda: self._search_substring(q, per_algo),
            "double_metaphone": lambda: self._search_dmetaphone(q, per_algo),
        }

        results: dict[str, list[dict]] = {}
        futures = {k: self._pool.submit(fn) for k, fn in algos.items()}
        for key, fut in futures.items():
            try:
                results[key] = fut.result(timeout=120)
            except Exception as exc:
                results[key] = []
                results[f"_{key}_error"] = str(exc)

        clean_algos = {k: v for k, v in results.items() if not k.startswith("_")}

        mode_request = merge if merge is not None else self.merge_mode
        mode = resolve_merge_mode(mode_request, policy_available=self.bandit is not None)

        combined, merge_meta = rank_with_policy(
            q,
            clean_algos,
            mode=mode,
            bandit=self.bandit,
            explore=False,
            combined_limit=combined_limit,
            include_features=debug,
        )

        payload: dict[str, Any] = {
            "query": q,
            "combined": combined,
            "algorithms": clean_algos,
            "merge": {
                "mode": mode,
                "arm": merge_meta.get("arm"),
                "arm_name": merge_meta.get("arm_name"),
            },
        }
        if debug and "features" in merge_meta:
            payload["merge"]["features"] = merge_meta["features"]
        return payload

    def find_alternatives(
        self,
        name: str,
        limit: int = 20,
        same_form: bool = True,
    ) -> dict:
        canonical = self._display_name(name)
        return self.alternatives.find_alternatives(
            canonical, limit=limit, same_form=same_form
        )
