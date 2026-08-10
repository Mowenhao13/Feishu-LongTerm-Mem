"""本体 YAML 加载器

从 configs/ontology/*.yaml 加载本体定义，支持默认本体 + 用户自定义扩展。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.ontology.models import (
    AttributeDef,
    EntityTypeDef,
    Ontology,
    RelationshipTypeDef,
)

logger = logging.getLogger(__name__)


def _parse_attribute(name: str, raw: Dict[str, Any]) -> AttributeDef:
    return AttributeDef(
        type=raw.get("type", "str"),
        required=raw.get("required", False),
        description=raw.get("description", ""),
        enum=raw.get("enum"),
    )


def _parse_entity_type(name: str, raw: Dict[str, Any]) -> EntityTypeDef:
    attrs_raw = raw.get("attributes", {})
    attributes = {
        aname: _parse_attribute(aname, adef)
        for aname, adef in attrs_raw.items()
    }
    return EntityTypeDef(
        name=name,
        description=raw.get("description", ""),
        attributes=attributes,
    )


def _parse_relationship_types(raw_list: List[Dict[str, Any]]) -> List[RelationshipTypeDef]:
    return [
        RelationshipTypeDef(
            source=item.get("source", "*"),
            target=item.get("target", "*"),
            types=item.get("types", []),
        )
        for item in raw_list
    ]


def load_ontology(path: str | Path) -> Ontology:
    """从 YAML 文件加载本体定义"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Ontology file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw: Dict[str, Any] = yaml.safe_load(f)

    entity_types_raw = raw.get("entity_types", {})
    relationship_raw = raw.get("relationship_types", [])

    entity_types = {
        ename: _parse_entity_type(ename, edef)
        for ename, edef in entity_types_raw.items()
    }

    relationship_types = _parse_relationship_types(relationship_raw)

    ontology = Ontology(
        entity_types=entity_types,
        relationship_types=relationship_types,
    )

    logger.info(
        "[OntologyLoader] Loaded: entities=%d relationships=%d",
        len(entity_types), len(relationship_types),
    )
    return ontology


def load_ontology_chain(default_path: str | Path, custom_path: Optional[str | Path] = None) -> Ontology:
    """加载默认本体并合并用户自定义扩展

    优先加载 default.yaml，然后加载 custom.yaml（如果有的话）：
    - custom 中的同名实体类型合并 attributes
    - custom 中的同名关系类型合并 types
    - custom 中的新实体类型直接添加
    """
    ontology = load_ontology(default_path)

    if custom_path is not None:
        custom_path = Path(custom_path)
        if custom_path.exists():
            logger.info("[OntologyLoader] Merging custom ontology from %s", custom_path)
            custom = load_ontology(custom_path)

            # 合并实体类型
            for ename, etype in custom.entity_types.items():
                if ename in ontology.entity_types:
                    existing = ontology.entity_types[ename]
                    existing.attributes.update(etype.attributes)
                    if etype.description:
                        existing.description = etype.description
                else:
                    ontology.entity_types[ename] = etype

            # 合并关系类型
            for crt in custom.relationship_types:
                matched = False
                for ort in ontology.relationship_types:
                    if ort.source == crt.source and ort.target == crt.target:
                        ort.types = list(set(ort.types + crt.types))
                        matched = True
                        break
                if not matched:
                    ontology.relationship_types.append(crt)

    return ontology