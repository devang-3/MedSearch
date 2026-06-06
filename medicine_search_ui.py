"""
Interactive medicine search UI (Google-style autocomplete + per-algorithm panels).

Usage:
    cd MedSearch
    pip install -r requirements-search.txt
    python medicine_search_ui.py

Then open http://127.0.0.1:5000
"""
from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from alternatives import parse_bool
from search_engines import SearchEngines

APP_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)
engines: SearchEngines | None = None


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

    if not query.strip():
        return jsonify({"query": "", "combined": [], "algorithms": {}})

    data = engines.search_all(query, per_algo=per_algo, combined_limit=combined_limit)
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
    return jsonify({"ok": engines is not None})


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
    args = parser.parse_args()

    print("Building search indexes (first run may take several minutes)...")
    names = None
    if args.limit > 0:
        from search_engines import DATASET_PATH, _load_module

        prefix_mod = _load_module("prefix", "prefix.py")
        names = prefix_mod.load_medicines_from_csv(DATASET_PATH)[: args.limit]
        print(f"  (--limit {args.limit} names only)")
    engines = SearchEngines.build(names)

    url = f"http://{args.host}:{args.port}"
    print(f"Open {url}")
    if not args.no_browser:
        webbrowser.open(url)

    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
