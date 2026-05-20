"""
Git Storage - High-level decision CRUD with git backend.

Translates ref/git/git_storage.go (removing bitable-related parts).

File structure:
  {work_dir}/
    decisions/{project}/{topic}/{SDRID}.md
    objections/{project}/{topic}/{OID}.md
    L0_RULES.md
    archive/{project}/
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

from .git_cli import BlameEntry, CommitLogEntry, GitCLI, SearchHit
from .git_format import (
    format_decision_summary,
    parse_decision_file,
    parse_objection_file,
    render_decision_file,
    render_objection_file,
)

logger = get_logger(__name__)

_BRANCH_PREFIX_DECISION = "decision/"


@dataclass
class GitStorageConfig:
    work_dir: str = "data"
    remote: str = ""
    auto_push: bool = False
    branch: str = "main"
    git_user_name: str = "feishu-mem"
    git_user_email: str = "feishu-mem@example.com"


class GitStorageError(Exception):
    pass


class GitStorage:
    """High-level CRUD operations for decision/objection storage using git."""

    def __init__(self, config: GitStorageConfig) -> None:
        self._config = config
        self._work_dir = Path(config.work_dir).resolve()
        self._cli = GitCLI(str(self._work_dir))
        self._init_repo()

    @property
    def cli(self) -> GitCLI:
        return self._cli

    @property
    def work_dir(self) -> Path:
        return self._work_dir

    # ==================== Init ====================

    def _init_repo(self) -> None:
        self._work_dir.mkdir(parents=True, exist_ok=True)
        git_dir = self._work_dir / ".git"
        if git_dir.exists():
            return

        self._cli.run("init")
        self._cli.run("config", "user.name", self._config.git_user_name)
        self._cli.run("config", "user.email", self._config.git_user_email)

        rules_path = self._work_dir / "L0_RULES.md"
        if not rules_path.exists():
            rules_path.write_text("# L0 Rules\n\n", encoding="utf-8")
            self._cli.run("add", "L0_RULES.md")
            self._cli.run("commit", "-m", "Initial commit: L0 rules")

        dummy_path = self._work_dir / "dummy.md"
        if not dummy_path.exists():
            dummy = {
                "sid": "dummy",
                "title": "Root Dummy",
                "status": "completed",
                "version": 0,
            }
            content = render_decision_file(dummy)
            dummy_path.write_text(content, encoding="utf-8")
            self._cli.run("add", "dummy.md")
            self._cli.run("commit", "-m", "dummy: Root Dummy (v0)")

    # ==================== Decision CRUD ====================

    def write_decision(self, decision: Dict[str, Any]) -> str:
        branch = self._get_decision_branch(decision)
        self._ensure_decision_branch(branch)
        self._switch_to_branch(branch)

        project = decision.get("project", "default")
        topic = decision.get("topic_id", "") or decision.get("topic", "general")
        sid = decision.get("sid", "") or decision.get("id", "")
        if not sid:
            raise GitStorageError("decision must have 'sid' or 'id' field")

        decision_dir = self._work_dir / "decisions" / project / topic
        decision_dir.mkdir(parents=True, exist_ok=True)

        path = decision_dir / f"{sid}.md"

        version = self._cli.rev_list_count(branch, self._config.branch)
        if version > 0:
            decision["version"] = version

        content = render_decision_file(decision)
        path.write_text(content, encoding="utf-8")

        rel_path = str(path.relative_to(self._work_dir))
        msg = self._format_commit_message("decision", decision)
        commit_hash = self._cli.commit(rel_path, msg)

        decision["git_commit_hash"] = commit_hash

        if self._config.auto_push and self._config.remote:
            self._push()

        return commit_hash

    def read_decision(self, project: str, topic: str, sid: str) -> Dict[str, Any]:
        path = self._work_dir / "decisions" / project / topic / f"{sid}.md"
        if not path.exists():
            raise GitStorageError(f"decision {sid} not found at {path}")
        data = path.read_text(encoding="utf-8")
        return parse_decision_file(data)

    def list_decisions(self, project: str, topic: str) -> List[Dict[str, Any]]:
        decision_dir = self._work_dir / "decisions" / project / topic
        if not decision_dir.exists():
            return []
        decisions = []
        for f in sorted(decision_dir.iterdir()):
            if f.suffix == ".md":
                sid = f.stem
                try:
                    decisions.append(self.read_decision(project, topic, sid))
                except GitStorageError:
                    continue
        return decisions

    def list_topics(self, project: str) -> List[str]:
        project_dir = self._work_dir / "decisions" / project
        if not project_dir.exists():
            return []
        return sorted(
            e.name for e in project_dir.iterdir() if e.is_dir()
        )

    # ==================== Objection CRUD ====================

    def write_objection(self, objection: Dict[str, Any]) -> str:
        project = objection.get("project", "default")
        topic = objection.get("topic_id", "") or objection.get("topic", "general")
        oid = objection.get("oid", "") or objection.get("OID", "")
        if not oid:
            raise GitStorageError("objection must have 'oid' field")

        objection_dir = self._work_dir / "objections" / project / topic
        objection_dir.mkdir(parents=True, exist_ok=True)

        path = objection_dir / f"{oid}.md"
        content = render_objection_file(objection)
        path.write_text(content, encoding="utf-8")

        rel_path = str(path.relative_to(self._work_dir))
        msg = f"objection({topic}): {oid} - {objection.get('objection_content', '')}"
        commit_hash = self._cli.commit(rel_path, msg)

        return commit_hash

    def list_objections(self, project: str, topic: str = "general") -> List[Dict[str, Any]]:
        obj_dir = self._work_dir / "objections" / project / topic
        if not obj_dir.exists():
            return []
        objections = []
        for f in sorted(obj_dir.iterdir()):
            if f.suffix == ".md":
                try:
                    data = f.read_text(encoding="utf-8")
                    objections.append(parse_objection_file(data))
                except Exception:
                    continue
        return objections

    # ==================== Git Operations ====================

    def get_head_hash(self) -> str:
        return self._cli.get_head_hash()

    def get_file_hash(self, project: str, topic: str, sid: str) -> str:
        path = f"decisions/{project}/{topic}/{sid}.md"
        return self._cli.run("rev-parse", f"HEAD:{path}")

    def push(self) -> None:
        if not self._config.remote:
            return
        self._cli.run("push", "-u", "origin", self._config.branch)

    def pull(self) -> None:
        self._cli.run("pull", "origin", self._config.branch)

    def create_branch(self, branch_name: str) -> None:
        self._cli.create_branch(branch_name)

    def switch_branch(self, branch_name: str) -> None:
        self._cli.switch_branch(branch_name)

    def merge_branch(self, branch_name: str) -> None:
        self._cli.merge_branch(branch_name)

    def get_current_branch(self) -> str:
        return self._cli.get_current_branch()

    def list_branches(self) -> List[str]:
        return self._cli.list_branches()

    def list_decision_branches(self) -> List[str]:
        all_branches = self.list_branches()
        return [b for b in all_branches if b.startswith(_BRANCH_PREFIX_DECISION)]

    def read_decision_from_branch(self, branch: str, sid: str) -> Dict[str, Any]:
        files = self._cli.ls_tree(branch)
        for f in files:
            if f.endswith(f"/{sid}.md"):
                content = self._cli.read_file_at_commit(f, branch)
                return parse_decision_file(content)
        raise GitStorageError(f"decision {sid} not found on branch {branch}")

    def get_commit_log(self, path: str = "", limit: int = 0) -> List[CommitLogEntry]:
        return self._cli.get_commit_log(path, limit)

    def blame_decision(self, project: str, topic: str, sid: str) -> List[BlameEntry]:
        path = f"decisions/{project}/{topic}/{sid}.md"
        return self._cli.git_blame(path)

    def search_content(self, project: str, query: str) -> List[SearchHit]:
        path = f"decisions/{project}" if project else "decisions"
        return self._cli.git_grep(query, path)

    def read_decision_at_commit(
        self, project: str, topic: str, sid: str, commit_hash: str
    ) -> Dict[str, Any]:
        path = f"decisions/{project}/{topic}/{sid}.md"
        content = self._cli.read_file_at_commit(path, commit_hash)
        return parse_decision_file(content)

    def get_decision_history(
        self, project: str, topic: str, sid: str
    ) -> List[CommitLogEntry]:
        path = f"decisions/{project}/{topic}/{sid}.md"
        return self._cli.get_commit_log(path)

    def archive_project(self, project: str) -> None:
        src = f"decisions/{project}"
        dst = f"archive/{project}"
        archive_dir = self._work_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        src_path = self._work_dir / src
        if src_path.exists():
            self._cli.move_with_git(src, dst)
            self._cli.run("commit", "-m", f"archive({project}): project archived")

    # ==================== Helpers ====================

    def _ensure_decision_branch(self, branch_name: str) -> None:
        branches = self.list_branches()
        if branch_name not in branches:
            self._cli.create_branch_from(branch_name, self._config.branch)

    def _switch_to_branch(self, branch_name: str) -> None:
        current = self.get_current_branch()
        if current != branch_name:
            self.switch_branch(branch_name)

    @staticmethod
    def _get_decision_branch(decision: Dict[str, Any]) -> str:
        sid = decision.get("sid", "") or decision.get("id", "")
        return f"{_BRANCH_PREFIX_DECISION}{sid}"

    @staticmethod
    def _format_commit_message(typ: str, data: Dict[str, Any]) -> str:
        topic = data.get("topic_id", "") or data.get("topic", "")
        sid = data.get("sid", "") or data.get("id", "")
        title = data.get("title", "")
        content = data.get("content", "") or data.get("decision", "")
        rationale = data.get("rationale", "")
        proposer = data.get("proposer", "")

        msg = f"{typ}({topic}): {sid} - {title}\n\n"
        if content:
            msg += f"Decision: {content[:100]}\n"
        if rationale:
            msg += f"Rationale: {rationale[:100]}\n"
        if proposer:
            msg += f"Proposer: {proposer}\n"
        return msg