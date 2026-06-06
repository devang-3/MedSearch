# MedSearch

A multi-algorithm medicine search application supporting prefix matching, fuzzy search, keyboard-aware typo correction, substring search, and phonetic matching via Double Metaphone.

## Features

- **Prefix Search** (Trie): Fast prefix matching with alphabetical sorting
- **Fuzzy Search** (N-gram): Approximate matching using Jaccard similarity on character n-grams
- **Keyboard Search** (Damerau–Levenshtein): Find medicines with typos considering QWERTY keyboard proximity
- **Substring Search** (Trigram): Contains search with wildcard support (`*text*`)
- **Double Metaphone**: Phonetic matching for medicine names

## Setup

```bash
cd MedSearch
pip install -r requirements-search.txt
```

## Usage

```bash
# Web UI (default)
python medicine_search_ui.py

# Then open http://127.0.0.1:5000 in your browser

# Or run individual algorithm modules:
python prefix.py      # Prefix trie search
python fuzzy_n-gram.py    # Fuzzy n-gram search
python key.py         # Keyboard-aware search
python sub-string-tri.py  # Substring/trigram search
python double_metaphone.py  # Phonetic search
```

## Dataset

The application uses `dataset/A_Z_medicines_dataset_of_India.csv` containing Indian medicine names.

## Files

| File | Description |
|------|-------------|
| `medicine_search_ui.py` | Flask web UI with autocomplete |
| `search_engines.py` | Combined search engine orchestrator |
| `prefix.py` | Trie-based prefix search |
| `fuzzy_n-gram.py` | N-gram fuzzy search |
| `key.py` | Keyboard-aware Damerau–Levenshtein search |
| `sub-string-tri.py` | Trigram substring index |
| `double_metaphone.py` | Double Metaphone phonetic search |
| `paths.py` | Shared path configuration |
| `templates/medicine_search.html` | UI template |
| `static/medicine_search.js` | Frontend JavaScript |
| `static/medicine_search.css` | Styling |