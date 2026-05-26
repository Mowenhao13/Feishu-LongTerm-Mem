"""
文档检测器/适配器/提取器测试

不依赖飞书 API，使用本地文件模拟
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time

import pytest

from src.adapter.doc_adapter import DocAdapter, DocDebounceTracker
from src.detect.doc_detector import DocDetector
from src.detect.types import AdapterType


# ==================== 防抖追踪器测试 ====================


class TestDocDebounceTracker:
    def test_on_document_changed(self, tmp_path):
        tracker = DocDebounceTracker(debounce_window=1, state_dir=str(tmp_path))
        tracker.on_document_changed("doc-001", "hash1")
        state = tracker.get_state("doc-001")
        assert state is not None
        assert state["doc_token"] == "doc-001"

    def test_can_process_now_fresh(self, tmp_path):
        tracker = DocDebounceTracker(debounce_window=30, state_dir=str(tmp_path))
        ok, reason = tracker.can_process_now("unknown-doc")
        assert ok is True

    def test_can_process_now_debouncing(self, tmp_path):
        tracker = DocDebounceTracker(debounce_window=30, state_dir=str(tmp_path))
        tracker.on_document_changed("doc-001", "hash1")
        ok, reason = tracker.can_process_now("doc-001")
        assert ok is False
        assert "debounce" in reason

    def test_mark_processed(self, tmp_path):
        tracker = DocDebounceTracker(debounce_window=0, state_dir=str(tmp_path))
        tracker.on_document_changed("doc-001", "hash1")
        ok, _ = tracker.can_process_now("doc-001")
        assert ok is True
        tracker.mark_processed("doc-001", "hash1")
        ok, _ = tracker.can_process_now("doc-001")
        assert ok is False

    def test_get_ready_docs(self, tmp_path):
        tracker = DocDebounceTracker(debounce_window=0, state_dir=str(tmp_path))
        tracker.on_document_changed("doc-001", "hash1")
        ready = tracker.get_ready_docs()
        assert "doc-001" in ready


# ==================== 文档适配器测试 ====================


class TestDocAdapter:
    @pytest.fixture
    def temp_docs_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def write_doc(self, docs_dir: str, name: str, content: str) -> str:
        filepath = os.path.join(docs_dir, name)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def test_detect_new_doc(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)
        result = adapter.detect()
        assert result.has_changes is False

        self.write_doc(temp_docs_dir, "test-001.md", "# Test Doc\nHello")
        result = adapter.detect()
        assert result.has_changes is True
        assert len(result.changes) == 1
        assert result.changes[0].type == "doc_created"
        assert result.changes[0].doc_token == "test-001"

    def test_detect_updated_doc(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)
        self.write_doc(temp_docs_dir, "test-002.md", "# Version 1\nInitial")
        adapter.detect()

        time.sleep(0.1)
        self.write_doc(temp_docs_dir, "test-002.md", "# Version 2\nUpdated")
        result = adapter.detect()
        assert result.has_changes is True
        assert result.changes[0].type == "doc_updated"

    def test_detect_no_change(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)
        self.write_doc(temp_docs_dir, "test-003.md", "Static content")
        result1 = adapter.detect()
        assert result1.has_changes is True

        result2 = adapter.detect()
        assert result2.has_changes is False

    def test_multi_docs(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)
        self.write_doc(temp_docs_dir, "doc-a.md", "Doc A")
        self.write_doc(temp_docs_dir, "doc-b.md", "Doc B")

        result = adapter.detect()
        assert result.has_changes is True
        assert len(result.changes) == 2

    def test_fetch_content(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir)
        self.write_doc(temp_docs_dir, "fetch-test.md", "# Fetched\nContent here")
        content = adapter.fetch_content("fetch-test")
        assert "# Fetched" in content

    def test_fetch_content_not_found(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir)
        content = adapter.fetch_content("nonexistent")
        assert content == ""

    def test_list_docs(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir)
        assert adapter.list_docs() == []

        self.write_doc(temp_docs_dir, "a.md", "A")
        self.write_doc(temp_docs_dir, "b.md", "B")
        docs = adapter.list_docs()
        assert len(docs) == 2
        assert "a" in docs

    def test_name(self):
        adapter = DocAdapter()
        assert adapter.name == "lark_doc"


# ==================== 文档检测器测试 ====================


class TestDocDetector:
    @pytest.fixture
    def temp_docs_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def write_doc(self, docs_dir: str, name: str, content: str) -> str:
        filepath = os.path.join(docs_dir, name)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def test_detect_and_create_jobs(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)
        detector = DocDetector(adapter=adapter)

        assert detector.name == "lark_doc"

        self.write_doc(temp_docs_dir, "decision-doc.md", """
