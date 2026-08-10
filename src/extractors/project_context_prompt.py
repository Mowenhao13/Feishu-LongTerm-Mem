"""Project context injection prompt for LLM decision extraction.

When the ConversationFileBridge decides to merge file change context
with conversation context, this template formats the file changes as
a preamble that gets injected before the conversation content.

The pattern follows the existing entity context injection in
SimpleLLMExtractor.extract_with_context() — entity context is injected
as a preamble, and project context follows the same structure.

Usage:
    project_preamble = PROJECT_CONTEXT_PROMPT.format(
        file_changes_text=formatted_changes,
    )
    enriched_content = f"{project_preamble}\n\n{original_content}"
"""

PROJECT_CONTEXT_PROMPT = """## 项目代码变更上下文

以下是在此对话期间或附近检测到的项目代码变更：

{file_changes_text}

在提取决策时，请考虑以上代码变更是否与对话内容相关。
如果相关，请在提取的决策中引用具体的文件路径和变更内容。

注意：并非所有代码变更都与对话相关。只有确实相关的才引用。
"""


def format_file_changes_for_prompt(
    changes: list,
    max_changes: int = 10,
    max_diff_length: int = 120,
) -> str:
    """Format a list of ProjectFileChange objects as readable text for LLM prompt.

    Args:
        changes: List of ProjectFileChange objects.
        max_changes: Maximum number of changes to include (newest first).
        max_diff_length: Maximum length of diff_summary to show.

    Returns:
        Formatted string suitable for prompt injection.
    """
    if not changes:
        return "（无文件变更）"

    # Sort by timestamp, newest first, then limit
    sorted_changes = sorted(
        changes, key=lambda c: c.timestamp if hasattr(c, "timestamp") else 0, reverse=True
    )[:max_changes]

    lines: list[str] = []
    for c in sorted_changes:
        change_type_symbol = {
            "created": "➕",
            "modified": "✏️",
            "deleted": "🗑️",
        }.get(c.change_type, "❓")

        lang_tag = f" [{c.language}]" if c.language else ""
        diff_text = ""
        if c.diff_summary:
            truncated = c.diff_summary[:max_diff_length]
            if len(c.diff_summary) > max_diff_length:
                truncated += "..."
            diff_text = f" — {truncated}"

        lines.append(f"  {change_type_symbol} {c.change_type}: `{c.file_path}`{lang_tag}{diff_text}")

    if not lines:
        return "（无文件变更）"

    return "\n".join(lines)