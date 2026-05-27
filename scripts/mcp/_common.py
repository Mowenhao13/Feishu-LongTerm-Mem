"""公共模块：路径设置 + 导入所有 MCP 工具函数"""

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# 确保 graph 已加载
from src.mcp_server.server import _loader
_loader.ensure_loaded()

# 导入所有工具函数
from src.mcp_server.server import (
    list_decisions,
    topic,
    search,
    decision,
    timeline,
    list_topics,
    get_relations,
    stats,
    hot_decisions,
    forgotten_decisions,
    related_decisions,
    recent_decisions,
    fulltext_search,
    git_history,
    git_search,
    git_blame,
    conflict_list,
    objection_list,
    decision_card,
    decision_history,
    create_decision,
    update_decision,
    confirm_decision,
    reject_decision,
    revert_decision,
    resolve_conflict,
    extract_decision,
    classify_topic,
    detect_crosstopic,
    check_conflict,
    evaluate_dedup,
    resolve_conflict_action,
    extract_and_create,
    refresh,
)