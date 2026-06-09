"""Find alternative medicines by matching composition and dosage."""
from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from paths import DATASET_PATH

_COMPOSITION_RE = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")
_FORM_KEYWORDS = (
    "tablet",
    "capsule",
    "syrup",
    "injection",
    "suspension",
    "drop",
    "cream",
    "gel",
    "ointment",
    "powder",
    "spray",
    "inhaler",
    "solution",
    "sachet",
)


def normalize_salt(name: str) -> str:
    return " ".join(name.lower().split())


def normalize_strength(strength: str) -> str:
    return strength.lower().replace(" ", "")


def parse_composition(text: str) -> tuple[str, str] | None:
    """Parse 'Amoxycillin  (500mg)' -> (salt, strength)."""
    text = text.strip()
    if not text:
        return None
    match = _COMPOSITION_RE.match(text)
    if not match:
        return (normalize_salt(text), "")
    salt = normalize_salt(match.group(1))
    strength = normalize_strength(match.group(2))
    return (salt, strength)


def composition_signature(comp1: str, comp2: str) -> str:
    parts: list[tuple[str, str]] = []
    for text in (comp1, comp2):
        parsed = parse_composition(text)
        if parsed:
            parts.append(parsed)
    if not parts:
        return ""
    parts.sort()
    return "|".join(f"{salt}:{strength}" for salt, strength in parts)


def format_composition(comp1: str, comp2: str) -> str:
    bits = [c.strip() for c in (comp1, comp2) if c and c.strip()]
    return " + ".join(bits)


def parse_price(value: str) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        price = float(text)
    except ValueError:
        return None
    return price if price >= 0 else None


def parse_form(pack_size_label: str, name: str = "") -> str:
    text = f"{pack_size_label} {name}".lower()
    for keyword in _FORM_KEYWORDS:
        if keyword in text:
            return keyword
    return "other"


def format_form_label(form: str) -> str:
    if form == "other":
        return "Other"
    return form.capitalize()


def format_price_inr(price: float) -> str:
    return f"₹{price:.2f}"


def compute_savings(
    selected: MedicineMeta,
    pool: list[MedicineMeta],
) -> dict | None:
    """Cheapest priced alternative vs selected; None if savings not computable."""
    if selected.price is None or not pool:
        return None

    cheapest: MedicineMeta | None = None
    for meta in pool:
        if meta.price is not None:
            cheapest = meta
            break

    if cheapest is None or cheapest.price is None:
        return None

    if cheapest.price >= selected.price:
        return {
            "available": False,
            "reason": "already_cheapest",
            "cheapest_name": selected.name,
            "cheapest_price": selected.price,
            "cheapest_price_display": format_price_inr(selected.price),
            "selected_price": selected.price,
            "selected_price_display": format_price_inr(selected.price),
            "amount": 0.0,
            "amount_display": format_price_inr(0.0),
            "percent": 0.0,
            "percent_display": "0%",
        }

    amount = selected.price - cheapest.price
    percent = (amount / selected.price) * 100 if selected.price > 0 else 0.0

    return {
        "available": True,
        "reason": "cheaper_alternative",
        "cheapest_name": cheapest.name,
        "cheapest_price": cheapest.price,
        "cheapest_price_display": format_price_inr(cheapest.price),
        "selected_price": selected.price,
        "selected_price_display": format_price_inr(selected.price),
        "amount": round(amount, 2),
        "amount_display": format_price_inr(amount),
        "percent": round(percent, 1),
        "percent_display": f"{round(percent, 1)}%",
    }


def parse_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class MedicineMeta:
    id: str
    name: str
    pack_size_label: str
    short_composition1: str
    short_composition2: str
    signature: str
    composition_display: str
    price: float | None
    form: str


