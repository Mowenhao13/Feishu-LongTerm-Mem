from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from src.llm.client import LLMClient

mcp = FastMCP(
    "Feishu Memory Agent",
    instructions="Feishu Memory Agent 提供决策记忆管理功能，包括搜索、分类、冲突检测等",
)


_mcp_llm_client: Optional[LLMClient] = None
_DEFAULT_STORAGE_PATH = "data"
_DEFAULT_PROJECT = "feishu-mem"


def set_llm_client(client: LLMClient) -> None:
    global _mcp_llm_client
    _mcp_llm_client = client


def get_llm_client() -> LLMClient:
    global _mcp_llm_client
    if _mcp_llm_client is None:
        _mcp_llm_client = LLMClient()
    return _mcp_llm_client


def _get_storage() -> Any:
    from src.storage.git_storage import GitStorage, GitStorageConfig
    return GitStorage(GitStorageConfig(work_dir=_DEFAULT_STORAGE_PATH))


def _get_all_decisions() -> list[dict[str, Any]]:
    storage = _get_storage()
    topics = storage.list_topics(_DEFAULT_PROJECT)
    all_decisions: list[dict[str, Any]] = []
    for t in topics:
        all_decisions.extend(storage.list_decisions(_DEFAULT_PROJECT, t))
    return all_decisions


@mcp.tool(
    name="search",
    description="搜索记忆系统中的决策记录，支持关键词、议题过滤",
)
def search(query: str, topic: str = "", limit: int = 20) -> str:
    from src.storage.git_cli import GitCLIError

    storage = _get_storage()
    try:
        results = storage.search_content(_DEFAULT_PROJECT, query)
    except GitCLIError:
        return "未找到匹配的决策记录"
    if not results:
        return "未找到匹配的决策记录"

    lines = ["## 搜索结果\n"]
    for r in results[:limit]:
        lines.append(f"- {r.file}:{r.line_num}: {r.content}")
    return "\n".join(lines)


@mcp.tool(
    name="decision",
    description="获取单个决策的详细信息",
)
def decision(sdr_id: str, topic: str = "") -> str:
    if not topic:
        all_decisions = _get_all_decisions()
        for d in all_decisions:
            if d.get("sid") == sdr_id:
                topic = d.get("topic_id", "")
                break

    if not topic:
        return f"未找到决策: {sdr_id}"

    storage = _get_storage()
    d = storage.read_decision(_DEFAULT_PROJECT, topic, sdr_id)
    if d is None:
        return f"未找到决策: {sdr_id}"

    lines = [
        f"## {d.get('sid', 'unknown')}",
        f"- **SDR ID**: {d.get('sid', '')}",
        f"- **议题**: {d.get('topic_id', topic)}",
        f"- **状态**: {d.get('status', '')}",
        f"- **摘要**: {d.get('summary', '')}",
    ]
    full = d.get("full_text", "")
    if full:
        lines.append(f"- **全文**: {full[:500]}...")
    elif d.get("summary"):
        lines.append(f"- **全文**: {d['summary']}")
    return "\n".join(lines)


@mcp.tool(
    name="extract_decision",
    description="从文本内容中智能提取决策信息",
)
def extract_decision(content: str, topics: Optional[list[str]] = None) -> str:
    from src.prompts.decision_prompts import DECISION_EXTRACTION_PROMPT_SHORT

    prompt = DECISION_EXTRACTION_PROMPT_SHORT.format(conversation_text=content)
    client = get_llm_client()

    try:
        result = client.chat_json(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
        )
        has_decision = result.get("has_decisions", False) if isinstance(result.get("has_decisions"), bool) else False
        if not has_decision:
            return "未检测到决策信息"

        decisions = result.get("decisions", [])
        if not decisions:
            return "未检测到决策信息"

        lines = ["## 决策提取结果\n"]
        for d in decisions[:3]:
            lines.append(f"- **标题**: {d.get('title', 'untitled')}")
            lines.append(f"  **决策**: {d.get('content', '')}")
            lines.append(f"  **置信度**: {d.get('confidence', 0)}")
        return "\n".join(lines)
    except Exception as e:
        return f"提取失败: {e}"


