"""
Interactive medicine search UI (Google-style autocomplete + per-algorithm panels).

Usage:
    cd MedSearch
    pip install -r requirements-search.txt
    python medicine_search_ui.py

Then open http://127.0.0.1:5000

Search and selection history is saved to history.json for retraining.
"""
from __future__ import annotations

import argparse
import json
import os
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from alternatives import parse_bool
from search_engines import SearchEngines

APP_DIR = Path(__file__).resolve().parent
HISTORY_PATH = APP_DIR / "history.json"
app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)
engines: SearchEngines | None = None


def _load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


@app.route("/")
def index():
    return render_template("medicine_search.html")


@app.route("/api/suggest")
def api_suggest():
    if engines is None:
        return jsonify({"error": "Search engines not loaded"}), 503

    query = request.args.get("q", "")
    per_algo = min(int(request.args.get("per_algo", 8)), 15)
    combined_limit = min(int(request.args.get("combined", 10)), 15)
    merge = request.args.get("merge", "").strip() or None
    debug = parse_bool(request.args.get("debug"), default=False)

    if not query.strip():
        return jsonify({"query": "", "combined": [], "algorithms": {}})

    data = engines.search_all(
        query,
        per_algo=per_algo,
        combined_limit=combined_limit,
        merge=merge,
        debug=debug,
    )
    return jsonify(data)


@app.route("/api/alternatives")
def api_alternatives():
    if engines is None:
        return jsonify({"error": "Search engines not loaded"}), 503

    name = request.args.get("name", "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)
    same_form = parse_bool(request.args.get("same_form"), default=True)

    if not name:
        return jsonify({"error": "name parameter required"}), 400

    return jsonify(engines.find_alternatives(name, limit=limit, same_form=same_form))


@app.route("/api/health")
def health():
    if engines is None:
        return jsonify({"ok": False})
    return jsonify(
        {
            "ok": True,
            "merge_mode": engines.merge_mode,
            "linucb_loaded": engines.bandit is not None,
            "linucb_updates": engines.bandit.total_updates if engines.bandit else 0,
        }
    )


@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify(_load_history())


@app.route("/api/history", methods=["POST"])
def save_history():
    try:
        entry = request.get_json()
        if not entry:
            return jsonify({"error": "No data provided"}), 400

        history = _load_history()
        history.append(entry)

        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        return jsonify({"status": "ok", "count": len(history)}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def main():
    global engines

    parser = argparse.ArgumentParser(description="Medicine multi-algorithm search UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Use only first N medicines (faster dev test; 0 = full dataset)",
    )
    parser.add_argument(
        "--merge",
        choices=("auto", "fixed", "linucb", "balanced"),
        default="auto",
        help="Combined ranking: auto=LinUCB if policy/state.json exists else fixed",
    )
    args = parser.parse_args()

    print("Building search indexes (first run may take several minutes)...")
    names = None
    if args.limit > 0:
        from search_engines import DATASET_PATH, _load_module

        prefix_mod = _load_module("prefix", "prefix.py")
        names = prefix_mod.load_medicines_from_csv(DATASET_PATH)[: args.limit]
        print(f"  (--limit {args.limit} names only)")
    engines = SearchEngines.build(names, merge_mode=args.merge)

    history = _load_history()
    print(f"  Loaded {len(history)} previous search+selection records from history.json.")

    url = f"http://{args.host}:{args.port}"
    print(f"Open {url}")
    if not args.no_browser:
        webbrowser.open(url)

    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
