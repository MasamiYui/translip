"""Dataset adapters — import side-effects populate DATASET_REGISTRY."""
from __future__ import annotations

from .base import DATASET_REGISTRY, DatasetAdapter, available_datasets, get_dataset, register_dataset

# Importing each module registers its adapter.
from . import aishell4, alimeeting, folder, synthetic_mix, synthetic_subtitle, textgrid_folder  # noqa: E402,F401

__all__ = ["DATASET_REGISTRY", "DatasetAdapter", "get_dataset", "register_dataset", "available_datasets"]
