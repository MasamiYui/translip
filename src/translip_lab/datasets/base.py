"""DatasetAdapter base + registry.

An adapter turns an external corpus (placed by the user under the datasets dir)
into a normalized ``SampleManifest``. Adapters are registered by name and
instantiated with the lab config plus suite-provided params (e.g. a folder root
or an AliMeeting subset). ``acquire`` is a hook for auto-download; most corpora
are EULA-gated, so the default is "user places files" and ``describe`` tells them
exactly where.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..config import LabConfig
from ..core.sample import SampleManifest


class DatasetAdapter(ABC):
    name: str = "dataset"

    def __init__(self, config: LabConfig, **params: Any) -> None:
        self.config = config
        self.params = params

    @property
    def root(self) -> Path:
        return self.config.datasets_dir / self.name

    def acquire(self) -> None:
        """Optional download hook. Default: no-op (files are user-provided)."""

    @abstractmethod
    def normalize(self) -> SampleManifest:
        ...

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root": str(self.root),
            "exists": self.root.exists(),
            "params": self.params,
        }


DATASET_REGISTRY: dict[str, type[DatasetAdapter]] = {}


def register_dataset(cls: type[DatasetAdapter]) -> type[DatasetAdapter]:
    DATASET_REGISTRY[cls.name] = cls
    return cls


def get_dataset(name: str, config: LabConfig, params: dict[str, Any] | None = None) -> DatasetAdapter:
    if name not in DATASET_REGISTRY:
        raise KeyError(f"unknown dataset '{name}'. Available: {sorted(DATASET_REGISTRY)}")
    return DATASET_REGISTRY[name](config, **(params or {}))


def available_datasets() -> list[str]:
    return sorted(DATASET_REGISTRY)
