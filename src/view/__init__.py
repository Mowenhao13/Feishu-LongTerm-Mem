import os
from .task_syncer import TaskViewSyncer


def is_task_view_enabled() -> bool:
    return os.environ.get("TASK_ENABLED", "").strip().lower() == "true"


__all__ = ["TaskViewSyncer", "is_task_view_enabled"]