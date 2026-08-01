from __future__ import annotations

import json
import pytest

from src.mcp_server.server import mcp, search, decision, list_topics, stats


class TestMCPToolDefinitions:
    def test_search_tool_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "search" in names

    def test_decision_tool_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "decision" in names

    def test_extract_decision_tool_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "extract_decision" in names

    def test_classify_topic_tool_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "classify_topic" in names

    def test_detect_crosstopic_tool_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "detect_crosstopic" in names

    def test_check_conflict_tool_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "check_conflict" in names

    def test_list_topics_tool_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "list_topics" in names

    def test_stats_tool_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "stats" in names

class TestMCPToolDescriptions:
    def test_search_description_contains_search(self):
        tools = mcp._tool_manager.list_tools()
        search_tool = next(t for t in tools if t.name == "search")
        assert "搜索" in search_tool.description

    def test_extract_decision_description_contains_extract(self):
        tools = mcp._tool_manager.list_tools()
        extract_tool = next(t for t in tools if t.name == "extract_decision")
        assert "提取" in extract_tool.description


class TestMCPToolInputSchema:
    def test_search_has_query_param(self):
        tools = mcp._tool_manager.list_tools()
        search_tool = next(t for t in tools if t.name == "search")
        props = search_tool.parameters.get("properties", {})
        assert "query" in props
        assert props["query"]["type"] == "string"

    def test_decision_has_sid_param(self):
        tools = mcp._tool_manager.list_tools()
        decision_tool = next(t for t in tools if t.name == "decision")
        props = decision_tool.parameters.get("properties", {})
        assert "sid" in props
        assert props["sid"]["type"] == "string"


class TestMCPToolExecution:
    def test_search_returns_json_string(self):
        result = search(query="nonexistent_keyword_xyz")
        data = json.loads(result)
        assert "results" in data
        assert "total" in data

    def test_decision_not_found(self):
        result = decision(sid="nonexistent_sdr")
        data = json.loads(result)
        assert "error" in data

    def test_list_topics_returns_string(self):
        result = list_topics()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_stats_returns_string(self):
        result = stats()
        data = json.loads(result)
        assert "total_decisions" in data


class TestMCPServerInfo:
    def test_server_name(self):
        assert mcp.name == "Feishu Memory Agent"

    def test_server_instructions(self):
        assert "决策记忆" in mcp.instructions



    