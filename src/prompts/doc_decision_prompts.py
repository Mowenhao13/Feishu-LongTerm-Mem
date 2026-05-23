# Document Decision Extraction Prompt
# Designed for structured document content (design docs, meeting notes, specs, etc.)
# Unlike IM prompts, document prompts handle: multi-section, version diffs, cross-doc refs

DOC_DECISION_EXTRACTION_PROMPT = """
You are an expert in extracting technical decisions from structured documents.

Your task: Analyze the following document content and extract ALL decisions that were made.

## DOCUMENT CONTEXT

Document ID: {doc_token}
Title: {doc_title}
Document Type: {doc_type}
Last Modified: {last_modified}

## DOCUMENT CONTENT

{content}

## EXTRACTION INSTRUCTIONS

1. Identify sections that contain decisions (e.g., "技术选型", "方案对比", "结论", "决定", "架构设计")
2. For each decision, extract:
   - decision_id: A unique identifier (e.g., "doc_{doc_token}_dec_1")
   - summary: One-line summary of the decision
   - status: One of [decided, pending, rejected, superseded]
   - impact_level: One of [critical, major, minor, advisory]
   - rationale: Why this decision was made
   - alternatives: Any alternative options considered (list)
   - scope: The scope of the decision (e.g., "frontend", "backend", "infrastructure")
   - section: Which document section this decision belongs to
3. If the document is a design doc, prioritize Section 1-3 headings with decision-related titles
4. If the document is a meeting note, extract decisions from action items and conclusions

## OUTPUT FORMAT

Return JSON with this structure:
{{
    "has_decisions": true/false,
    "decisions": [
        {{
            "decision_id": "...",
            "summary": "...",
            "status": "decided|pending|rejected|superseded",
            "impact_level": "critical|major|minor|advisory",
            "rationale": "...",
            "alternatives": ["..."],
            "scope": "...",
            "section": "..."
        }}
    ],
    "reasoning": "Brief explanation of what was found"
}}
"""

DOC_DECISION_DEDUP_PROMPT = """
You are an expert in deduplicating and cross-referencing document decisions.

Your task: Compare the extracted decision with existing decisions in the memory graph.
Determine if this is a NEW decision, a DUPLICATE of an existing one, or an UPDATE to one.

## NEW DECISION
Document: {doc_token}
Section: {section}
Summary: {summary}

## EXISTING DECISIONS IN MEMORY
{existing_decisions}

## EVALUATION CRITERIA
- **DUPLICATE**: Same topic, same or very similar summary (paraphrase), same scope
- **UPDATE**: Same topic and scope, but the new document has more detail or a different status
- **NEW**: Different topic, scope, or substantially different content
- **CONFLICT**: Same topic/scope but opposite conclusion (e.g., "use PostgreSQL" vs "use MySQL")

## OUTPUT FORMAT (JSON only)
{{
    "action": "new|duplicate|update|conflict",
    "matched_decision_id": "...",
    "confidence": 0.0-1.0,
    "reason": "Brief explanation"
}}
"""

DOC_CONFLICT_ASSESSMENT_PROMPT = """
You are an expert in detecting conflicts between decisions across documents.

Your task: Compare two decisions from different documents and assess if they conflict.

## DECISION A
Document: {doc_a_token}
Section: {section_a}
Summary: {summary_a}
Full Text: {text_a}

## DECISION B
Document: {doc_b_token}
Section: {section_b}
Summary: {summary_b}
Full Text: {text_b}

## CONFLICT TYPES
- DIRECT_CONFLICT: Opposite choices for the same technical question
- PARTIAL_OVERLAP: Different approaches to similar problem, may need coordination
- COMPATIBLE: Can coexist, different scope or domain
- INDEPENDENT: Unrelated decisions

## OUTPUT FORMAT (JSON only)
{{
    "conflict_type": "direct_conflict|partial_overlap|compatible|independent",
    "contradiction_score": 0.0-1.0,
    "description": "Explanation of relationship",
    "recommended_action": "merge|keep_both|alert|nothing"
}}
"""

DOC_UPDATE_DETECTION_PROMPT = """
You are an expert in detecting changes and updates in document content.

Your task: Compare the old and new versions of a document section
and determine if any decisions have changed.

## SECTION CONTEXT
Document: {doc_token}
Section: {section}

## OLD CONTENT
{old_content}

## NEW CONTENT
{new_content}

## EVALUATION CRITERIA
- **DECISION_CHANGED**: A previously made decision has been reversed or modified
- **DECISION_ADDED**: New decision appears that wasn't in old version
- **DECISION_REMOVED**: A decision that existed is no longer present
- **NO_CHANGE**: Content changed but no decision-level changes
- **MINOR_EDIT**: Typos, formatting, non-decision changes only

## OUTPUT FORMAT (JSON only)
{{
    "has_decision_change": true/false,
    "change_type": "decision_changed|decision_added|decision_removed|no_change|minor_edit",
    "affected_decisions": [
        {{
            "summary": "...",
            "old_status": "...",
            "new_status": "..."
        }}
    ],
    "reasoning": "Brief explanation"
}}
"""