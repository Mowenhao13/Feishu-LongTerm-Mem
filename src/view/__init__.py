import os
from .task_syncer import TaskViewSyncer
from .task_client import TaskViewClient


def is_task_view_enabled() -> bool:
    return os.environ.get("TASK_ENABLED", "").strip().lower() == "true"


__all__ = ["TaskViewSyncer", "TaskViewClient", "is_task_view_enabled"]