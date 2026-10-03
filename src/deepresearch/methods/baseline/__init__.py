"""Formal baseline revisions, including parallel source distillation."""
from .workflow import BaselineMethod, EnglishBaselineMethod, ExpandedBaselineMethod, definition
from .parallel_workflow import ParallelBaselineMethod

__all__ = ["BaselineMethod", "EnglishBaselineMethod", "ExpandedBaselineMethod", "ParallelBaselineMethod", "definition"]
