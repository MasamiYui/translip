"""Run reports: markdown + self-contained HTML, plus run-vs-run comparison."""
from __future__ import annotations

from .html import compare_to_html, run_to_html
from .markdown import compare_to_markdown, run_to_markdown, sweep_to_markdown

__all__ = ["run_to_markdown", "compare_to_markdown", "sweep_to_markdown", "run_to_html", "compare_to_html"]
