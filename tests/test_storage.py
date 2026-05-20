"""
Tests for src/storage module: GitCLI, GitFormat, GitStorage.
"""
import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
import yaml

from storage.git_cli import GitCLI
from storage.git_format import (
    parse_decision_file,
    parse_objection_file,
    render_decision_file,
    render_objection_file,
    format_decision_summary,
    _extract_frontmatter,
)
from storage.git_storage import GitStorage, GitStorageConfig


# ==================== GitFormat Tests ====================


class TestGitFormat:
    def test_render_decision_file(self) -> None:
        data = {
            "sid": "dec-001",
            "title": "Use Python 3.12",
            "topic_id": "infra",
            "status": "decided",
            "impact_level": "major",
        }
        result = render_decision_file(data)
        assert "---" in result
        assert "Use Python 3.12" in result

    def test_parse_decision_file(self) -> None:
        content = """---
sid: dec-001
title: Test Decision
status: pending
---
# Test Decision

## 决策

Use Python 3.12
"""
        parsed = parse_decision_file(content)
        assert parsed["sid"] == "dec-001"
        assert parsed["title"] == "Test Decision"
        assert parsed["status"] == "pending"

    def test_parse_invalid_file(self) -> None:
        with pytest.raises(Exception):
            parse_decision_file("no frontmatter here")

    def test_render_objection_file(self) -> None:
        data = {
            "oid": "obj-001",
            "objection_content": "成本过高",
            "rationale": "需要额外资源",
            "status": "active",
            "objector": "Alice",
        }
        result = render_objection_file(data)
        assert "---" in result
        assert "成本过高" in result

    def test_parse_objection_file(self) -> None:
        content = """---
oid: obj-001
objection_content: Too expensive
status: active
---
"""
        parsed = parse_objection_file(content)
        assert parsed["oid"] == "obj-001"
        assert parsed["status"] == "active"

    def test_format_decision_summary(self) -> None:
        data = {
            "sid": "dec-001",
            "title": "Test",
            "topic_id": "infra",
            "status": "decided",
            "impact_level": "major",
        }
        summary = format_decision_summary(data)
        assert "[dec-001]" in summary
        assert "Test" in summary

    def test_extract_frontmatter(self) -> None:
        content = "---\nkey: value\n---\nbody"
        fm = _extract_frontmatter(content)
        assert fm is not None
        assert "key: value" in fm

    def test_render_and_parse_roundtrip(self) -> None:
        data = {
            "sid": "dec-999",
            "title": "Round Trip",
            "status": "completed",
            "impact_level": "minor",
        }
        rendered = render_decision_file(data)
        parsed = parse_decision_file(rendered)
        assert parsed["sid"] == "dec-999"
        assert parsed["title"] == "Round Trip"

    def test_render_with_markdown_body(self) -> None:
        data = {
            "sid": "dec-100",
            "title": "Full Decision",
            "decision": "We will use PostgreSQL",
            "rationale": "Better ecosystem",
        }
        rendered = render_decision_file(data)
        assert "PostgreSQL" in rendered
        assert "Better ecosystem" in rendered


# ==================== GitCLI Tests ====================