@dataclass
class AlternativeIndex:
    records: list[MedicineMeta] = field(default_factory=list)
    by_name_lower: dict[str, MedicineMeta] = field(default_factory=dict)
    by_signature: dict[str, list[MedicineMeta]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        csv_path: Path | None = None,
        name_filter: list[str] | None = None,
    ) -> "AlternativeIndex":
        path = csv_path or DATASET_PATH
        allowed = {n.lower() for n in name_filter} if name_filter else None

        records: list[MedicineMeta] = []
        by_name_lower: dict[str, MedicineMeta] = {}
        by_signature: dict[str, list[MedicineMeta]] = {}

        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                if allowed is not None and name.lower() not in allowed:
                    continue

                c1 = (row.get("short_composition1") or "").strip()
                c2 = (row.get("short_composition2") or "").strip()
                pack = (row.get("pack_size_label") or "").strip()
                sig = composition_signature(c1, c2)
                meta = MedicineMeta(
                    id=(row.get("id") or "").strip(),
                    name=name,
                    pack_size_label=pack,
                    short_composition1=c1,
                    short_composition2=c2,
                    signature=sig,
                    composition_display=format_composition(c1, c2),
                    price=parse_price(row.get("price", "")),
                    form=parse_form(pack, name),
                )
                records.append(meta)
                by_name_lower[name.lower()] = meta
                if sig:
                    by_signature.setdefault(sig, []).append(meta)

        return cls(records=records, by_name_lower=by_name_lower, by_signature=by_signature)

    def lookup(self, name: str) -> MedicineMeta | None:
        return self.by_name_lower.get(name.strip().lower())

    @staticmethod
    def _meta_to_item(meta: MedicineMeta) -> dict:
        return {
            "name": meta.name,
            "pack_size_label": meta.pack_size_label,
            "composition": meta.composition_display,
            "price": meta.price,
            "price_display": format_price_inr(meta.price) if meta.price is not None else "",
            "form": meta.form,
            "form_label": format_form_label(meta.form),
            "match": "exact",
        }

    @staticmethod
    def _sort_key(meta: MedicineMeta) -> tuple:
        return (
            meta.price is None,
            meta.price if meta.price is not None else float("inf"),
            meta.name.lower(),
        )

    def find_alternatives(
        self,
        name: str,
        limit: int = 20,
        same_form: bool = True,
    ) -> dict:
        selected = self.lookup(name)
        if not selected:
            return {
                "selected": name,
                "found": False,
                "composition": "",
                "pack_size_label": "",
                "price": None,
                "price_display": "",
                "form": "",
                "form_label": "",
                "same_form": same_form,
                "alternatives": [],
                "total_alternatives": 0,
                "total_matching_form": 0,
                "savings": None,
            }

        if not selected.signature:
            return {
                "selected": selected.name,
                "found": True,
                "composition": selected.composition_display,
                "pack_size_label": selected.pack_size_label,
                "price": selected.price,
                "price_display": format_price_inr(selected.price)
                if selected.price is not None
                else "",
                "form": selected.form,
                "form_label": format_form_label(selected.form),
                "same_form": same_form,
                "alternatives": [],
                "total_alternatives": 0,
                "total_matching_form": 0,
                "savings": None,
            }

        hits = self.by_signature.get(selected.signature, [])
        all_candidates: list[MedicineMeta] = []
        form_candidates: list[MedicineMeta] = []

        for meta in hits:
            if meta.name.lower() == selected.name.lower():
                continue
            all_candidates.append(meta)
            if meta.form == selected.form:
                form_candidates.append(meta)

        pool = form_candidates if same_form else all_candidates
        pool.sort(key=self._sort_key)

        alternatives = [self._meta_to_item(meta) for meta in pool[:limit]]
        savings = compute_savings(selected, pool)

        return {
            "selected": selected.name,
            "found": True,
            "composition": selected.composition_display,
            "pack_size_label": selected.pack_size_label,
            "price": selected.price,
            "price_display": format_price_inr(selected.price)
            if selected.price is not None
            else "",
            "form": selected.form,
            "form_label": format_form_label(selected.form),
            "same_form": same_form,
            "alternatives": alternatives,
            "total_alternatives": len(all_candidates),
            "total_matching_form": len(form_candidates),
            "savings": savings,
        }


def load_medicines_from_csv(path: Path | None = None) -> list[MedicineMeta]:
    return AlternativeIndex.build(path).records


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading medicines from {DATASET_PATH.name}...")
    index = AlternativeIndex.build()
    print(f"Loaded {len(index.records):,} medicines.")
    print(f"Unique composition signatures: {len(index.by_signature):,}")

    query = input("\nEnter medicine name for alternatives (or blank to quit): ").strip()
    while query:
        result = index.find_alternatives(query, limit=15, same_form=True)
        if not result["found"]:
            print(f"  Not found: {query}")
        else:
            print(f"\n  Selected: {result['selected']}")
            print(f"  Composition: {result['composition']}")
            print(f"  Pack: {result['pack_size_label']}")
            print(f"  Form: {result['form_label']}")
            if result["price_display"]:
                print(f"  Price: {result['price_display']}")
            total = result.get("total_matching_form", 0)
            print(
                f"  Alternatives ({total} same-form total, showing {len(result['alternatives'])}):"
            )
            for alt in result["alternatives"]:
                price = f" — {alt['price_display']}" if alt["price_display"] else ""
                print(f"    - {alt['name']} ({alt['pack_size_label']}){price}")
            if not result["alternatives"]:
                print("    (none)")

        query = input("\nEnter medicine name (or blank to quit): ").strip()


if __name__ == "__main__":
    main()
