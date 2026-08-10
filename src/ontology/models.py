"""本体数据模型

定义实体类型和关系类型的 Schema 数据模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AttributeDef:
    """属性定义"""
    type: str = "str"
    required: bool = False
    description: str = ""
    enum: Optional[List[str]] = None


@dataclass
class EntityTypeDef:
    """实体类型定义"""
    name: str
    description: str = ""
    attributes: Dict[str, AttributeDef] = field(default_factory=dict)

    def validate_attributes(self, attrs: Dict[str, Any]) -> List[str]:
        """校验属性值是否符合定义"""
        errors: List[str] = []
        for attr_name, attr_def in self.attributes.items():
            value = attrs.get(attr_name)
            if attr_def.required and value is None:
                errors.append(f"Attribute '{attr_name}' is required for entity type '{self.name}'")
            if value is not None and attr_def.enum and value not in attr_def.enum:
                errors.append(
                    f"Attribute '{attr_name}' value '{value}' not in allowed values: {attr_def.enum}"
                )
        return errors


@dataclass
class RelationshipTypeDef:
    """关系类型定义"""
    source: str  # 源实体类型名，'*' 表示任意
    target: str  # 目标实体类型名，'*' 表示任意
    types: List[str] = field(default_factory=list)

    def supports(self, source_type: str, target_type: str, rel_type: str) -> bool:
        """判断是否支持该关系"""
        if rel_type not in self.types:
            return False
        if self.source != "*" and self.source != source_type:
            return False
        if self.target != "*" and self.target != target_type:
            return False
        return True


@dataclass
class Ontology:
    """完整本体定义"""
    entity_types: Dict[str, EntityTypeDef] = field(default_factory=dict)
    relationship_types: List[RelationshipTypeDef] = field(default_factory=list)

    def get_entity_type(self, name: str) -> Optional[EntityTypeDef]:
        return self.entity_types.get(name)

    def get_valid_relation_types(self, source_type: str, target_type: str) -> List[str]:
        """获取两个实体类型之间允许的关系类型"""
        result: List[str] = []
        for rt in self.relationship_types:
            if rt.source == "*" or rt.target == "*":
                continue
            if rt.source == source_type and rt.target == target_type:
                result.extend(rt.types)
        # 加上通用关系
        for rt in self.relationship_types:
            if rt.source == "*" or rt.target == "*":
                if (rt.source == "*" or rt.source == source_type) and \
                   (rt.target == "*" or rt.target == target_type):
                    result.extend(rt.types)
        return list(set(result))

    def is_valid_relation(self, source_type: str, target_type: str, rel_type: str) -> bool:
        """判断关系是否合法"""
        return any(
            rt.supports(source_type, target_type, rel_type)
            for rt in self.relationship_types
        )

    def list_entity_type_names(self) -> List[str]:
        return list(self.entity_types.keys())

    def to_prompt_context(self) -> str:
        """生成用于 LLM Prompt 的本体描述"""
        lines: List[str] = ["## 实体类型"]
        for etype in self.entity_types.values():
            attrs_desc = ", ".join(
                f"{aname}({'required' if adef.required else 'optional'})"
                for aname, adef in etype.attributes.items()
            )
            lines.append(f"- **{etype.name}**: {etype.description}")
            if attrs_desc:
                lines.append(f"  属性: {attrs_desc}")

        lines.append("\n## 关系类型")
        for rt in self.relationship_types:
            types_str = ", ".join(rt.types)
            lines.append(f"- {rt.source} → {rt.target}: [{types_str}]")

        return "\n".join(lines)