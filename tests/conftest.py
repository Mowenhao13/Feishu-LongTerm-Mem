"""Pytest configuration: add src/ to sys.path for imports to work correctly.

This avoids the PYTHONPATH=src issue where src/types.py shadows stdlib types module.
"""
import sys
from pathlib import Path

import pytest

from src.llm.config import LLMConfig

# Add src/ to sys.path (not PYTHONPATH) so imports like "from node.xxx import YYY" work
# while stdlib "types" module is already loaded and not shadowed.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ==================== LLM Test Configuration ====================
# SYSU AI Gateway — used by tests that need real LLM inference.
# To use in a test:
#   def test_foo(sysu_llm):
#       result = sysu_llm.chat([{"role": "user", "content": "hello"}])
#
SYSU_API_KEY = "sk-ZUWsguPrUGRtd6txjXwh6VtDaTm1Kjni2wMW0mbKGtTdzQ1A"
SYSU_BASE_URL = "https://aigw.sysu.edu.cn/v1"
SYSU_MODEL_ID = "deepseek-local"


@pytest.fixture(scope="session")
def sysu_llm():
    """Return an LLMClient configured for the SYSU AI Gateway (deepseek-local).

    Uses the OpenAI SDK under the hood. Intended for integration tests that
    need real LLM calls; unit tests should mock the client or provide a
    lightweight config instead.
    """
    from src.llm.client import LLMClient

    config = LLMConfig(
        model_name=SYSU_MODEL_ID,
        base_url=SYSU_BASE_URL,
        api_key=SYSU_API_KEY,
        max_tokens=4096,
        temperature=0.1,
    )
    return LLMClient(config=config)