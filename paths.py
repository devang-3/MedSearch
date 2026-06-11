"""Shared paths for MedSearch (run scripts from this folder)."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset"
DATASET_PATH = DATASET_DIR / "A_Z_medicines_dataset_of_India.csv"

EVAL_DIR = BASE_DIR / "eval"
POLICY_DIR = BASE_DIR / "policy"
BENCHMARK_PATH = EVAL_DIR / "typo_benchmark.jsonl"
POLICY_STATE_PATH = POLICY_DIR / "state.json"
EVAL_RESULTS_PATH = EVAL_DIR / "results.json"