# 技术选型

## 背景
项目需要选择前端框架。

## 决定
最终确定使用 React + TypeScript。

## 理由
团队熟悉度高，生态完善。
""")
        result = detector.detect()
        assert result.has_changes is True
        # 信号检测应在 meta 中标注
        for change in result.changes:
            assert "signal_score" in change.meta
            assert "signal_level" in change.meta
            assert "is_decision" in change.meta
            assert "doc_type" in change.meta

        jobs = detector.create_jobs(result)
        assert len(jobs) == 1
        assert jobs[0].doc_token == "decision-doc"
        assert jobs[0].adapter == AdapterType.DOCS

    def test_no_changes(self, temp_docs_dir):
        adapter = DocAdapter(docs_dir=temp_docs_dir)
        detector = DocDetector(adapter=adapter)
        result = detector.detect()
        assert result.has_changes is False

        jobs = detector.create_jobs(result)
        assert len(jobs) == 0


# ==================== 单文档与多文档场景测试 ====================


class TestDocScenarios:
    @pytest.fixture
    def temp_docs_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def write_doc(self, docs_dir: str, name: str, content: str):
        filepath = os.path.join(docs_dir, name)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def test_single_document_creation(self, temp_docs_dir):
        """单文档创建场景"""
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)

        self.write_doc(temp_docs_dir, "arch-decision.md", """
# 数据库选型

**决定**: 使用 PostgreSQL 15

**理由**: 事务支持完善，社区活跃
""")
        result = adapter.detect()
        assert result.has_changes is True
        assert len(result.changes) == 1
        assert result.changes[0].doc_token == "arch-decision"
        assert result.changes[0].type == "doc_created"

    def test_multi_document_creation(self, temp_docs_dir):
        """多文档创建场景 — 同时创建多个文档"""
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)

        self.write_doc(temp_docs_dir, "doc1.md", "# Doc 1\nDecision A")
        self.write_doc(temp_docs_dir, "doc2.md", "# Doc 2\nDecision B")
        self.write_doc(temp_docs_dir, "doc3.md", "# Doc 3\nDecision C")

        result = adapter.detect()
        assert result.has_changes is True
        assert len(result.changes) == 3
        tokens = [c.doc_token for c in result.changes]
        assert "doc1" in tokens
        assert "doc2" in tokens
        assert "doc3" in tokens

    def test_document_update_flow(self, temp_docs_dir):
        """文档更新场景 — 创建后修改"""
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)

        self.write_doc(temp_docs_dir, "flow-doc.md", "# Initial\nVersion 1")
        adapter.detect()

        self.write_doc(temp_docs_dir, "flow-doc.md", "# Updated\nVersion 2")
        result = adapter.detect()
        assert result.has_changes is True
        assert result.changes[0].type == "doc_updated"

    def test_mixed_created_updated(self, temp_docs_dir):
        """混合场景 — 新文档 + 已更新文档"""
        adapter = DocAdapter(docs_dir=temp_docs_dir, polling_interval=1, debounce_window=0)

        self.write_doc(temp_docs_dir, "existing.md", "Existing")
        adapter.detect()

        # 同时：修改已有 + 新增
        self.write_doc(temp_docs_dir, "existing.md", "Existing version 2")
        self.write_doc(temp_docs_dir, "new-doc.md", "Brand new")

        result = adapter.detect()
        assert result.has_changes is True
        assert len(result.changes) == 2

        change_types = {c.doc_token: c.type for c in result.changes}
        assert change_types["existing"] == "doc_updated"
        assert change_types["new-doc"] == "doc_created"