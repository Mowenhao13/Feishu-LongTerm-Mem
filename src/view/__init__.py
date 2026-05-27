import os

from .syncer import BaseViewSyncer
from .client import BaseViewClient


def is_bitable_enabled() -> bool:
    return os.environ.get("BITABLE_ENABLED", "").strip().lower() == "true"


__all__ = ["BaseViewSyncer", "BaseViewClient", "is_bitable_enabled"]