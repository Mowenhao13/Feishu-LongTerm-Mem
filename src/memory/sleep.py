from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from src.node.node import DecisionNode
from src.node.types import DecisionStatus, ImpactLevel, Relation, RelationType
from src.prompts import DEEP_SLEEP_DEDUP_PROMPT

logger = logging.getLogger(__name__)


class SleepReport:
    """睡眠整理报告 — 记录每次 consolidation 的结果"""

    def __init__(self) -> None:
        self.phase: str = ""
        self.timestamp: str = datetime.now().isoformat()
        self.total_decisions: int = 0
        self.duplicates_found: int = 0
        self.duplicates_merged: int = 0
        self.noise_pruned: int = 0
        self.conflicts_found: int = 0
        self.hot_scores_updated: int = 0
        self.decisions_promoted: int = 0
        self.errors: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "timestamp": self.timestamp,
            "total_decisions": self.total_decisions,
            "duplicates_found": self.duplicates_found,
            "duplicates_merged": self.duplicates_merged,
            "noise_pruned": self.noise_pruned,
            "conflicts_found": self.conflicts_found,
            "hot_scores_updated": self.hot_scores_updated,
            "decisions_promoted": self.decisions_promoted,
            "errors": self.errors,
        }


class SleepManager:
    """记忆整理管理器（仿 OpenClaw 睡眠机制）

    四阶段整理流程：
    Phase 1 - Light Sleep（浅睡）：收集当前所有决策，统计基础信息
    Phase 2 - Deep Sleep（深睡）：预过滤 + 批量 LLM 精判，发现重复/冲突
    Phase 3 - Promote（巩固）：根据 LLM action 分派处理（skip/merge/conflict/keep）
    Phase 4 - Wave（存档）：清理 processed_episode_hashes，保存状态

    LLM 调用优化（尽量减少调用次数）：
    - _fast_prefilter（Dice 0.35 + 同 topic）先过滤掉 90%+ 的无关配⇨
    - 每批最多 10 个候选，一次 LLM 调用处理多个判断
    - LLM 不可用时回退到 Dice >= 0.7
    """

    def __init__(
        self,
        graph: Any = None,
        pipeline: Any = None,
        storage: Any = None,
        hypergraph: Any = None,
        hg_persistence: Any = None,
        task_view_syncer: Any = None,
        llm_provider: Any = None,
        embedder: Any = None,
        source_path: Optional[str] = None,
    ) -> None:
        self._graph = graph
        self._pipeline = pipeline
        self._storage = storage
        self._hypergraph = hypergraph
        self._hg_persistence = hg_persistence
        self._task_view_syncer = task_view_syncer
        self._llm = llm_provider
        self._embedder = embedder
        self._source_path = source_path

        self._dedup_threshold = float(os.getenv("MEMORY_SLEEP_DEDUP_THRESHOLD", "0.7"))
        self._noise_hot_score_min = float(os.getenv("MEMORY_SLEEP_NOISE_HOT_MIN", "5.0"))
        self._noise_confidence_min = float(os.getenv("MEMORY_SLEEP_NOISE_CONFIDENCE_MIN", "0.3"))
        self._prefilter_dice = 0.35

        self._cached_judgments: List[Tuple[str, str, str, str, str]] = []

    def _load_decisions_from_path(self, path: str) -> List[DecisionNode]:
        """从备份目录加载决策文件

        预期结构:
          {path}/decisions/{project}/{topic}/*.md
        """
        from pathlib import Path

        decisions_dir = Path(path) / "decisions"
        if not decisions_dir.exists():
            logger.warning("[Sleep] No decisions directory found at %s", decisions_dir)
            return []

        loaded: List[DecisionNode] = []
        for md_file in sorted(decisions_dir.rglob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                # Parse simple key: value lines from the md front matter
                record: Dict[str, Any] = {"sid": md_file.stem}
                for line in content.split("\n"):
                    line = line.strip()
                    if ":" in line and not line.startswith("#") and not line.startswith("---") and not line.startswith("```"):
                        k, v = line.split(":", 1)
                        record[k.strip().lower()] = v.strip()

                node = DecisionNode(
                    sid=record.get("sid", md_file.stem),
                    topic_id=record.get("topic_id", "") or record.get("topic", ""),
                    title=record.get("title", "")[:100],
                    summary=record.get("summary", "")[:200],
                    full_text=content,
                    status=self._parse_status(record.get("status", "pending")),
                    impact_level=self._parse_impact(record.get("impact_level", "minor")),
                    is_suggestion=record.get("is_suggestion", "false").lower() in ("true", "1", "yes"),
                    confidence=float(record.get("confidence", 0.8)),
                    proposer=record.get("proposer", ""),
                    assignee=record.get("assignee", "") or record.get("executor", ""),
                    version=int(record.get("version", 1)),
                )
                loaded.append(node)
            except Exception as e:
                logger.warning("[Sleep] Failed to load decision %s: %s", md_file.name, str(e)[:60])

        logger.info("[Sleep] Loaded %d decisions from %s", len(loaded), path)
        return loaded

    @staticmethod
    def _parse_status(val: str) -> Any:
        from src.node.types import DecisionStatus
        try:
            return DecisionStatus(val)
        except ValueError:
            for s in DecisionStatus:
                if s.value == val or s.name.lower() == val.lower():
                    return s
            return DecisionStatus.PENDING

    @staticmethod
    def _parse_impact(val: str) -> Any:
        from src.node.types import ImpactLevel
        try:
            return ImpactLevel(val)
        except ValueError:
            for iv in ImpactLevel:
                if iv.value == val or iv.name.lower() == val.lower():
                    return iv
            return ImpactLevel.MINOR

    # ==================== Phase 1: Light Sleep ====================

    def light_sleep(self, report: SleepReport) -> List[DecisionNode]:
        """Phase 1 - 浅睡：收集所有决策，统计基础信息"""
        report.phase = "light_sleep"
        if self._source_path:
            decisions = self._load_decisions_from_path(self._source_path)
            report.total_decisions = len(decisions)
            logger.info("[Sleep] Phase 1 (Light Sleep): loaded %d decisions from %s",
                        len(decisions), self._source_path)
            return decisions
        if self._graph is None:
            report.errors.append("No graph available")
            return []

        all_decisions = self._graph.get_all_decisions()
        report.total_decisions = len(all_decisions)
        logger.info("[Sleep] Phase 1 (Light Sleep): collected %d decisions", len(all_decisions))
        return all_decisions

    # ==================== Phase 2: Deep Sleep ====================

    def deep_sleep(
        self,
        decisions: List[DecisionNode],
        report: SleepReport,
    ) -> List[Tuple[str, str, float]]:
        """Phase 2 - 深睡：预过滤 + 批量 LLM 精判

        OpenClaw 三重门槛：
        1. 置信度分数（Confidence Score）
        2. 召回频率（Recall Frequency）
        3. 查询多样性（Query Diversity）

        LLM 调优：先用 _fast_prefilter 快速缩小候选集，
        再用 _batch_dedup_judge 批量调用 LLM 判断。
        LLM 不可用时回退到 Dice >= 0.7。

        Returns:
            [(保留的 sid, 被合并的 sid, 相似度)] — 兼容旧 promote() 签名
        """
        report.phase = "deep_sleep"
        duplicates: List[Tuple[str, str, float]] = []
        self._cached_judgments = []

        if not decisions:
            return duplicates

        # Step 2a: 更新所有决策的 hot score
        for d in decisions:
            if self._graph:
                try:
                    self._graph.recalculate_hot_score(d.sid)
                    report.hot_scores_updated += 1
                except Exception as e:
                    report.errors.append(f"Hot score update failed for {d.sid}: {e}")

        logger.info("[Sleep] Phase 2 (Deep Sleep): updated %d hot scores", report.hot_scores_updated)

        # Step 2b: 预过滤 + LLM 批量判断
        candidates: List[Tuple[DecisionNode, DecisionNode, float]] = []
        seen_pairs: Set[Tuple[str, str]] = set()
        for i, a in enumerate(decisions):
            if not a.status.is_active():
                continue
            for b in decisions[i + 1:]:
                if not b.status.is_active():
                    continue
                pair_key = tuple(sorted([a.sid, b.sid]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                if not self._fast_prefilter(a, b):
                    continue
                dice = self._summary_similarity(a.summary, b.summary)
                candidates.append((a, b, dice))

        if not candidates:
            logger.info("[Sleep] Phase 2: no candidates after prefilter (0 LLM calls)")
            return duplicates

        # 有候选 → 尝试 LLM 批量判断
        if self._llm and hasattr(self._llm, "generate"):
            try:
                judgments = self._batch_dedup_judge(candidates)
                # judgments: [(main_sid, candidate_sid, action, reason, info_to_merge)]
                self._cached_judgments = judgments

                for main_sid, candidate_sid, action, _reason, _info in judgments:
                    if action in ("skip", "merge"):
                        report.duplicates_found += 1
                        duplicates.append((main_sid, candidate_sid, 1.0))
                    elif action == "conflict":
                        report.conflicts_found += 1

                logger.info("[Sleep] Phase 2 (Deep Sleep): LLM判定 %d pairs → skip/merge=%d conflict=%d keep=%d",
                            len(judgments), report.duplicates_found,
                            report.conflicts_found,
                            len(judgments) - report.duplicates_found - report.conflicts_found)
                return duplicates
            except Exception as e:
                logger.warning("[Sleep] LLM batch judge failed, falling back to Dice: %s", str(e)[:60])
                self._cached_judgments = []

        # 退路：Dice >= 0.7
        for a, b, dice in candidates:
            if dice >= self._dedup_threshold:
                report.duplicates_found += 1
                logger.info("[Sleep]   Fallback Dice: %.2f — %s vs %s", dice, a.summary[:40], b.summary[:40])
                if self._pick_winner(a, b):
                    duplicates.append((a.sid, b.sid, dice))
                else:
                    duplicates.append((b.sid, a.sid, dice))

        logger.info("[Sleep] Phase 2 (Deep Sleep): fallback Dice found %d duplicates", report.duplicates_found)
        return duplicates

    # ==================== Phase 3: Promote ====================

    def promote(
        self,
        decisions: List[DecisionNode],
        duplicates: List[Tuple[str, str, float]],
        report: SleepReport,
    ) -> None:
        """Phase 3 - 巩固：根据 LLM action 分派处理

        LLM action 分派：
        - skip  → _handle_skip（候选 SUPERSEDED，主保持不变）
        - merge → _merge_decisions（信息合并到主，候选 SUPERSEDED）
        - conflict → _handle_conflict（双向 CONFLICTS_WITH 关系）
        - keep  → 跳过（不做任何操作）

        无 LLM 时（Dice fallback）：走旧的 _merge_decisions 逻辑。
        """
        report.phase = "promote"

        if self._cached_judgments:
            # LLM action 分派
            for main_sid, candidate_sid, action, llm_reason, info_to_merge in self._cached_judgments:
                try:
                    if action == "skip":
                        self._handle_skip(main_sid, candidate_sid, llm_reason)
                        report.duplicates_merged += 1
                    elif action == "merge":
                        self._merge_decisions(main_sid, candidate_sid, info_to_merge, llm_reason)
                        report.duplicates_merged += 1
                    elif action == "conflict":
                        self._handle_conflict(main_sid, candidate_sid, llm_reason)
                    elif action == "keep":
                        pass
                except Exception as e:
                    report.errors.append(f"Action {action} failed {main_sid}/{candidate_sid}: {e}")
        else:
            # 退路：Dice fallback — 旧逻辑
            for keep_sid, merge_sid, sim in duplicates:
                try:
                    self._merge_decisions(keep_sid, merge_sid)
                    report.duplicates_merged += 1
                except Exception as e:
                    report.errors.append(f"Merge failed: {keep_sid} <- {merge_sid}: {e}")

        # Step 3b: 修剪噪音
        for d in decisions:
            if not d.status.is_active():
                continue
            hot = d.access_stats.hot_score if d.access_stats else 0.0
            if hot < self._noise_hot_score_min and d.confidence < self._noise_confidence_min:
                logger.info("[Sleep]   Prune noise: %s (hot=%.1f, conf=%.2f)", d.sid[:12], hot, d.confidence)
                if self._graph:
                    d.change_status(DecisionStatus.SHELVED)
                    self._graph.upsert_decision(d, "feishu-mem")
                if self._storage:
                    try:
                        self._storage.write_decision({"sid": d.sid, "status": "shelved"})
                    except Exception:
                        pass
                report.noise_pruned += 1

        # Step 3c: 提升高价值
        for d in decisions:
            if not d.status.is_active():
                continue
            hot = d.access_stats.hot_score if d.access_stats else 0.0
            if hot >= 50.0 and d.status == DecisionStatus.PENDING:
                logger.info("[Sleep]   Promote: %s (hot=%.1f) PENDING → DECIDED", d.sid[:12], hot)
                if self._graph:
                    d.change_status(DecisionStatus.DECIDED)
                    self._graph.upsert_decision(d, "feishu-mem")
                report.decisions_promoted += 1

        logger.info("[Sleep] Phase 3 (Promote): merged=%d pruned=%d promoted=%d conflicts=%d",
                     report.duplicates_merged, report.noise_pruned,
                     report.decisions_promoted, report.conflicts_found)

    # ==================== Phase 3b: Tree Building ====================

    def build_tree(self, decisions: List[DecisionNode], report: SleepReport) -> None:
        """Phase 3b - 建树：用 LLM 判断决策之间的父子关系

        在去重完成后，对当前所有活跃决策调用 LLM 建立树结构。
        LLM 不可用或调用失败时跳过，不影响已有 parent_id。
        """
        if self._graph is None or not self._llm:
            return
        report.phase = "build_tree"

        active = [d for d in decisions if d.status.is_active()]
        if len(active) < 2:
            return

        try:
            from src.prompts import DECISION_TREE_BUILD_PROMPT
            import json as _json

            decision_list = _json.dumps([
                {"sid": d.sid, "title": d.title or d.summary, "summary": d.summary}
                for d in active
            ], ensure_ascii=False, indent=2)

            prompt = DECISION_TREE_BUILD_PROMPT.format(decision_list=decision_list)
            _temp = float(os.getenv("MEMORY_DEDUP_TEMPERATURE", "0.05"))
            resp = self._llm.generate(
                prompt,
                temperature=_temp,
                response_format={"type": "json_object"},
            )
            result = _json.loads(resp) if isinstance(resp, str) else resp

            relations = result.get("relations", [])
            built = 0
            for rel in relations:
                parent_sid = rel.get("parent_sid", "")
                child_sid = rel.get("child_sid", "")
                if not parent_sid or not child_sid:
                    continue

                child_node = self._graph.get_decision(child_sid)
                parent_node = self._graph.get_decision(parent_sid)
                if child_node is None or parent_node is None:
                    continue

                # 更新 child 的 parent_id
                child_node.parent_id = parent_sid
                child_node.add_relation(Relation(
                    type=RelationType.CHILD_OF,
                    target_id=parent_sid,
                    description=rel.get("reason", ""),
                ))
                parent_node.add_relation(Relation(
                    type=RelationType.PARENT_OF,
                    target_id=child_sid,
                    description=rel.get("reason", ""),
                ))
                self._graph.upsert_decision(child_node, "feishu-mem")
                self._graph.upsert_decision(parent_node, "feishu-mem")
                built += 1

            logger.info("[Sleep] Phase 3b (Build Tree): built %d parent-child relations from LLM (out of %d active decisions)",
                        built, len(active))
        except Exception as e:
            logger.warning("[Sleep] Tree building skipped: %s", str(e)[:80])

    # ==================== Phase 4: Wave ====================

    def wave(self, report: SleepReport, processed_hashes: Optional[Set[str]] = None) -> None:
        """Phase 4 - 存档：先在本地写全量决策文件，再尝试同步多维表格

        执行顺序：
        1. Hypergraph 状态保存
        2. 全量决策写入本地 GitStorage（不依赖 dirty 标记，确保所有文件最新）
        3. BaseView 多维表格同步（即使失败也不影响本地文件）
        4. 清理 processed_hashes
        """
        report.phase = "wave"

        if self._hg_persistence and self._hypergraph:
            try:
                self._hg_persistence.save(self._hypergraph)
                logger.info("[Sleep]   Hypergraph saved")
            except Exception as e:
                report.errors.append(f"Hypergraph save failed: {e}")

        if self._storage and self._graph:
            try:
                all_nodes = self._graph.get_all_decisions()
                written = 0
                for node in all_nodes:
                    node_dict = self._graph.node_to_dict(node) if hasattr(self._graph, "node_to_dict") else {"sid": node.sid}
                    self._storage.write_decision(node_dict)
                    written += 1
                logger.info("[Sleep]   Wrote %d decisions to local storage", written)
            except Exception as e:
                report.errors.append(f"Local storage write failed: {e}")

        if self._task_view_syncer:
            try:
                self._task_view_syncer.full_sync()
                logger.info("[Sleep]   Task view synced to 飞书任务")
            except Exception as e:
                logger.warning("[Sleep]   Task view sync failed (non-fatal, local files safe): %s", str(e)[:80])
                report.errors.append(f"Task view sync failed: {e}")

        if self._storage and self._graph:
            try:
                self._graph.get_dirty_and_clean()
                logger.debug("[Sleep]   Dirty set cleared")
            except Exception:
                pass

        if processed_hashes is not None:
            while len(processed_hashes) > 100:
                processed_hashes.pop()
            logger.info("[Sleep]   Processed hashes cleaned: %d remaining", len(processed_hashes))

        logger.info("[Sleep] Phase 4 (Wave): consolidation complete")

    # ==================== 完整睡眠周期 ====================

    def sleep(
        self,
        processed_hashes: Optional[Set[str]] = None,
    ) -> SleepReport:
        """执行一次完整的记忆整理睡眠周期"""
        report = SleepReport()
        logger.info("[Sleep] ====== Memory Consolidation (Sleep) start ======")

        try:
            decisions = self.light_sleep(report)
            duplicates = self.deep_sleep(decisions, report)
            self.promote(decisions, duplicates, report)
            self.build_tree(decisions, report)
            self.wave(report, processed_hashes)
        except Exception as e:
            report.errors.append(f"Sleep cycle failed: {e}")
            logger.error("[Sleep] Cycle failed: %s", e)

        logger.info("[Sleep] ====== Memory Consolidation complete: %s", report.to_dict())
        return report

    # ==================== 预过滤 ====================

    def _fast_prefilter(self, a: DecisionNode, b: DecisionNode) -> bool:
        """快速预过滤：只有通过预过滤的候选才会进入 LLM 判断

        严格的条件尽可能减少 LLM 调用次数：
        1. 同 topic 或跨群 topic 语义相近
        2. Dice >= 0.35（低阈值，高召回）
        3. summary 为空时退回到 full_text 比较

        跨群匹配（新增）：不同 chat_id 但 topic 语义相似度 >= 0.5 也视为候选。
        """
        if a.topic_id == b.topic_id:
            # Same topic: check similarity
            dice = self._summary_similarity(a.summary, b.summary)
            if dice >= self._prefilter_dice:
                return True
            if not a.summary and not b.summary and a.full_text and b.full_text:
                dice = self._summary_similarity(a.full_text, b.full_text)
                return dice >= self._prefilter_dice
            return False

        # Cross-chat: different chat_id but semantically similar topic
        a_cid = getattr(a, "chat_id", None)
        b_cid = getattr(b, "chat_id", None)
        if a_cid is not None and b_cid is not None and a_cid != b_cid:
            topic_sim = self._summary_similarity(a.topic_id, b.topic_id)
            if topic_sim >= 0.5:
                dice = self._summary_similarity(a.summary, b.summary)
                logger.debug("[Sleep] Cross-chat candidate: %s(topic=%s) <-> %s(topic=%s) topic_sim=%.2f dice=%.2f",
                              a.sid[:12], a.topic_id, b.sid[:12], b.topic_id, topic_sim, dice)
                if dice >= self._prefilter_dice:
                    return True

        return False

    # ==================== 批量 LLM 判断 ====================

    def _batch_dedup_judge(
        self,
        candidates: List[Tuple[DecisionNode, DecisionNode, float]],
    ) -> List[Tuple[str, str, str, str, str]]:
        """批量调用 LLM 做去重判断

        每批最多 10 对候选，一次 LLM 调用判断多个。
        LLM 不可用或失败时返回空列表（触发热回 Dice）。

        Returns:
            [(main_sid, candidate_sid, action, reason, info_to_merge), ...]
            action: "skip" | "merge" | "conflict" | "keep"
        """
        if not self._llm or not hasattr(self._llm, "generate"):
            return []

        batch_size = 10
        results: List[Tuple[str, str, str, str, str]] = []

        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            main = batch[0][0]

            prompt = DEEP_SLEEP_DEDUP_PROMPT.format(
                main_sid=main.sid,
                main_title=main.title or main.summary,
                main_summary=main.summary,
                main_content=(main.full_text or main.summary)[:300],
                main_topic=main.topic_id,
                main_confidence=main.confidence,
                main_version=main.version,
                main_status=main.status.value,
                decision_list=json.dumps([
                    {
                        "candidate_sid": c.sid,
                        "title": c.title or c.summary,
                        "summary": c.summary,
                        "content": (c.full_text or c.summary)[:300],
                        "topic": c.topic_id,
                    }
                    for _, c, _ in batch
                ], ensure_ascii=False, indent=2),
            )

            _dedup_temp = float(os.getenv("MEMORY_DEDUP_TEMPERATURE", "0.05"))

            try:
                resp = self._llm.generate(
                    prompt,
                    temperature=_dedup_temp,
                    response_format={"type": "json_object"},
                )
                result = json.loads(resp) if isinstance(resp, str) else resp
                for j in result.get("judgments", []):
                    action = j.get("action", "keep")
                    reason = j.get("reason", "")
                    info = j.get("info_to_merge", "")
                    results.append((batch[0][0].sid, j["candidate_sid"], action, reason, info))
            except Exception as e:
                logger.warning("[Sleep] Batch LLM call failed: %s", str(e)[:60])
                for _, c, _ in batch:
                    results.append((main.sid, c.sid, "keep", "LLM_error", ""))

        return results

    # ==================== Action 处理器 ====================

    def _handle_skip(self, main_sid: str, candidate_sid: str, reason: str) -> None:
        """处理 skip action：候选决策被主决策代表，标记 SUPERSEDED"""
        if self._graph is None:
            return
        mergee = self._graph.get_decision(candidate_sid)
        if mergee is None:
            return
        mergee.change_status(DecisionStatus.SUPERSEDED)
        mergee.add_relation(Relation(
            type=RelationType.SUPERSEDES,
            target_id=main_sid,
            description=f"Sleep dedup: skip identical ({reason})",
        ))
        self._graph.upsert_decision(mergee, "feishu-mem")
        if self._storage:
            try:
                self._storage.write_decision({"sid": mergee.sid, "status": "superseded"})
            except Exception:
                pass
        logger.debug("[Sleep] Skip: %s SUPERSEDED by %s", candidate_sid[:12], main_sid[:12])

    def _handle_conflict(self, main_sid: str, candidate_sid: str, reason: str) -> None:
        """处理 conflict action：双向标记 CONFLICTS_WITH"""
        if self._graph is None:
            return
        main_node = self._graph.get_decision(main_sid)
        candidate_node = self._graph.get_decision(candidate_sid)
        if main_node is None or candidate_node is None:
            return

        main_node.add_relation(Relation(
            type=RelationType.CONFLICTS_WITH,
            target_id=candidate_sid,
            description=reason,
        ))
        candidate_node.add_relation(Relation(
            type=RelationType.CONFLICTS_WITH,
            target_id=main_sid,
            description=reason,
        ))
        self._graph.upsert_decision(main_node, "feishu-mem")
        self._graph.upsert_decision(candidate_node, "feishu-mem")
        if self._storage:
            try:
                self._storage.write_decision({"sid": main_sid, "status": main_node.status.value})
                self._storage.write_decision({"sid": candidate_sid, "status": candidate_node.status.value})
            except Exception:
                pass
        logger.info("[Sleep] Conflict: %s <-> %s", main_sid[:12], candidate_sid[:12])

    # ==================== 内部方法 ====================

    def _pick_winner(self, a: DecisionNode, b: DecisionNode) -> bool:
        """在两条重复决策中选择保留哪条"""
        a_score = self._decision_score(a)
        b_score = self._decision_score(b)
        return a_score >= b_score

    @staticmethod
    def _decision_score(d: DecisionNode) -> float:
        """计算决策的综合价值分"""
        status_score = {
            DecisionStatus.COMPLETED: 100,
            DecisionStatus.EXECUTING: 90,
            DecisionStatus.DECIDED: 80,
            DecisionStatus.IN_DISCUSSION: 60,
            DecisionStatus.PENDING: 50,
            DecisionStatus.SUPERSEDED: 20,
            DecisionStatus.DEPRECATED: 10,
            DecisionStatus.SHELVED: 5,
        }
        s = status_score.get(d.status, 50)
        v = min(d.version, 10) * 5
        c = d.confidence * 30
        hs = (d.access_stats.hot_score if d.access_stats else 0) * 0.5
        return s + v + c + hs

    def _merge_decisions(
        self,
        keep_sid: str,
        merge_sid: str,
        info_to_merge: str = "",
        reason: str = "",
    ) -> None:
        """将 merge_sid 合并到 keep_sid

        1. 合并 tags、full_text、confidence
        2. merge_sid 标记为 SUPERSEDED，建立 SUPERSEDES 关系
        3. 刷新 version
        """
        if self._graph is None:
            return

        keeper = self._graph.get_decision(keep_sid)
        mergee = self._graph.get_decision(merge_sid)

        if keeper is None or mergee is None:
            logger.warning("[Sleep] Merge failed: sid not found keeper=%s mergee=%s", keep_sid[:12], merge_sid[:12])
            return

        keeper.add_relation(Relation(
            type=RelationType.SUPERSEDES,
            target_id=merge_sid,
            description=f"Sleep merge: supersedes {merge_sid} ({reason or f'sim={self._summary_similarity(keeper.summary, mergee.summary):.2f}'})",
        ))

        keeper.tags = list(set(keeper.tags + mergee.tags))

        if mergee.full_text and (not keeper.full_text or len(mergee.full_text) > len(keeper.full_text)):
            keeper.full_text = mergee.full_text
        elif mergee.full_text and keeper.full_text and mergee.full_text not in keeper.full_text:
            keeper.full_text += "\n\n[合并信息]\n" + mergee.full_text

        if info_to_merge and info_to_merge not in (keeper.full_text or ""):
            keeper.full_text = (keeper.full_text or "") + "\n\n[补充信息]\n" + info_to_merge

        keeper.confidence = max(keeper.confidence, mergee.confidence)
        keeper.version = max(keeper.version, mergee.version) + 1

        mergee.change_status(DecisionStatus.SUPERSEDED)
        mergee.updated_at = datetime.now()

        self._graph.upsert_decision(keeper, "feishu-mem")
        self._graph.upsert_decision(mergee, "feishu-mem")

        if self._storage:
            try:
                self._storage.write_decision({"sid": keeper.sid, "status": keeper.status.value, "version": keeper.version})
                self._storage.write_decision({"sid": mergee.sid, "status": "superseded"})
            except Exception:
                pass

        if self._task_view_syncer:
            try:
                self._task_view_syncer.sync_decision(keeper.sid)
                self._task_view_syncer.sync_decision(mergee.sid)
            except Exception:
                pass

        logger.info("[Sleep] Merged: %s v%d ← SUPERSEDED %s v%d",
                     keeper.sid[:12], keeper.version, mergee.sid[:12], mergee.version)

    @staticmethod
    def _summary_similarity(a: str, b: str) -> float:
        """Dice 系数（bigram 级别）"""
        if not a or not b:
            return 0.0
        a = a.strip().lower()
        b = b.strip().lower()

        def bigrams(s):
            return set(s[i:i + 2] for i in range(max(0, len(s) - 1)))

        a_bg, b_bg = bigrams(a), bigrams(b)
        if not a_bg or not b_bg:
            return 0.0
        return len(a_bg & b_bg) / len(a_bg | b_bg)