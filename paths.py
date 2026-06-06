"""Shared paths for MedSearch (run scripts from this folder)."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset"
DATASET_PATH = DATASET_DIR / "A_Z_medicines_dataset_of_India.csv"
