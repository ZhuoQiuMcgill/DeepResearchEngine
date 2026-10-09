"""Agent selection shared by baselines 7–12; role revisions are method pins."""
from .parallel_workflow import ParallelBaselineMethod


class SelectionBaselineMethod(ParallelBaselineMethod):
    agent_selection = True

    def __init__(self, revision=7):
        super().__init__(revision=revision)
        if revision >= 12:
            self.defaults = {**self.defaults, "max_sources": 40}
