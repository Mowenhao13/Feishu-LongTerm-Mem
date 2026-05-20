from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

EVALDATA_DIR = Path(__file__).resolve().parent.parent.parent / "eval_data"


@dataclass
class EvalItem:
    input: str = ""
    expected: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_extraction_dialogue(scenario: str) -> Optional[dict[str, Any]]:
    path = EVALDATA_DIR / "decision_extraction" / scenario / "dialogue.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_extraction_qa(scenario: str) -> Optional[dict[str, Any]]:
    path = EVALDATA_DIR / "decision_extraction" / scenario / "qa.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def list_extraction_scenarios() -> list[str]:
    base = EVALDATA_DIR / "decision_extraction"
    if not base.exists():
        return []
    return sorted(d.name for d in base.iterdir() if d.is_dir())


def get_eval_path(name: str) -> Path:
    return EVALDATA_DIR / name


def list_eval_datasets() -> list[dict[str, Any]]:
    datasets: list[dict[str, Any]] = []
    for subdir in EVALDATA_DIR.iterdir():
        if subdir.is_dir() and subdir.name != "decision_extraction":
            jsonl_files = list(subdir.glob("*.jsonl"))
            if jsonl_files:
                datasets.append({
                    "name": subdir.name,
                    "files": [f.name for f in jsonl_files],
                })
    return datasets