@mcp.tool(
    name="classify_topic",
    description="将决策智能分类到正确的议题",
)
def classify_topic(decision_text: str, topics: list[str]) -> str:
    from src.prompts.topic_prompts import CLASSIFICATION_PROMPT

    client = get_llm_client()
    topics_str = ", ".join(topics)

    try:
        result = client.chat_json(
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": f"决策内容: {decision_text}\\n候选议题: {topics_str}"},
            ],
        )
        lines = ["## 议题分类结果\n"]
        lines.append(f"- **建议议题**: {result.get('topic', '未知')}")
        lines.append(f"- **置信度**: {result.get('confidence', 0)}")
        lines.append(f"- **说明**: {result.get('reasoning', '')}")
        return "\n".join(lines)
    except Exception as e:
        return f"分类失败: {e}"


@mcp.tool(
    name="detect_crosstopic",
    description="检测决策是否会影响多个议题",
)
def detect_crosstopic(title: str, decision_text: str, candidate_topics: list[str]) -> str:
    from src.prompts.topic_prompts import CROSS_TOPIC_DETECT_PROMPT

    client = get_llm_client()
    topics_str = ", ".join(candidate_topics)

    try:
        result = client.chat_json(
            messages=[
                {"role": "system", "content": CROSS_TOPIC_DETECT_PROMPT},
                {"role": "user", "content": f"决策标题: {title}\\n决策内容: {decision_text}\\n候选议题: {topics_str}"},
            ],
        )
        is_cross = result.get("is_cross_topic", False)
        lines = ["## 跨议题检测结果\n"]
        if is_cross:
            lines.append("⚠️ **检测到跨议题影响**")
            refs = result.get("cross_topic_refs", [])
            if refs:
                lines.append(f"- **受影响议题**: {', '.join(refs)}")
        else:
            lines.append("✅ **无跨议题影响**")
        lines.append(f"\\n- **置信度**: {result.get('confidence', 0)}")
        return "\n".join(lines)
    except Exception as e:
        return f"检测失败: {e}"


@mcp.tool(
    name="check_conflict",
    description="评估两个决策之间是否存在冲突",
)
def check_conflict(decision_a: str, decision_b: str) -> str:
    from src.prompts.decision_prompts import CONFLICT_ASSESSMENT_PROMPT

    client = get_llm_client()

    try:
        result = client.chat_json(
            messages=[
                {"role": "system", "content": CONFLICT_ASSESSMENT_PROMPT},
                {"role": "user", "content": f"决策A: {decision_a}\\n\\n决策B: {decision_b}"},
            ],
        )
        lines = ["## 冲突评估结果\n"]
        lines.append(f"- **冲突分数**: {result.get('contradiction_score', 0)}")
        lines.append(f"- **冲突类型**: {result.get('contradiction_type', 'unknown')}")
        lines.append(f"- **描述**: {result.get('description', '')}")
        lines.append(f"- **建议**: {result.get('suggestion', '')}")
        return "\n".join(lines)
    except Exception as e:
        return f"冲突评估失败: {e}"


@mcp.tool(
    name="list_topics",
    description="列出所有议题",
)
def list_topics(project: str = "") -> str:
    storage = _get_storage()
    topics = storage.list_topics(project or _DEFAULT_PROJECT)

    lines = ["## 所有议题\n"]
    if not topics:
        lines.append("暂无议题")
    else:
        for t in topics:
            lines.append(f"- {t}")
    return "\n".join(lines)


@mcp.tool(
    name="stats",
    description="获取系统统计信息",
)
def stats() -> str:
    all_decisions = _get_all_decisions()
    storage = _get_storage()
    topics = storage.list_topics(_DEFAULT_PROJECT)

    lines = ["## 系统统计\n"]
    lines.append(f"- **总决策数**: {len(all_decisions)}")
    lines.append(f"- **议题数**: {len(topics)}")
    return "\n".join(lines)


@mcp.tool(
    name="timeline",
    description="获取决策历史时间线",
)
def timeline() -> str:
    all_decisions = _get_all_decisions()

    lines = ["## 决策时间线\n"]
    if not all_decisions:
        lines.append("暂无决策记录")
    else:
        for d in all_decisions:
            sid = d.get("sid", "unknown")
            topic = d.get("topic_id", "")
            summary = d.get("summary", "")
            status = d.get("status", "")
            lines.append(f"- [{status}] {sid}: {summary} (议题: {topic})")
    return "\n".join(lines)


def run_server(transport: str = "stdio") -> None:
    mcp.run(transport=transport)


if __name__ == "__main__":
    run_server()