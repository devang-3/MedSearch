"""LinUCB contextual bandit for merge-arm selection."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import numpy as np

from paths import POLICY_STATE_PATH
from policy.features import FEATURE_DIM
from policy.rank import ARM_NAMES

DEFAULT_ALPHA = 1.0


class LinUCBPolicy:
    """Disjoint LinUCB — one linear model per merge arm."""

    def __init__(
        self,
        d: int = FEATURE_DIM,
        n_arms: int = len(ARM_NAMES),
        alpha: float = DEFAULT_ALPHA,
        rng: random.Random | None = None,
    ):
        self.d = d
        self.n_arms = n_arms
        self.alpha = alpha
        self.rng = rng or random.Random()
        self.A = [np.identity(d, dtype=np.float64) for _ in range(n_arms)]
        self.b = [np.zeros(d, dtype=np.float64) for _ in range(n_arms)]
        self.arm_names = list(ARM_NAMES[:n_arms])
        self.total_updates = 0

    def select(self, features: list[float], explore: bool = True) -> int:
        x = np.asarray(features, dtype=np.float64)
        if x.shape[0] != self.d:
            raise ValueError(f"Expected {self.d} features, got {x.shape[0]}")

        if not explore:
            return self._best_arm(x)

        best_arm = 0
        best_score = float("-inf")
        for arm in range(self.n_arms):
            A_inv = np.linalg.solve(self.A[arm], np.eye(self.d))
            theta = A_inv @ self.b[arm]
            mean = float(theta @ x)
            uncertainty = float(np.sqrt(max(0.0, x @ A_inv @ x)))
            score = mean + self.alpha * uncertainty
            if score > best_score:
                best_score = score
                best_arm = arm
        return best_arm

    def _best_arm(self, x: np.ndarray) -> int:
        best_arm = 0
        best_score = float("-inf")
        for arm in range(self.n_arms):
            A_inv = np.linalg.solve(self.A[arm], np.eye(self.d))
            theta = A_inv @ self.b[arm]
            score = float(theta @ x)
            if score > best_score:
                best_score = score
                best_arm = arm
        return best_arm

    def update(self, features: list[float], arm: int, reward: float) -> None:
        x = np.asarray(features, dtype=np.float64)
        arm = int(arm) % self.n_arms
        self.A[arm] += np.outer(x, x)
        self.b[arm] += reward * x
        self.total_updates += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "algorithm": "linucb",
            "alpha": self.alpha,
            "d": self.d,
            "n_arms": self.n_arms,
            "arm_names": self.arm_names,
            "total_updates": self.total_updates,
            "A": [a.tolist() for a in self.A],
            "b": [v.tolist() for v in self.b],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LinUCBPolicy":
        policy = cls(
            d=int(data["d"]),
            n_arms=int(data.get("n_arms", len(ARM_NAMES))),
            alpha=float(data.get("alpha", DEFAULT_ALPHA)),
        )
        policy.arm_names = list(data.get("arm_names", ARM_NAMES))
        policy.total_updates = int(data.get("total_updates", 0))
        policy.A = [np.asarray(m, dtype=np.float64) for m in data["A"]]
        policy.b = [np.asarray(v, dtype=np.float64) for v in data["b"]]
        return policy


def save_policy(policy: LinUCBPolicy, path: Path | None = None) -> Path:
    out = path or POLICY_STATE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(policy.to_dict(), indent=2), encoding="utf-8")
    return out


def load_policy(path: Path | None = None) -> LinUCBPolicy:
    src = path or POLICY_STATE_PATH
    if not src.exists():
        return LinUCBPolicy()
    data = json.loads(src.read_text(encoding="utf-8"))
    return LinUCBPolicy.from_dict(data)
