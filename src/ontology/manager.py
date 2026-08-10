"""运行时 Ontology Manager

管理本体的运行时状态：加载、合并、查询、缓存。
支持默认本体和用户自定义扩展。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ontology.loader import load_ontology_chain
from src.ontology.models import Ontology

logger = logging.getLogger(__name__)

DEFAULT_ONTOLOGY_PATH = Path(__file__).parent.parent.parent / "configs" / "ontology" / "default.yaml"
CUSTOM_ONTOLOGY_PATH = Path(__file__).parent.parent.parent / "configs" / "ontology" / "custom.yaml"


class OntologyManager:
    """本体管理器（单例）"""

    _instance: Optional["OntologyManager"] = None

    def __init__(self, default_path: str | Path = DEFAULT_ONTOLOGY_PATH,
                 custom_path: Optional[str | Path] = None) -> None:
        self._ontology = load_ontology_chain(default_path, custom_path)
        self._custom_path = custom_path
        logger.info("[OntologyManager] Initialized: %d entity types, %d relationship types",
                    len(self._ontology.entity_types), len(self._ontology.relationship_types))

    @classmethod
    def get_instance(cls) -> "OntologyManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    @property
    def ontology(self) -> Ontology:
        return self._ontology

    def get_entity_type_names(self) -> List[str]:
        return self._ontology.list_entity_type_names()

    def get_entity_type(self, name: str):
        return self._ontology.get_entity_type(name)

    def get_valid_relations(self, source_type: str, target_type: str) -> List[str]:
        return self._ontology.get_valid_relation_types(source_type, target_type)

    def is_valid_relation(self, source_type: str, target_type: str, rel_type: str) -> bool:
        return self._ontology.is_valid_relation(source_type, target_type, rel_type)

    def supports_entity_type(self, name: str) -> bool:
        return name in self._ontology.entity_types

    def to_prompt_context(self) -> str:
        """生成 LLM Prompt 中的本体约束描述"""
        return self._ontology.to_prompt_context()

    def reload(self, custom_path: Optional[str | Path] = None) -> None:
        """重新加载本体（运行时热更新）"""
        path = custom_path or self._custom_path
        self._ontology = load_ontology_chain(DEFAULT_ONTOLOGY_PATH, path)
        logger.info("[OntologyManager] Reloaded: %d entity types, %d relationship types",
                    len(self._ontology.entity_types), len(self._ontology.relationship_types))