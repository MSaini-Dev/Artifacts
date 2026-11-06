"""Configuration for tool retrieval and orchestration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OrchestrationConfig:
    retrieval_k: int = 6
    retrieval_threshold: float = 0.12
    max_steps: int = 6
    max_replans: int = 2
    parallelism: int = 3
    max_total_steps: int = 12
    shell_timeout: int = 30

    @classmethod
    def from_env(cls) -> "OrchestrationConfig":
        return cls(
            retrieval_k=max(1, int(os.getenv("ORCHESTRATION_K", "6"))),
            retrieval_threshold=float(os.getenv("ORCHESTRATION_THRESHOLD", "0.12")),
            max_steps=max(1, int(os.getenv("ORCHESTRATION_MAX_STEPS", "6"))),
            max_replans=max(0, int(os.getenv("ORCHESTRATION_MAX_REPLANS", "2"))),
            parallelism=max(1, int(os.getenv("ORCHESTRATION_PARALLELISM", "3"))),
            max_total_steps=max(1, int(os.getenv("ORCHESTRATION_MAX_TOTAL_STEPS", "12"))),
            shell_timeout=max(1, int(os.getenv("ORCHESTRATION_SHELL_TIMEOUT", "30"))),
        )
