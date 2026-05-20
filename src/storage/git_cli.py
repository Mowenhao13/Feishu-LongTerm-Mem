"""
Git CLI wrapper - translates ref/git/git_ops.go

Executes git commands via subprocess with typed results.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CommitLogEntry:
    hash: str = ""
    message: str = ""


@dataclass
class SearchHit:
    file: str = ""
    line_num: int = 0
    content: str = ""


@dataclass
class BlameEntry:
    commit: str = ""
    line_num: int = 0
    content: str = ""
    author: str = ""
    date: str = ""


class GitCLIError(Exception):
    pass


class GitCLI:
    """Git command execution wrapper."""

    def __init__(self, work_dir: str | Path) -> None:
        self.work_dir = Path(work_dir).resolve()

    def run(self, *args: str) -> str:
        cmd = ["git", *args]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise GitCLIError(
                    f"git {' '.join(args)} failed: {result.stderr.strip()}"
                )
            return result.stdout.strip()
        except FileNotFoundError:
            raise GitCLIError("git command not found")

    def commit(self, path: str, message: str) -> str:
        self.run("add", path)
        try:
            self.run("commit", "-m", message)
        except GitCLIError as e:
            if "nothing to commit" in str(e):
                return self.get_head_hash()
            raise
        return self.get_head_hash()

    def get_head_hash(self) -> str:
        return self.run("rev-parse", "HEAD")

    def create_branch(self, branch_name: str) -> None:
        self.run("checkout", "-b", branch_name)

    def create_branch_from(self, branch_name: str, base: str) -> None:
        self.run("checkout", "-b", branch_name, base)

    def switch_branch(self, branch_name: str) -> None:
        self.run("checkout", branch_name)

    def merge_branch(self, branch_name: str) -> None:
        self.run("merge", "--no-ff", branch_name)

    def get_current_branch(self) -> str:
        return self.run("rev-parse", "--abbrev-ref", "HEAD")

    def list_branches(self) -> List[str]:
        output = self.run("branch", "-a")
        branches = []
        for line in output.split("\n"):
            line = line.strip()
            if line and not line.startswith("remotes/"):
                branches.append(line.lstrip("* "))
        return branches

    def get_commit_log(self, path: str = "", limit: int = 0) -> List[CommitLogEntry]:
        args = ["log", "--oneline"]
        if limit > 0:
            args.append(f"-{limit}")
        if path:
            args.extend(["--", path])
        output = self.run(*args)
        logs = []
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            entry = CommitLogEntry(hash=parts[0])
            if len(parts) > 1:
                entry.message = parts[1]
            logs.append(entry)
        return logs

    def move_with_git(self, src: str, dst: str) -> None:
        self.run("mv", src, dst)

    def git_grep(self, pattern: str, path: str = "") -> List[SearchHit]:
        args = ["grep", "-i", "-n", pattern]
        if path:
            args.extend(["--", path])
        try:
            output = self.run(*args)
        except GitCLIError as e:
            if "exit status 1" in str(e):
                return []
            raise
        return self._parse_grep_output(output)

    def git_blame(self, path: str) -> List[BlameEntry]:
        try:
            output = self.run("blame", "-p", path)
        except GitCLIError:
            return []
        return self._parse_blame_output(output)

    def read_file_at_commit(self, file_path: str, commit_hash: str) -> str:
        if not commit_hash or commit_hash == "HEAD":
            return self.read_file(file_path)
        return self.run("show", f"{commit_hash}:{file_path}")

    def read_file(self, file_path: str) -> str:
        full_path = self.work_dir / file_path
        return full_path.read_text(encoding="utf-8")

    def rev_list_count(self, branch: str, exclude: str = "main") -> int:
        try:
            result = self.run("rev-list", "--count", branch, f"^{exclude}")
            return int(result)
        except (GitCLIError, ValueError):
            return 0

    def ls_tree(self, branch: str) -> List[str]:
        output = self.run("ls-tree", "-r", "--name-only", branch)
        return [line.strip('" \t\r\n') for line in output.split("\n") if line.strip()]

    @staticmethod
    def _parse_grep_output(output: str) -> List[SearchHit]:
        hits = []
        for line in output.split("\n"):
            if not line:
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                hits.append(SearchHit(file=parts[0], content=parts[2]))
        return hits

    @staticmethod
    def _parse_blame_output(output: str) -> List[BlameEntry]:
        entries = []
        current = BlameEntry()
        for line in output.split("\n"):
            if not line:
                continue
            if line.startswith("\t"):
                current.content = line[1:]
                entries.append(current)
                current = BlameEntry()
            elif " " not in line:
                continue
            else:
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    key, val = parts
                    if key == "author":
                        current.author = val
                    elif key == "author-time":
                        current.date = val
        return entries