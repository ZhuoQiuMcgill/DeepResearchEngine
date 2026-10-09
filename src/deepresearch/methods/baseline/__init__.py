"""Formal baseline revisions, including parallel source distillation."""
from .workflow import BaselineMethod, EnglishBaselineMethod, ExpandedBaselineMethod, definition
from .parallel_workflow import ParallelBaselineMethod
from .selection_workflow import SelectionBaselineMethod

__all__ = ["BaselineMethod", "EnglishBaselineMethod", "ExpandedBaselineMethod", "ParallelBaselineMethod", "SelectionBaselineMethod", "definition"]