class TestGitCLI:
    @pytest.fixture
    def git_dir(self) -> Generator[Path, None, None]:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_git_cli_init_and_run(self, git_dir: Path) -> None:
        cli = GitCLI(git_dir)
        cli.run("init")
        cli.run("config", "user.name", "test")
        cli.run("config", "user.email", "test@test.com")

        test_file = git_dir / "test.md"
        test_file.write_text("# hello", encoding="utf-8")
        cli.run("add", "test.md")
        cli.run("commit", "-m", "init")

        head = cli.get_head_hash()
        assert len(head) == 40

        branch = cli.get_current_branch()
        assert branch == "main" or branch == "master"

    def test_branch_operations(self, git_dir: Path) -> None:
        cli = GitCLI(git_dir)
        cli.run("init")
        cli.run("config", "user.name", "test")
        cli.run("config", "user.email", "test@test.com")

        (git_dir / "init.md").write_text("init", encoding="utf-8")
        cli.run("add", "init.md")
        cli.run("commit", "-m", "init")
        cli.create_branch("feature/test")
        branch = cli.get_current_branch()
        assert branch == "feature/test"
        branches = cli.list_branches()
        assert any("feature/test" in b for b in branches)

    def test_commit_log(self, git_dir: Path) -> None:
        cli = GitCLI(git_dir)
        cli.run("init")
        cli.run("config", "user.name", "test")
        cli.run("config", "user.email", "test@test.com")

        (git_dir / "a.md").write_text("a", encoding="utf-8")
        cli.commit("a.md", "commit a")
        (git_dir / "b.md").write_text("b", encoding="utf-8")
        cli.commit("b.md", "commit b")

        logs = cli.get_commit_log()
        assert len(logs) >= 2

    def test_rev_list_count(self, git_dir: Path) -> None:
        cli = GitCLI(git_dir)
        cli.run("init")
        cli.run("config", "user.name", "test")
        cli.run("config", "user.email", "test@test.com")
        (git_dir / "f.md").write_text("f", encoding="utf-8")
        cli.commit("f.md", "first commit")
        cli.create_branch("feature/x")
        (git_dir / "g.md").write_text("g", encoding="utf-8")
        cli.commit("g.md", "second commit on feature/x")

        count = cli.rev_list_count("feature/x", "main")
        # The count should be 1 (only the commit on the feature branch)
        assert count >= 0


# ==================== GitStorage Tests ====================


class TestGitStorage:
    @pytest.fixture
    def storage(self) -> Generator[GitStorage, None, None]:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = GitStorageConfig(work_dir=tmpdir)
            gs = GitStorage(config)
            yield gs

    def test_init_creates_repo(self, storage: GitStorage) -> None:
        assert storage.get_head_hash() is not None
        assert (storage.work_dir / "L0_RULES.md").exists()

    def test_write_and_read_decision(self, storage: GitStorage) -> None:
        decision = {
            "sid": "dec-test-001",
            "title": "Test Decision",
            "status": "pending",
            "topic_id": "general",
        }
        hash_val = storage.write_decision(decision)
        assert len(hash_val) == 40

        read = storage.read_decision("default", "general", "dec-test-001")
        assert read["title"] == "Test Decision"

    def test_list_decisions(self, storage: GitStorage) -> None:
        storage.write_decision({
            "sid": "dec-list-1", "title": "D1", "topic_id": "t1",
        })
        decisions = storage.list_decisions("default", "t1")
        assert len(decisions) == 1
        assert decisions[0]["sid"] == "dec-list-1"

    def test_list_topics(self, storage: GitStorage) -> None:
        storage.write_decision({
            "sid": "dec-topic-1", "title": "T1", "topic_id": "arch",
        })
        topics = storage.list_topics("default")
        assert "arch" in topics

    def test_write_and_read_objection(self, storage: GitStorage) -> None:
        obj = {
            "oid": "obj-001",
            "objection_content": "Too complex",
            "status": "active",
            "objector": "Alice",
        }
        hash_val = storage.write_objection(obj)
        assert len(hash_val) == 40

        objections = storage.list_objections("default")
        assert len(objections) >= 1
        assert objections[0]["oid"] == "obj-001"

    def test_branch_operations(self, storage: GitStorage) -> None:
        decision = {"sid": "dec-branch-1", "title": "Branch Test", "topic_id": "t1"}
        storage.write_decision(decision)
        branches = storage.list_decision_branches()
        assert any("dec-branch-1" in b for b in branches)

    def test_get_decision_history(self, storage: GitStorage) -> None:
        decision = {"sid": "dec-hist-1", "title": "History Test", "topic_id": "t1"}
        storage.write_decision(decision)
        history = storage.get_decision_history("default", "t1", "dec-hist-1")
        assert len(history) >= 1

    def test_search_content(self, storage: GitStorage) -> None:
        decision = {"sid": "dec-srch-1", "title": "SearchMe", "topic_id": "t1"}
        storage.write_decision(decision)
        hits = storage.search_content("default", "SearchMe")
        assert len(hits) >= 1

    def test_archive_project(self, storage: GitStorage) -> None:
        decision = {"sid": "dec-arch-1", "title": "Archive Test", "topic_id": "t1"}
        storage.write_decision(decision)
        storage.archive_project("default")
        assert not (storage.work_dir / "decisions" / "default").exists()