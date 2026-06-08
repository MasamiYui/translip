from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from shutil import copy2
from typing import Any, Callable

from ....utils.io import write_json as _write_json_impl


ProgressCallback = Callable[[float, str | None], None]


class ToolAdapter(ABC):
    @abstractmethod
    def validate_params(self, params: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def run(
        self,
        params: dict,
        input_dir: Path,
        output_dir: Path,
        on_progress: ProgressCallback,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def first_input(input_dir: Path, stem: str | None = None) -> Path:
        base_dir = input_dir / stem if stem else input_dir
        return next(path for path in base_dir.rglob("*") if path.is_file())

    @staticmethod
    def copy_output(src: Path, output_dir: Path, filename: str | None = None) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / (filename or src.name)
        copy2(src, target)
        return target

    @staticmethod
    def write_json(output_path: Path, payload: dict[str, Any]) -> Path:
        return _write_json_impl(payload, output_path, atomic=False, trailing_newline=True)


# Auto-discover adapter modules: importing each triggers its register_tool()
# side-effect, so dropping a new adapter file in this package registers it with
# no manual list to keep in sync.
import importlib as _importlib  # noqa: E402
import pkgutil as _pkgutil  # noqa: E402

for _module in sorted(_pkgutil.iter_modules(__path__), key=lambda m: m.name):
    if _module.name.startswith("_"):
        continue
    _importlib.import_module(f"{__name__}.{_module.name}")
