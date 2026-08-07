"""Memory extraction prompts for Stage 1 (entity/relationship/fact extraction)."""

# ─────────────────────────────────────────────
# Stage 1: Memory Extraction
# Extracts entities, relationships, and facts from episode text.
# ─────────────────────────────────────────────

MEMORY_EXTRACTION_PROMPT = """
You are an expert in extracting structured knowledge from team chat conversations.

Your task: Analyze the following episode text and extract ALL named entities,
their relationships, and factual assertions.

## EPISODE TEXT

{episode_content}

## ONTOLOGY CONTEXT

The following entity types and relationship types are defined. Extract entities
that match these types, and relationships that use the allowed type labels.

{ontology_context}

## EXISTING ENTITIES

The following entities are already known. If the episode mentions them,
use the exact same name (case-preserving) to avoid duplication.

{existing_entities_context}

---

# EXTRACTION RULES

## Entities
- Extract ALL named entities — people, technologies, projects, services, concepts
- Entity names must be explicit and specific (e.g. "PostgreSQL 15" not "数据库")
- No pronouns, no abstract umbrella terms, no generic references
- Each entity gets:
  - `name`: the canonical name as used in the conversation
  - `entity_type`: one of the ontology types defined above
  - `attributes`: type-specific attributes observed in the conversation
  - `confidence`: how certain you are this entity is real and correctly typed
- Assign confidence based on:
  - 0.9-1.0: Explicitly named, clear type evidence, mentioned multiple times
  - 0.7-0.9: Named but type inferred from context
  - 0.5-0.7: Implicitly referenced, some uncertainty

## Relationships
- Extract relationships only between entities that were also extracted
- Use relationship types from the ontology above
- Each relationship gets:
  - `source_name`: exact entity name from the entities array
  - `relationship_type`: the relationship label
  - `target_name`: exact entity name from the entities array
  - `confidence`: how certain you are this relationship exists
  - `valid_at`: (optional) temporal context like "as of last week", "in v2 planning"

## Facts
- Extract factual assertions — statements of fact that are not better represented
  as entity attribute or relationship
- Examples: "The team decided to freeze new features", "Deployment was delayed by 2 days"
- Each fact gets:
  - `content`: the factual statement in natural language
  - `confidence`: how certain you are this fact is true
  - `related_entity_names`: which of the extracted entities this fact relates to
- Skip: opinions, jokes, greetings, meta-conversation, status updates without substance

## General
- Be selective — extract only production-relevant named entities, relationships, and facts.
- Hard limits: at most 20 entities, 20 relationships, and 10 facts.
- Keep `reasoning` to one short sentence.
- When in doubt between two entity types, choose the more specific one
- When in doubt about whether something is a fact, extract it
- Use the exact same entity name in relationships and facts as used in the entities array

---

# OUTPUT FORMAT

Return JSON with the following structure:

```json
{{
    "reasoning": "Brief explanation of the extraction strategy",
    "entities": [
        {{
            "name": "Exact entity name",
            "entity_type": "Technology",
            "attributes": {{"version": "15", "category": "database"}},
            "confidence": 0.95
        }}
    ],
    "relationships": [
        {{
            "source_name": "Entity A Name",
            "relationship_type": "DEPENDS_ON",
            "target_name": "Entity B Name",
            "confidence": 0.85
        }}
    ],
    "facts": [
        {{
            "content": "The team decided to freeze new features until the migration completes",
            "confidence": 0.90,
            "related_entity_names": ["Entity A Name", "Entity C Name"]
        }}
    ]
}}
```

If no entities, relationships, or facts are found, return empty arrays:
```json
{{"reasoning": "No entities found in this episode", "entities": [], "relationships": [], "facts": []}}
```
"""
