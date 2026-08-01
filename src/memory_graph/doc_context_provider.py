"""DocContextProvider — 飞书搜索 API 驱动的文档上下文检索

通过飞书搜索 API（search/v2/doc_wiki/search）检索知识库中的相关文档，
按需获取文档内容块，作为决策提取的上下文参考。
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DocBlock:
    """文档块"""
    block_id: str = ""
    block_type: str = ""
    content: str = ""


@dataclass
class DocContext:
    """完整的文档上下文"""
    doc_token: str = ""
    title: str = ""
    owner_name: str = ""
    update_time: str = ""
    url: str = ""
    blocks: List[DocBlock] = field(default_factory=list)


class LarkSearchClient:
    """飞书搜索 API + Doc raw_content API 封装"""

    def __init__(self, wiki_space_id: str = ""):
        self._wiki_space_id = wiki_space_id

    def search_docs(
        self,
        query: str,
        doc_types: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """调用飞书搜索 API 检索文档

        使用 lark-cli api 调用 search/v2/doc_wiki/search。
        """
        if not query.strip():
            return []

        data: Dict[str, Any] = {
            "search_key": query[:100],
            "page_size": limit,
        }
        if doc_types:
            data["docs_types"] = doc_types  # ["DOC", "DOCX"]

        try:
            result = subprocess.run(
                [
                    "lark-cli", "api",
                    "POST", "/open-apis/search/v2/doc_wiki/search",
                    "--data", json.dumps(data),
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return []

            resp = json.loads(result.stdout)
            if not resp.get("ok"):
                return []

            items = resp.get("data", {}).get("items", [])
            return items

        except Exception:
            return []

    def get_doc_content(self, doc_token: str) -> str:
        """获取飞书文档内容（Markdown 格式）"""
        try:
            result = subprocess.run(
                [
                    "lark-cli", "docs", "+fetch",
                    "--api-version", "v2",
                    "--doc", doc_token,
                    "--doc-format", "markdown",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return ""
            return result.stdout
        except Exception:
            return ""


class DocContextProvider:
    """文档上下文提供者

    通过飞书搜索 API 实时检索知识库文档，按需获取文档内容，
    为决策提取提供相关文档上下文。
    """

    def __init__(self, wiki_space_id: str = ""):
        self._search_client = LarkSearchClient(wiki_space_id=wiki_space_id)
        self._wiki_space_id = wiki_space_id

    def retrieve_context(self, query: str) -> List[DocContext]:
        """检索与 query 相关的文档上下文

        流程:
        1. 调用飞书搜索 API 检索文档
        2. 对匹配的文档获取内容
        3. 选取相关块
        4. 组装 DocContext
        """
        if not query.strip():
            return []

        # Step 1: 搜索文档
        search_results = self._search_client.search_docs(
            query=query[:100],
            doc_types=["DOC", "DOCX"],
            limit=5,
        )

        if not search_results:
            return []

        contexts: List[DocContext] = []

        for item in search_results:
            doc_token = (
                item.get("doc_token", "")
                or item.get("obj_token", "")
                or item.get("url", "").split("/")[-1].split("?")[0]
            )
            if not doc_token:
                continue

            # Step 2: 获取文档内容
            content = self._search_client.get_doc_content(doc_token)
            if not content:
                continue

            # Step 3: 按标题分块，选取相关块
            blocks = self._split_into_blocks(content)
            relevant = self._select_relevant_blocks(blocks, query)

            contexts.append(DocContext(
                doc_token=doc_token,
                title=item.get("name", "") or item.get("title", ""),
                owner_name=item.get("owner_name", ""),
                update_time=item.get("update_time", ""),
                url=item.get("url", ""),
                blocks=relevant,
            ))

            if len(contexts) >= 3:
                break

        return contexts

    def format_prompt_context(self, contexts: List[DocContext]) -> str:
        """将文档上下文格式化为 LLM prompt 文本"""
        if not contexts:
            return ""

        lines = ["📄 [相关文档参考]"]

        for ctx in contexts:
            lines.append("")
            lines.append(f"**{ctx.title}**")
            if ctx.url:
                lines.append(f"链接: {ctx.url}")
            lines.append("")

            for block in ctx.blocks:
                if block.content.strip():
                    lines.append(block.content)
                    lines.append("")

        return "\n".join(lines)

    # ---- 内部方法 ----

    @staticmethod
    def _split_into_blocks(content: str) -> List[DocBlock]:
        """按 Markdown 标题级别分块"""
        blocks: List[DocBlock] = []
        current_title = ""
        current_lines: List[str] = []

        for line in content.split("\n"):
            if line.startswith("#"):
                # 遇到新标题，保存之前的块
                if current_lines:
                    blocks.append(DocBlock(
                        block_type="heading",
                        content="\n".join(current_lines),
                    ))
                    current_lines = []
                current_title = line.strip("# ").strip()
                current_lines.append(line)
            else:
                current_lines.append(line)

        if current_lines:
            blocks.append(DocBlock(
                block_type="content",
                content="\n".join(current_lines),
            ))

        return blocks

    @staticmethod
    def _select_relevant_blocks(blocks: List[DocBlock], query: str, max_blocks: int = 5) -> List[DocBlock]:
        """基于关键词评分选取相关块"""
        query_terms = [t.lower() for t in query.split() if len(t) > 1]
        if not query_terms:
            return blocks[:max_blocks]

        scored: List[tuple] = []
        for block in blocks:
            score = 0
            content_lower = block.content.lower()
            for term in query_terms:
                score += content_lower.count(term)
            # 标题块优先
            if block.block_type == "heading":
                score += 5
            scored.append((score, block))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [b for _, b in scored[:max_blocks]]
