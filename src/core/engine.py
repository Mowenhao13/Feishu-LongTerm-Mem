from __future__ import annotations

import asyncio
import hashlib
import os
import signal
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.card.config import CardConfig
from src.card.pusher import PushEngine, PushTrigger
from src.core.engine_config import EngineConfig, EngineStatus
from src.core.mutations import DecisionMutation, MutationType
from src.graph.memory_graph import Conflict, MemoryGraph
from src.graph.snapshot import DetectorSnapshot, SnapshotManager
from src.node.node import DecisionNode
from src.node.types import DecisionStatus, ImpactLevel, Objection, Relation, RelationType
from src.prompts import REALTIME_DEDUP_PROMPT
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.llm.langfuse_config import get_langfuse, should_sample
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PipelineEngine:
    """决策管道引擎

    对应 Go 版 ref/core/pipeline.go 的 PipelineEngine。
    接收 Mutation 并在 MemoryGraph + GitStorage 中执行。
    """

    def __init__(
        self,
        memory_graph: Optional[MemoryGraph] = None,
        git_storage: Optional[GitStorage] = None,
        config: Optional[EngineConfig] = None,
    ) -> None:
        self._graph = memory_graph or MemoryGraph()
        self._storage = git_storage
        self._config = config or EngineConfig()
        self._applied_count = 0
        self._failed_count = 0
        self._mutation_history: List[Dict[str, Any]] = []

    # ==================== 入口 ====================

    def apply_mutation(self, mut: DecisionMutation) -> bool:
        """应用单个 Mutation

        对应 Go ApplyMutation, 按 mut.mtype 分发。
        自动设置 mutation timestamp 并记录到历史。
        """
        if mut.timestamp is None:
            mut.timestamp = datetime.now()

        if not mut.is_valid:
            logger.warning("Invalid mutation: sdr_id=%s, type=%s", mut.sdr_id, mut.mtype)
            self._failed_count += 1
            return False

        try:
            dispatcher = {
                MutationType.CREATE: self._apply_create,
                MutationType.UPDATE: self._apply_update,
                MutationType.STATUS_CHANGE: self._apply_status_change,
                MutationType.CONFLICT_MERGE: self._apply_conflict_merge,
                MutationType.CONFLICT_KEEP_BOTH: self._apply_conflict_keep_both,
                MutationType.OBJECTION: self._apply_objection,
                MutationType.DEPRECATE: self._apply_deprecate,
                MutationType.REVERT: self._apply_revert,
            }
            handler = dispatcher.get(mut.mtype)
            if handler is None:
                logger.error("Unknown mutation type: %s", mut.mtype)
                self._failed_count += 1
                return False

            # 从 mutation metadata 中提取 trace_id，注入 GitStorage 用于 commit 溯源
            trace_id = mut.metadata.get("trace_id") if mut.metadata else None
            if trace_id and self._storage:
                self._storage.set_trace_id(trace_id)

            result = handler(mut)
            if result:
                self._applied_count += 1
                self._record_mutation(mut)
            else:
                self._failed_count += 1
            return result

        except Exception as e:
            logger.error("Mutation failed: %s — %s", mut.mtype, e)
            self._failed_count += 1
            return False

    def _record_mutation(self, mut: DecisionMutation) -> None:
        """记录 mutation 到历史（用于审计追踪）"""
        self._mutation_history.append({
            "timestamp": mut.timestamp.isoformat() if mut.timestamp else "",
            "type": mut.mtype.value,
            "sid": mut.sdr_id,
            "topic": mut.topic,
            "old_status": mut.old_status,
            "new_status": mut.new_status,
            "summary": mut.summary or "",
        })

    def get_mutations_for_decision(self, sid: str) -> List[Dict[str, Any]]:
        """获取指定决策的所有 mutation 记录，按时间排序"""
        return [
            m for m in self._mutation_history
            if m["sid"] == sid
        ]

    def get_all_mutation_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的 mutation 历史"""
        return list(reversed(self._mutation_history))[:limit]

    def batch_apply(self, mutations: List[DecisionMutation]) -> int:
        """批量应用 Mutation，返回成功数"""
        success = 0
        for mut in mutations:
            if self.apply_mutation(mut):
                success += 1
        return success

    def validate_decision(self, node: DecisionNode) -> List[str]:
        """验证决策，返回错误列表"""
        errors: List[str] = []
        if not node.sid:
            errors.append("sid is required")
        if not node.summary:
            errors.append("summary is required")
        if not node.topic_id:
            errors.append("topic_id is required")
        return errors

    # ==================== 查询 ====================

    def get_status_summary(self) -> Dict[str, Any]:
        return {
            "applied": self._applied_count,
            "failed": self._failed_count,
            "graph_decisions": self._graph.count(),
            "storage_available": self._storage is not None,
        }

    # ==================== 8 种 Mutation ====================

    def _apply_create(self, mut: DecisionMutation) -> bool:
        """CREATE — 新建决策"""
        status = DecisionStatus(mut.new_status) if mut.new_status else DecisionStatus.PENDING
        node = DecisionNode(
            sid=mut.sdr_id,
            topic_id=mut.topic,
            title=mut.title or mut.summary,
            summary=mut.summary,
            full_text=mut.full_text,
            rationale=mut.rationale,
            status=status,
            impact_level=ImpactLevel(mut.new_impact_level) if mut.new_impact_level else ImpactLevel.MINOR,
            version=1,
            branch=f"decision/{mut.sdr_id}",
            proposer=mut.proposer,
            authority=mut.proposer or "",
            assignee=mut.executor or "",
            tags=mut.tags or [],
            confidence=mut.confidence,
            source=mut.source or "",
            parent_id=mut.parent_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        node.change_status(status)

        errors = self.validate_decision(node)
        if errors:
            logger.warning("Create validation failed: %s", errors)
            return False

        self._graph.upsert_decision(node, mut.project)

        if self._storage:
            node_dict = self._graph.node_to_dict(node)
            commit_hash = self._storage.write_decision(node_dict)
            node.git_commit_hash = commit_hash

        logger.info("Created decision: %s v%d — %s", node.sid, node.version, node.summary[:60])
        return True

    def _apply_update(self, mut: DecisionMutation) -> bool:
        """UPDATE — 覆盖更新决策（版本递增）"""
        existing = self._graph.get_decision(mut.sdr_id)
        if existing is None:
            logger.warning("Update failed: decision %s not found", mut.sdr_id)
            return False

        if mut.title:
            existing.title = mut.title
        if mut.summary:
            existing.summary = mut.summary
        if mut.full_text:
            existing.full_text = mut.full_text
        if mut.rationale:
            existing.rationale = mut.rationale
        if mut.proposer:
            existing.proposer = mut.proposer
            existing.authority = mut.proposer
        if mut.executor:
            existing.assignee = mut.executor
        if mut.tags:
            existing.tags = mut.tags
        if mut.parent_id and mut.parent_id != existing.parent_id:
            existing.parent_id = mut.parent_id
        if mut.new_status:
            try:
                existing.status = DecisionStatus(mut.new_status)
            except ValueError:
                pass
        if mut.new_impact_level:
            try:
                existing.impact_level = ImpactLevel(mut.new_impact_level)
            except ValueError:
                pass
        existing.version += 1
        existing.confidence = mut.confidence
        existing.updated_at = datetime.now()

        self._graph.upsert_decision(existing, mut.project)

        if self._storage:
            node_dict = self._graph.node_to_dict(existing)
            commit_hash = self._storage.write_decision(node_dict)
            existing.git_commit_hash = commit_hash

        logger.info("Updated decision: %s v%d", mut.sdr_id, existing.version)
        return True

    def _apply_status_change(self, mut: DecisionMutation) -> bool:
        """STATUS_CHANGE — 变更决策状态（自动记录生命周期时间戳）"""
        existing = self._graph.get_decision(mut.sdr_id)
        if existing is None:
            logger.warning("Status change failed: decision %s not found", mut.sdr_id)
            return False

        try:
            new_status = DecisionStatus(mut.new_status)
        except ValueError:
            logger.warning("Invalid status: %s", mut.new_status)
            return False

        old_status = existing.status
        existing.change_status(new_status)

        self._graph.upsert_decision(existing, mut.project)

        if self._storage:
            node_dict = self._graph.node_to_dict(existing)
            self._storage.write_decision(node_dict)

        logger.info("Status change: %s %s -> %s", mut.sdr_id, old_status.value, new_status.value)
        return True

    def _apply_conflict_merge(self, mut: DecisionMutation) -> bool:
        """CONFLICT_MERGE — 合并冲突决策

        合并两个冲突的决策为一个（保留 source 的版本）。
        """
        source = self._graph.get_decision(mut.source_sdr_id)
        target = self._graph.get_decision(mut.target_sdr_id)

        if source is None or target is None:
            logger.warning("Conflict merge failed: source/target not found")
            return False

        merged = DecisionNode(
            sid=mut.sdr_id,
            topic_id=source.topic_id or target.topic_id,
            summary=f"{source.summary}; {target.summary}",
            full_text=f"{source.full_text}\n---\n{target.full_text}",
            status=DecisionStatus.DECIDED,
            impact_level=max(source.impact_level, target.impact_level, key=lambda x: x.value),
            authority=source.authority or target.authority,
            assignee=source.assignee or target.assignee,
            tags=list(set(source.tags + target.tags)),
            confidence=max(source.confidence, target.confidence),
            created_at=source.created_at,
            updated_at=datetime.now(),
        )

        merged.add_relation(Relation(
            target_id=target.sid,
            type=RelationType.SUPERSEDES,
            description="Merged from conflict",
        ))

        self._graph.upsert_decision(merged, mut.project)
        target.change_status(DecisionStatus.SUPERSEDED)
        self._graph.upsert_decision(target, mut.project)

        if self._storage:
            self._storage.write_decision(self._graph.node_to_dict(merged))
            self._storage.write_decision(self._graph.node_to_dict(target))

        logger.info("Conflict merged: %s + %s -> %s", mut.source_sdr_id, mut.target_sdr_id, mut.sdr_id)
        return True

    def _apply_conflict_keep_both(self, mut: DecisionMutation) -> bool:
        """CONFLICT_KEEP_BOTH — 保留双方冲突

        在双方决策上都标记冲突关系，不做合并。
        """
        source = self._graph.get_decision(mut.source_sdr_id)
        target = self._graph.get_decision(mut.target_sdr_id)

        if source is None or target is None:
            logger.warning("Keep both failed: source/target not found")
            return False

        source.add_relation(Relation(
            target_id=target.sid,
            type=RelationType.CONFLICTS_WITH,
            description=f"Conflicts with {target.sid}: {mut.metadata.get('description', '')}",
        ))
        target.add_relation(Relation(
            target_id=source.sid,
            type=RelationType.CONFLICTS_WITH,
            description=f"Conflicts with {source.sid}: {mut.metadata.get('description', '')}",
        ))

        self._graph.upsert_decision(source, mut.project)
        self._graph.upsert_decision(target, mut.project)

        if self._storage:
            self._storage.write_decision(self._graph.node_to_dict(source))
            self._storage.write_decision(self._graph.node_to_dict(target))

        logger.info("Conflict kept both: %s <-> %s", mut.source_sdr_id, mut.target_sdr_id)
        return True

    def _apply_objection(self, mut: DecisionMutation) -> bool:
        """OBJECTION — 创建决策异议"""
        existing = self._graph.get_decision(mut.sdr_id)
        if existing is None:
            logger.warning("Objection failed: decision %s not found", mut.sdr_id)
            return False

        objection = Objection(
            reason=mut.objection_reason,
            author=mut.objection_author or "unknown",
            created_at=datetime.now().isoformat(),
        )

        existing.add_relation(Relation(
            target_id=mut.sdr_id,
            type=RelationType.OBJECTS_TO,
            description=f"Objection: {mut.objection_reason}",
        ))
        existing.updated_at = datetime.now()

        self._graph.upsert_decision(existing, mut.project)

        if self._storage:
            node_dict = self._graph.node_to_dict(existing)
            self._storage.write_decision(node_dict)
            self._storage.write_objection({
                "oid": f"obj_{mut.sdr_id}",
                "project": mut.project,
                "topic_id": mut.topic,
                "objection_content": mut.objection_reason,
                "author": mut.objection_author or "unknown",
                "created_at": datetime.now().isoformat(),
            })

        logger.info("Objection added to %s: %s", mut.sdr_id, mut.objection_reason[:50])
        return True

    def _apply_deprecate(self, mut: DecisionMutation) -> bool:
        """DEPRECATE — 废弃决策"""
        existing = self._graph.get_decision(mut.sdr_id)
        if existing is None:
            logger.warning("Deprecate failed: decision %s not found", mut.sdr_id)
            return False

        old_status = existing.status
        existing.change_status(DecisionStatus.DEPRECATED)

        self._graph.upsert_decision(existing, mut.project)

        if self._storage:
            node_dict = self._graph.node_to_dict(existing)
            self._storage.write_decision(node_dict)

        logger.info("Deprecated: %s (was %s)", mut.sdr_id, old_status.value)
        return True

    def _apply_revert(self, mut: DecisionMutation) -> bool:
        """REVERT — 回退到历史版本

        注意：当前简化实现，实际生产需要版本控制系统支持。
        """
        existing = self._graph.get_decision(mut.sdr_id)
        if existing is None:
            logger.warning("Revert failed: decision %s not found", mut.sdr_id)
            return False

        logger.info("Revert: %s to version %s (simplified, marking as pending)", mut.sdr_id, mut.revert_to_version)
        existing.change_status(DecisionStatus.PENDING)

        self._graph.upsert_decision(existing, mut.project)

        if self._storage:
            node_dict = self._graph.node_to_dict(existing)
            self._storage.write_decision(node_dict)

        return True


class MemoryEngine:
    """记忆系统引擎 — 长驻后台进程

    执行流程：读取配置 → 启动检测器 → 检测器返回数据并异步处理 →
    处理完后将提取到的决策信息在超图/GitStorage 中进行处理（更新 删除 合并 新建）
    """

    def __init__(
        self,
        config: Optional[EngineConfig] = None,
        detector: Any = None,
        decision_extractor: Any = None,
    ) -> None:
        self._config = config or EngineConfig.from_env()
        self._detector = detector
        self._extractor = decision_extractor
        self._status = EngineStatus()

        self._graph = MemoryGraph()
        self._storage: Optional[GitStorage] = None
        self._pipeline: Optional[PipelineEngine] = None
        self._snapshot_mgr: Optional[SnapshotManager] = None

        self._push_engine: Optional[PushEngine] = None

        self._embedder = None
        self._reranker = None

        self._hypergraph: Any = None
        self._hg_persistence: Any = None
        self._hypergraph_embedding: Any = None
        self._hypergraph_modified: bool = False

        self._memory_extractor: Optional[Any] = None
        self._entity_store: Optional[Any] = None

        self._processed_episode_hashes: Set[str] = set()
        self._task_view_syncer: Any = None

        self._sleep_manager: Any = None

        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._start_time: float = 0.0
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def graph(self) -> MemoryGraph:
        return self._graph

    @property
    def pipeline(self) -> Optional[PipelineEngine]:
        return self._pipeline

    @property
    def push_engine(self) -> Optional[PushEngine]:
        return self._push_engine

    @property
    def status(self) -> EngineStatus:
        if self._start_time:
            self._status.uptime_seconds = int(time.time() - self._start_time)
        return self._status

    # ==================== 生命周期 ====================

    def initialize(self, lark_client: Any = None) -> None:
        """初始化引擎

        1. 初始化 GitStorage（如果 STORAGE_PATH 可配置）
        2. 初始化 PipelineEngine
        3. 从 Git 加载已有决策到 MemoryGraph
        4. 初始化快照管理器
        5. 初始化推送引擎（注入飞书客户端）
        """
        logger.info("Initializing MemoryEngine...")

        try:
            self._storage = GitStorage(
                config=GitStorageConfig(work_dir=self._config.storage_path)
            )
            git_dir = Path(self._config.storage_path) / ".git"
            if git_dir.exists() and (git_dir / "HEAD").exists():
                logger.info("[Engine] Git repo verified at %s", self._config.storage_path)
            else:
                logger.warning("[Engine] Git repo not found at %s, some features disabled",
                               self._config.storage_path)
        except Exception as e:
            logger.warning("GitStorage init failed (non-fatal): %s", e)
            self._storage = None

        self._pipeline = PipelineEngine(
            memory_graph=self._graph,
            git_storage=self._storage,
            config=self._config,
        )

        if self._storage:
            try:
                self._graph.load_from_git(self._storage, self._config.project)
                self._status.decisions_loaded = self._graph.count()
                self._status.topics_loaded = self._graph.topic_count(self._config.project)
                logger.info("Loaded %d decisions, %d topics",
                            self._status.decisions_loaded, self._status.topics_loaded)
            except Exception as e:
                logger.warning("Graph load failed (non-fatal): %s", e)

        self._snapshot_mgr = SnapshotManager(
            storage_path=self._config.detector_snapshot_storage_path
        )

        try:
            from src.graph.persistence import HypergraphPersistence
            from src.structure import Hypergraph
            hg_dir = Path(self._config.storage_path) / "hypergraph"
            self._hg_persistence = HypergraphPersistence(hg_dir / "state.json")
            if self._hg_persistence.exists():
                self._hypergraph = self._hg_persistence.load()
                stats = self._hypergraph.get_stats()
                logger.info("Hypergraph loaded: decisions=%d episodes=%d topics=%d",
                            stats["decisions"], stats["episodes"], stats["topics"])

                # Load cached embeddings if available
                try:
                    self._hypergraph_embedding = self._hg_persistence.load_embeddings()
                    if self._hypergraph_embedding is not None:
                        emb_stats = self._hypergraph_embedding.get_stats()
                        logger.info("Hypergraph embeddings loaded: stats=%s", emb_stats)
                except Exception as emb_load_err:
                    logger.debug("Hypergraph embedding cache not found or invalid: %s", str(emb_load_err)[:60])
                    self._hypergraph_embedding = None
            else:
                self._hypergraph = Hypergraph()
                logger.info("No existing hypergraph found, starting fresh")
        except Exception as e:
            logger.warning("Hypergraph init failed (non-fatal): %s", e)
            from src.structure import Hypergraph
            self._hypergraph = Hypergraph()

        try:
            from src.view import TaskViewSyncer
            self._task_view_syncer = TaskViewSyncer(graph_path=self._config.storage_path)
            logger.info("[TaskView] TaskViewSyncer initialized")
        except Exception as e:
            logger.debug("[TaskView] TaskViewSyncer not available (non-fatal): %s", e)
            self._task_view_syncer = None

        try:
            from src.memory.sleep import SleepManager
            self._sleep_manager = SleepManager(
                graph=self._graph,
                pipeline=self._pipeline,
                storage=self._storage,
                hypergraph=self._hypergraph,
                hg_persistence=self._hg_persistence,
                task_view_syncer=self._task_view_syncer,
                llm_provider=self._extractor._llm if hasattr(self._extractor, "_llm") else None,
            )
            sleep_enabled = os.getenv("MEMORY_SLEEP_ENABLED", "true").lower() == "true"
            if sleep_enabled:
                logger.info("SleepManager initialized (auto-sleep ENABLED, interval=%ss)",
                            os.getenv("MEMORY_SLEEP_INTERVAL", "3600"))
            else:
                logger.info("SleepManager initialized (auto-sleep DISABLED, manual only)")
        except Exception as e:
            logger.debug("SleepManager not available (non-fatal): %s", e)
            self._sleep_manager = None

        self._push_engine = PushEngine(
            config=CardConfig.from_env(),
            memory_graph=self._graph,
            pipeline=self._pipeline,
            lark_client=lark_client,
        )
        logger.info("MemoryEngine initialized")

    async def start(self) -> None:
        """启动引擎 — 进入事件循环"""
        self._running = True
        self._start_time = time.time()
        self._loop = asyncio.get_running_loop()
        self._status.is_running = True

        logger.info("MemoryEngine starting (project=%s)", self._config.project)

        if self._detector and self._config.detector_enabled:
            task = asyncio.create_task(
                self._run_detector_loop(),
                name="detector-loop",
            )
            self._tasks.append(task)

        self._tasks.append(
            asyncio.create_task(
                self._sync_loop(),
                name="sync-loop",
            )
        )

        self._tasks.append(
            asyncio.create_task(
                self._hg_sync_loop(),
                name="hg-sync-loop",
            )
        )

        self._tasks.append(
            asyncio.create_task(
                self._sleep_loop(),
                name="sleep-loop",
            )
        )

        if self._push_engine:
            self._push_engine.start_push_scheduler()

        logger.info("MemoryEngine started with %d background tasks", len(self._tasks))

    async def stop(self) -> None:
        """停止引擎"""
        self._running = False
        self._status.is_running = False
        self._status.last_snapshot_time = datetime.now().isoformat()

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self._push_engine:
            await self._push_engine.stop()

        # Save hypergraph before stopping
        if self._hg_persistence and self._hypergraph:
            try:
                self._hg_persistence.save(self._hypergraph)
                logger.info("Hypergraph saved on stop")

                # Also persist embeddings if available
                if self._hypergraph_embedding is not None:
                    self._hg_persistence.save_embeddings(self._hypergraph_embedding)
            except Exception as e:
                logger.warning("Hypergraph save on stop failed: %s", e)

        await self._sync_dirty_to_storage()

        logger.info("MemoryEngine stopped (applied=%d, failed=%d)",
                    self._status.total_mutations_applied, self._status.failed_mutations)

    # ==================== 检测器循环 ====================

    async def _run_detector_loop(self) -> None:
        """检测器主循环 — 持续监听信号"""
        while self._running:
            try:
                await self._tick_detector()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._status.error_count += 1
                self._status.last_error = str(e)
                logger.error("Detector loop error: %s", e)

    async def _tick_detector(self) -> None:
        """单次检测轮询"""
        if not self._detector:
            await asyncio.sleep(1)
            return

        try:
            result = await self._detector.async_detect()
        except Exception:
            await asyncio.sleep(self._config.ingester_poll_interval)
            return

        if result is None:
            await asyncio.sleep(self._config.ingester_poll_interval)
            return

        if result.is_decision:
            await self._process_detection(result)

        await asyncio.sleep(self._config.ingester_poll_interval)

    # ==================== 检测结果处理 ====================

    async def _process_detection(self, detection_result: Any) -> None:
        """处理检测结果

        1. 保存快照
        2. 决策提取
        3. 冲突检测 + 应用 Mutation
        4. 同步到 GitStorage
        """
        # 生成 trace_id 贯穿整个检测流程
        trace_id = f"trc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        content = getattr(detection_result, "content", "") or str(detection_result)
        source = getattr(detection_result, "source", "im")
        content_preview = content[:80].replace("\n", " ")
        logger.info("[Engine] >>> _process_detection source=%s content=%.60s trace_id=%s", source, content_preview, trace_id)

        proc_start = time.time()

        try:
            # Step 1: Save snapshot
            if self._config.detector_snapshot_enabled and self._snapshot_mgr:
                ctx = getattr(detection_result, "context", None)
                det = getattr(detection_result, "_detection_result", detection_result)
                snapshot = DetectorSnapshot.from_detection(content, source, det, ctx)
                self._snapshot_mgr.save_snapshot(snapshot)
                self._status.last_snapshot_time = snapshot.timestamp

            # Step 2: Extract decision via LLM
            existing_decisions = self._build_existing_decisions_context()
            node = await self._extract_decision(content, source, existing_decisions=existing_decisions, trace_id=trace_id)

            # Step 3: Apply mutations
            if node:
                await self._apply_decision_mutations(node, source, trace_id=trace_id)
            else:
                logger.info("[Engine] No decision extracted from content (%.60s)", content_preview)

            elapsed = time.time() - proc_start
            logger.info("[Engine] <<< _process_detection done time=%.2fs", elapsed)
        except Exception as e:
            elapsed = time.time() - proc_start
            logger.error("[Engine] _process_detection FAILED after %.2fs: %s", elapsed, e)
            import traceback
            logger.error("[Engine] Traceback:\n%s", traceback.format_exc())

    async def _process_episode(self, episode: Any, episode_manager: Any = None) -> None:
        """处理完整 episode（完整对话上下文）

        与 _process_detection 单条消息不同，episode 包含完整的讨论上下文。
        LLM 能看到完整的对话过程，提取更准确的决策信息。

        支持语义重连：通过 episode_manager 将当前 episode 与已关闭的
        episode 进行语义相似度匹配，若匹配则复用同一 topic 和超边。

        Episode 对象需要以下属性:
            - episode.id: episode 唯一 ID
            - episode.chat_id: 群聊 ID
            - episode.full_text: 完整对话文本
            - episode.message_count: 消息数量
            - episode.messages: EpisodeMessage 列表
            - episode.to_dict(): 序列化方法
        """
        # 生成 trace_id 贯穿整个 episode 处理流程
        trace_id = f"trc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        content = episode.full_text
        chat_id = episode.chat_id
        episode_id = episode.id

        # Episode 级别内容去重：相同 content 的重复发送直接跳过
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if content_hash in self._processed_episode_hashes:
            logger.info("[Engine] Episode %s content hash %s already processed, skipping duplicate",
                        episode_id[:12], content_hash)
            return
        self._processed_episode_hashes.add(content_hash)

        logger.info("[Engine] >>> _process_episode id=%s chat=%s msgs=%d len=%d trace_id=%s",
                    episode_id[:12], chat_id[:12], episode.message_count, len(content), trace_id)

        if episode.message_count < 2 and len(content) < 100:
            logger.info("[Engine] Episode %s too short (msgs=%d, len=%d), skipping LLM extraction",
                        episode_id[:12], episode.message_count, len(content))
            return

        if self._extractor is None:
            logger.info("[Engine] No LLM extractor, cannot process episode %s", episode_id[:12])
            return

        proc_start = time.time()
        reconnected_episode_id: Optional[str] = None

        try:
            nodes = await self._extract_decision(content, "im",
                                                  existing_decisions=self._build_existing_decisions_context(),
                                                  trace_id=trace_id)

            if nodes:
                for node in nodes:
                    await self._apply_decision_mutations(node, "im", trace_id=trace_id)
            else:
                logger.info("[Engine] No decision extracted from episode %s (len=%d)",
                            episode_id[:12], len(content))

            if episode_manager is not None:
                logger.debug("[Engine] Episode %s managed by SuspendPool (reconnect handled at buffer level)",
                             episode_id[:12])

            try:
                from src.graph.builder import HypergraphBuilder
                from src.structure import EpisodeRole

                builder = HypergraphBuilder(self._extractor)
                episode_dict = episode.to_dict()

                if reconnected_episode_id is not None:
                    episode_dict["_reconnect_to"] = reconnected_episode_id
                    episode_dict["_reconnect_role"] = EpisodeRole.RECURRING.value

                if self._hypergraph is None:
                    from src.structure import Hypergraph
                    self._hypergraph = Hypergraph()

                self._hypergraph = builder.build_from_episodes(
                    [episode_dict], self._extractor,
                    existing_hypergraph=self._hypergraph,
                )
                stats = self._hypergraph.get_stats()
                if stats.get("episodes", 0) > 0:
                    logger.info("[Engine] Hypergraph updated: stats=%s", stats)

                if self._hg_persistence:
                    self._hg_persistence.save(self._hypergraph)
                    self._hypergraph_modified = True

                # ── Generate embeddings for hypergraph content ──
                if self._embedder and self._hg_persistence and stats.get("episodes", 0) > 0:
                    try:
                        from src.structure import HypergraphEmbedding
                        emb = HypergraphEmbedding.compute_from_hypergraph(
                            self._hypergraph,
                            embed_fn=self._embedder.embed,
                        )
                        self._hg_persistence.save_embeddings(emb)
                        emb_stats = emb.get_stats()
                        logger.info("[Engine] Hypergraph embeddings generated: stats=%s", emb_stats)
                    except Exception as emb_err:
                        logger.warning("[Engine] Hypergraph embedding generation skipped: %s",
                                        str(emb_err)[:60])
            except Exception as hg_err:
                logger.warning("[Engine] Hypergraph build skipped: %s", str(hg_err)[:60])

            elapsed = time.time() - proc_start
            logger.info("[Engine] <<< _process_episode done time=%.2fs", elapsed)

        except Exception as e:
            elapsed = time.time() - proc_start
            logger.error("[Engine] _process_episode FAILED after %.2fs: %s", elapsed, e)
            import traceback
            logger.error("[Engine] Traceback:\n%s", traceback.format_exc())

    async def _process_episode_v2(self, episode: Any) -> None:
        """两阶段处理 pipeline

        Stage 1: MemoryExtractor — 提取实体/关系/事实
        Stage 2: DecisionExtractor with entity context — 提取决策

        流程:
        1. 内容去重 (content hash)
        2. MemoryExtractor.extract() — 单次 LLM 调用获取实体/关系/事实
        3. 将提取结果存入 EntityStore
        4. 用实体上下文调用 DecisionExtractor.extract_with_context()
        5. 若 Stage 2 返回空，fallback 到 _extract_decision
        6. 应用决策 mutation
        """
        if self._memory_extractor is None or self._entity_store is None:
            logger.info("[Engine] Memory extractor or entity store not configured, "
                        "falling back to v1 pipeline")
            await self._process_episode(episode)
            return

        trace_id = f"trc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        content = getattr(episode, "full_text", "") or getattr(episode, "content", "")
        episode_id = getattr(episode, "id", "")
        chat_id = getattr(episode, "chat_id", "")

        if not content:
            logger.info("[Engine] v2: Empty content, skipping")
            return

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if content_hash in self._processed_episode_hashes:
            logger.info("[Engine] v2: Episode %s content hash %s already processed, skipping",
                        episode_id[:12] if episode_id else "?", content_hash)
            return
        self._processed_episode_hashes.add(content_hash)

        logger.info("[Engine] >>> _process_episode_v2 id=%s chat=%s len=%d trace_id=%s",
                    episode_id[:12] if episode_id else "?",
                    chat_id[:12] if chat_id else "?",
                    len(content), trace_id)

        proc_start = time.time()

        try:
            # ── Stage 1: Memory Extraction ──
            if hasattr(self._memory_extractor, "set_trace_id"):
                self._memory_extractor.set_trace_id(trace_id)

            existing_entity_ctx = self._entity_store.build_extraction_context()
            mem_result = await self._memory_extractor.extract(
                content,
                episode_id=episode_id,
                existing_entities=existing_entity_ctx,
            )

            logger.info("[Engine] v2 Stage 1 done: entities=%d rels=%d facts=%d",
                        len(mem_result.entities), len(mem_result.relationships),
                        len(mem_result.facts))

            # Store results
            self._entity_store.add_entities(mem_result.entities)
            self._entity_store.add_relationships(mem_result.relationships)
            self._entity_store.add_facts(mem_result.facts)

            # ── Stage 2: Decision Extraction with Entity Context ──
            entity_context = [
                {"name": e.name, "entity_type": e.entity_type}
                for e in mem_result.entities
            ]

            nodes: Any = None
            if self._extractor is not None:
                if hasattr(self._extractor, "set_trace_id"):
                    self._extractor.set_trace_id(trace_id)

                if hasattr(self._extractor, "extract_with_context"):
                    logger.info("[Engine] v2 Stage 2: Calling extract_with_context")
                    if asyncio.iscoroutinefunction(self._extractor.extract_with_context):
                        result = await self._extractor.extract_with_context(
                            content,
                            entity_context=entity_context,
                            existing_decisions=self._build_existing_decisions_context(),
                        )
                    else:
                        result = await asyncio.to_thread(
                            self._extractor.extract_with_context,
                            content,
                            entity_context,
                            self._build_existing_decisions_context(),
                        )

                    if result:
                        logger.info("[Engine] v2 Stage 2: Extracted %d decisions", len(result))
                        for item in result:
                            node = self._dict_to_node(item, "im")
                            if node:
                                await self._apply_decision_mutations(node, "im", trace_id=trace_id)
                        nodes = result
                else:
                    logger.info("[Engine] v2: extract_with_context not available, using v1 extract_decision")
                    nodes = await self._extract_decision(
                        content, "im",
                        existing_decisions=self._build_existing_decisions_context(),
                        trace_id=trace_id,
                    )
                    if nodes:
                        for node in nodes:
                            await self._apply_decision_mutations(node, "im", trace_id=trace_id)
            else:
                logger.info("[Engine] v2: No decision extractor, decisions skipped")

            # Fallback to direct extraction if Stage 2 returned nothing
            if not nodes and self._extractor is not None and hasattr(self._extractor, "extract_decision"):
                logger.info("[Engine] v2: Stage 2 returned empty, falling back to direct extraction")
                fallback = await self._extract_decision(
                    content, "im",
                    existing_decisions=self._build_existing_decisions_context(),
                    trace_id=trace_id,
                )
                if fallback:
                    for node in fallback:
                        await self._apply_decision_mutations(node, "im", trace_id=trace_id)

            elapsed = time.time() - proc_start
            logger.info("[Engine] <<< _process_episode_v2 done time=%.2fs", elapsed)

        except Exception as e:
            elapsed = time.time() - proc_start
            logger.error("[Engine] _process_episode_v2 FAILED after %.2fs: %s", elapsed, e)
            import traceback
            logger.error("[Engine] Traceback:\n%s", traceback.format_exc())

    async def _extract_decision(self, content: str, source: str,
                                 existing_decisions: Optional[List[Dict]] = None,
                                 trace_id: Optional[str] = None) -> Optional[List[DecisionNode]]:
        """使用 LLM 提取决策（支持批量返回多条决策）

        Args:
            content: 对话内容
            source: 来源 ("im", "doc", etc.)
            existing_decisions: 已有决策列表（注入到 prompt 中让 LLM 避免重复提取）
                格式: [{"title": "...", "summary": "..."}, ...]
            trace_id: 用于 Langfuse 溯源的 trace ID
        """
        if self._extractor is None:
            logger.warning("[LLM] No extractor configured, skipping LLM extraction")
            return None

        # 将 trace_id 传入 extractor，使 LLM 调用可溯源
        if hasattr(self._extractor, "set_trace_id"):
            self._extractor.set_trace_id(trace_id)

        # 注入已有决策上下文（Plan A）
        if existing_decisions:
            lines = ["⚠️ 以下决策已存在于系统中（仅作参考，不要因此跳过提取）。请分析新对话是否与已有决策冲突或需要更新，如有请正常提取新的决策事项。"]
            for d in existing_decisions:
                lines.append(f"- {d['title'] or d['summary']}")
            context = "\n".join(lines)
            content = f"{context}\n\n## 新对话\n\n{content}"
            logger.info("[LLM] Injected %d existing decisions as context", len(existing_decisions))

        content_preview = content[:80].replace("\n", " ")
        logger.info("[LLM] >>> _extract_decision source=%s len=%d content=%.60s",
                    source, len(content), content_preview)

        extract_start = time.time()

        try:
            if hasattr(self._extractor, "extract_decision"):
                logger.info("[LLM] Calling extractor.extract_decision (len=%d)", len(content))
                if asyncio.iscoroutinefunction(self._extractor.extract_decision):
                    result = await self._extractor.extract_decision(content)
                else:
                    result = await asyncio.to_thread(self._extractor.extract_decision, content)
            elif hasattr(self._extractor, "extract"):
                logger.info("[LLM] Calling extractor.extract (len=%d)", len(content))
                if asyncio.iscoroutinefunction(self._extractor.extract):
                    result = await self._extractor.extract(content)
                else:
                    result = await asyncio.to_thread(self._extractor.extract, content)
            else:
                logger.warning("[LLM] Extractor has no extract method")
                return None

            elapsed = time.time() - extract_start
            logger.info("[LLM] <<< Extract result type=%s time=%.2fs",
                        type(result).__name__, elapsed)

            # Handle list of decisions (batch extraction)
            if isinstance(result, list):
                nodes = []
                for item in result:
                    if isinstance(item, DecisionNode):
                        nodes.append(item)
                    elif isinstance(item, dict):
                        nodes.append(self._dict_to_node(item, source))
                if nodes:
                    logger.info("[LLM] Extracted %d decisions", len(nodes))
                    return nodes
                return None

            if isinstance(result, DecisionNode):
                logger.info("[LLM] Extracted decision: sid=%s summary=%.50s status=%s",
                            result.sid[:12], result.summary, result.status.value)
                return [result]
            if isinstance(result, dict):
                logger.info("[LLM] Extracted decision dict with %d keys", len(result))
                return [self._dict_to_node(result, source)]
            if result is None:
                logger.info("[LLM] No decision found in content (%.60s)", content_preview)
                return None
            logger.info("[LLM] Converting result dict to node")
            return [self._dict_to_node(result, source)]

        except Exception as e:
            elapsed = time.time() - extract_start
            logger.error("[LLM] Decision extraction FAILED after %.2fs: %s", elapsed, str(e)[:100])
            self._status.error_count += 1
            self._status.last_error = str(e)
            return None

    def _build_existing_decisions_context(self) -> Optional[List[Dict]]:
        """收集已有活跃决策，作为提取时的去重上下文

        只取每个决策的 title + summary，不暴露太多信息以控制 token 消耗。
        """
        if self._graph is None:
            return None
        try:
            all_d = self._graph.get_all_decisions()
            if not all_d:
                return None
            active = [d for d in all_d if d.status.is_active()]
            if not active:
                return None
            # 每个决策只取 title+summary，最多 50 条
            ctx = [{"title": d.title or d.summary, "summary": d.summary} for d in active[:50]]
            logger.debug("[LLM] Built existing decisions context: %d active decisions", len(ctx))
            return ctx
        except Exception as e:
            logger.warning("[LLM] Failed to build existing decisions context: %s", str(e)[:60])
            return None

    def set_embedding_reranker(self, embedder: Any = None, reranker: Any = None) -> None:
        """设置 embedding + reranker 模型用于相似度检索（可选）"""
        self._embedder = embedder
        self._reranker = reranker
        if embedder:
            logger.info("Embedding provider set for similarity search")
        if reranker:
            logger.info("Reranker provider set for similarity search")

    def set_memory_extractor(self, memory_extractor: Any = None, entity_store: Any = None) -> None:
        """设置 Stage 1 记忆提取器（MemoryExtractor）和 EntityStore

        启用两阶段管道 (_process_episode_v2)。
        """
        self._memory_extractor = memory_extractor
        self._entity_store = entity_store
        if memory_extractor:
            logger.info("Memory extractor set for 2-stage pipeline")
        if entity_store:
            logger.info("Entity store set for 2-stage pipeline")

    @staticmethod
    def _summary_similarity(a: str, b: str) -> float:
        """计算两条决策摘要的文本相似度

        使用字符级别的 Dice 系数（bigram 交集 / 总 bigram 数），
        用于重复决策检测的快速预过滤。
        """
        if not a or not b:
            return 0.0
        a = a.strip().lower()
        b = b.strip().lower()
        def bigrams(s):
            return set(s[i:i+2] for i in range(max(0, len(s)-1)))
        a_bg, b_bg = bigrams(a), bigrams(b)
        if not a_bg or not b_bg:
            return 0.0
        return len(a_bg & b_bg) / len(a_bg | b_bg)

    @staticmethod
    def _fast_prefilter(a: DecisionNode, b: DecisionNode, threshold: float = 0.15) -> bool:
        """快速预过滤：只有通过预过滤的候选才会进入 LLM 精判

        与 SleepManager._fast_prefilter 对称，保持逻辑一致：
        1. 必须同 topic
        2. Dice >= threshold（默认 0.15，低阈值高召回，由 LLM 精判做最终过滤）
        3. summary 不够时退回到 full_text 比较
        """
        if a.topic_id != b.topic_id:
            return False
        dice = MemoryEngine._summary_similarity(a.summary, b.summary)
        if dice >= threshold:
            return True
        if a.full_text and b.full_text:
            dice = MemoryEngine._summary_similarity(a.full_text, b.full_text)
            return dice >= threshold
        return False

    async def _find_similar_decision(self, node: DecisionNode, project: str) -> Tuple[Optional[DecisionNode], float]:
        """查找同一 topic 下内容相似的已有决策

        Strategy:
        1. 如果 embedding provider 可用，用 embedding+reranker 语义检索
        2. 否则 fallback 到字符二重相似度

        同步阻塞 IO（embedding HTTP、reranker HTTP）通过 asyncio.to_thread 卸到线程池，
        避免阻塞主事件循环，确保 IM WS 长连接和防抖循环不被打断。

        Returns:
            (matched_node, similarity_score)
            matched_node: 匹配到的决策节点，未找到则为 None
            similarity_score: 相似度分数 (0.0~1.0)
        """
        same_topic = self._graph.query_by_topic(project, node.topic_id)
        if not same_topic:
            return None, 0.0

        candidate_texts = [(d, d.full_text or d.summary) for d in same_topic]

        if self._embedder:
            try:
                import numpy as np
                query_text = node.full_text or node.summary
                query_vec = np.array((await asyncio.to_thread(self._embedder.embed, [query_text]))[0])
                doc_texts = [t for _, t in candidate_texts]
                doc_vecs = np.array(await asyncio.to_thread(self._embedder.embed, doc_texts))
                scores = self._embedder.cosine_similarity(query_vec, doc_vecs)

                top_indices = np.argsort(scores)[::-1][:5]
                top_candidates = [(candidate_texts[int(i)][0], float(scores[int(i)])) for i in top_indices]

                if self._reranker and top_candidates:
                    docs = [d.full_text or d.summary for d, _ in top_candidates]
                    rerank_scores = await asyncio.to_thread(self._reranker.rerank_single, query_text, docs)
                    reranked = [(top_candidates[i][0], rerank_scores[i]) for i in range(len(top_candidates))]
                    reranked.sort(key=lambda x: x[1], reverse=True)
                    top_candidates = reranked

                if top_candidates and top_candidates[0][1] > 0.5:
                    logger.info("[Similar] Found by embedding: sid=%s score=%.4f",
                                top_candidates[0][0].sid[:12], top_candidates[0][1])
                    return top_candidates[0][0], top_candidates[0][1]

                logger.info("[Similar] Embedding search no match (top=%.4f)",
                            top_candidates[0][1] if top_candidates else 0)
            except Exception as e:
                logger.warning("[Similar] Embedding search failed, fallback to bigram: %s", str(e)[:60])

        def bigram_similarity(a: str, b: str) -> float:
            if not a or not b:
                return 0.0
            def bigrams(s):
                return set(s[i:i+2] for i in range(max(0, len(s)-1)))
            a_bg, b_bg = bigrams(a), bigrams(b)
            if not a_bg or not b_bg:
                return 0.0
            return len(a_bg & b_bg) / len(a_bg | b_bg)

        for existing in same_topic:
            bsim = bigram_similarity(node.summary, existing.summary)
            if bsim >= 0.15:
                logger.info("[Similar] Found by bigram: sid=%s score=%.2f", existing.sid[:12], bsim)
                return existing, bsim

        return None, 0.0

    async def _judge_decision_duplicate(self, new_node: DecisionNode, existing_node: DecisionNode, trace_id: Optional[str] = None) -> tuple:
        """用 LLM 判断新决策与已有决策的关系

        如果两者是同父决策或存在直接父子关系，跳过 LLM 判断直接返回 create_new。

        Returns:
            (action: str, reason: str, info_to_merge: str)
            action: "skip" | "update" | "conflict" | "create_new"
        """
        # Phase 3: 同父决策是兄弟选项，不合并
        if new_node.parent_id and existing_node.parent_id and new_node.parent_id == existing_node.parent_id:
            logger.debug("[Dedup] Sibling guard: both under parent=%s, keeping both", new_node.parent_id[:12])
            return "create_new", "siblings with same parent", ""
        # 父子关系也不合并
        if new_node.parent_id == existing_node.sid or existing_node.parent_id == new_node.sid:
            logger.debug("[Dedup] Parent-child guard: skipping dedup")
            return "create_new", "parent-child relationship", ""

        if self._extractor is None:
            return "create_new", "no LLM", ""

        # Langfuse Trace: dedup_judge
        langfuse = get_langfuse()
        dedup_trace = None
        if langfuse and should_sample():
            dedup_trace = langfuse.trace(
                name="dedup_judge",
                input={"new": new_node.title, "existing": existing_node.title},
                metadata={"trace_id": trace_id or ""},
            )

        prompt = REALTIME_DEDUP_PROMPT.format(
            new_title=new_node.title or new_node.summary,
            new_summary=new_node.summary,
            new_content=(new_node.full_text or new_node.summary)[:300],
            new_topic=new_node.topic_id,
            new_confidence=new_node.confidence,
            new_source="",
            existing_title=existing_node.title or existing_node.summary,
            existing_summary=existing_node.summary,
            existing_content=(existing_node.full_text or existing_node.summary)[:300],
            existing_topic=existing_node.topic_id,
            existing_version=existing_node.version,
            existing_status=existing_node.status.value,
        )
        _dedup_temperature = float(os.getenv("MEMORY_DEDUP_TEMPERATURE", "0.05"))
        try:
            if hasattr(self._extractor, "_llm") and hasattr(self._extractor._llm, "generate"):
                resp = await self._extractor._llm.generate(
                    prompt,
                    temperature=_dedup_temperature,
                    response_format={"type": "json_object"},
                    trace_id=trace_id,
                )
                import json
                result = json.loads(resp)
                action = result.get("action", "create_new")
                reason = result.get("reason", "")
                info = result.get("info_to_merge", "")
                logger.info("[Dedup] LLM judge: action=%s reason=%.60s", action, reason)
                if dedup_trace:
                    dedup_trace.end(output={"action": action, "reason": reason})
                return action, reason, info
        except Exception as e:
            logger.warning("[Dedup] LLM judge failed: %s", str(e)[:60])
            if dedup_trace:
                dedup_trace.end(output={"status": "error", "error": str(e)})
        return "create_new", "judge_failed", ""

    async def _apply_decision_mutations(self, node: DecisionNode, source: str, trace_id: Optional[str] = None) -> None:
        """将提取的决策应用于超图和存储

        核心流程：
        1. 检查 sid 精确匹配 → UPDATE
        2. 没有 sid 匹配 → embedding+reranker 查语义相似
        3. 相似命中 → LLM 判断是否重复
        4. LLM 确认为重复 → 覆盖 UPDATE（version++）
        5. 无重复 → CREATE（version=1）
        6. 冲突检测
        """
        if self._pipeline is None:
            logger.warning("[Mutation] Pipeline not available, skipping mutation")
            return

        project = self._config.project
        logger.info("[Mutation] >>> _apply_decision_mutations sid=%s title=%.50s source=%s",
                    node.sid[:12], node.title or node.summary, source)

        existing = self._graph.get_decision(node.sid)

        # 在 mutation 中携带 trace_id，用于 Git commit 溯源
        trace_meta = {"trace_id": trace_id or ""} if trace_id else {}

        if existing:
            logger.info("[Mutation] Existing by sid: sid=%s v%d", node.sid[:12], existing.version)
            updates = DecisionMutation(
                mtype=MutationType.UPDATE,
                sdr_id=node.sid,
                project=project,
                topic=node.topic_id,
                title=node.title or node.summary,
                summary=node.summary,
                full_text=node.full_text,
                rationale=node.rationale,
                proposer=node.proposer or node.authority,
                executor=node.assignee,
                tags=node.tags,
                confidence=node.confidence,
                parent_id=node.parent_id,
                metadata={**trace_meta},
            )
            if await asyncio.to_thread(self._pipeline.apply_mutation, updates):
                self._status.total_mutations_applied += 1
                logger.info("[Mutation] UPDATE applied: sid=%s v%d", node.sid[:12], existing.version + 1)
                if self._task_view_syncer:
                    await asyncio.to_thread(self._task_view_syncer.sync_decision, node.sid)
                    logger.info("[TaskView] Sync triggered for UPDATE: sid=%s", node.sid[:12])
                if self._push_engine and self._push_engine._config.trigger_on_update:
                    await asyncio.to_thread(
                        self._push_engine.push_decision_update_card,
                        node.sid,
                        existing.status.value,
                        node.status.value,
                    )
            else:
                logger.warning("[Mutation] UPDATE FAILED: sid=%s", node.sid[:12])
            return

        similar, similar_score = await self._find_similar_decision(node, project)
        if similar:
            logger.info("[Mutation] Similar found: sid=%s summary=%.40s score=%.4f",
                        similar.sid[:12], similar.summary[:40], similar_score)

            # Plan B: Embedding 硬约束 — 强匹配时直接合并，不走 LLM judge
            if similar_score >= 0.65:
                logger.info("[Mutation] HARD constraint: score=%.4f >= 0.65, direct UPDATE", similar_score)
                node.sid = similar.sid
                node.confidence = max(node.confidence, similar.confidence)
                node.tags = list(set(node.tags + similar.tags))
            else:
                action, reason, info = await self._judge_decision_duplicate(node, similar, trace_id=trace_id)

                if action == "skip":
                    logger.info("[Mutation] SKIP: new=%s similar=%s reason=%.60s",
                                node.sid[:12], similar.sid[:12], reason)
                    return

                elif action == "update":
                    logger.info("[Mutation] UPDATE: new=%s -> similar=%s reason=%.60s",
                                node.sid[:12], similar.sid[:12], reason)
                    node.sid = similar.sid
                    if info and info not in (node.full_text or ""):
                        node.full_text = (node.full_text or "") + "\n\n[补充]\n" + info
                    node.tags = list(set(node.tags + similar.tags))
                    node.confidence = max(node.confidence, similar.confidence)
                elif action == "conflict":
                    logger.info("[Mutation] CONFLICT: new=%s vs similar=%s reason=%.60s",
                                node.sid[:12], similar.sid[:12], reason)
                    similar.add_relation(Relation(
                        type=RelationType.CONFLICTS_WITH,
                        target_id=node.sid, description=reason,
                    ))
                    node.add_relation(Relation(
                        type=RelationType.CONFLICTS_WITH,
                        target_id=similar.sid, description=reason,
                    ))
                    self._graph.upsert_decision(similar, project)
                    if self._storage:
                        await asyncio.to_thread(self._storage.write_decision,
                            self._graph.node_to_dict(similar))
                else:  # create_new
                    logger.info("[Mutation] LLM says not same: %s", reason)

        # 预过滤 + LLM 精判：对所有已有决策执行快速扫描
        # 即使 embedding 找到了相似决策，也需要检查其余决策（多冲突场景）
        all_decisions = self._graph.get_all_decisions()
        logger.info("[Mutation] Prefilter scan: new_topic=%s new_summary='%s', existing_count=%d",
                    node.topic_id, node.summary[:80], len(all_decisions))
        for existing in all_decisions:
            if existing.sid == node.sid:
                continue
            if similar and existing.sid == similar.sid:
                logger.info("[Mutation] Prefilter skip: already checked in similar path, sid=%s", existing.sid[:12])
                continue
            pf = self._fast_prefilter(node, existing)
            if not pf:
                logger.info("[Mutation] Prefilter skip: topic=%s vs %s, dice=%.3f(dice_ft=%.3f), existing_summary='%s'",
                            existing.topic_id, node.topic_id,
                            MemoryEngine._summary_similarity(node.summary, existing.summary),
                            MemoryEngine._summary_similarity((node.full_text or ""), (existing.full_text or "")),
                            existing.summary[:80])
                continue
            action, reason, info = await self._judge_decision_duplicate(node, existing, trace_id=trace_id)
            if action == "skip":
                logger.info("[Mutation] Prefilter SKIP: new=%s vs existing=%s reason=%.60s",
                            node.sid[:12], existing.sid[:12], reason)
                return
            elif action == "update":
                logger.info("[Mutation] Prefilter UPDATE: new=%s -> existing=%s reason=%.60s",
                            node.sid[:12], existing.sid[:12], reason)
                node.sid = existing.sid
                if info and info not in (node.full_text or ""):
                    node.full_text = (node.full_text or "") + "\n\n[补充]\n" + info
                node.tags = list(set(node.tags + existing.tags))
                node.confidence = max(node.confidence, existing.confidence)
                break
            elif action == "conflict":
                logger.info("[Mutation] Prefilter CONFLICT: new=%s vs existing=%s reason=%.60s",
                            node.sid[:12], existing.sid[:12], reason)
                existing.add_relation(Relation(
                    type=RelationType.CONFLICTS_WITH,
                    target_id=node.sid, description=reason,
                ))
                node.add_relation(Relation(
                    type=RelationType.CONFLICTS_WITH,
                    target_id=existing.sid, description=reason,
                ))
                self._graph.upsert_decision(existing, project)
                if self._storage:
                    await asyncio.to_thread(self._storage.write_decision,
                        self._graph.node_to_dict(existing))
                else:  # create_new
                    pass

        logger.info("[Mutation] Confirmed new decision: sid=%s v1", node.sid[:12])
        create = DecisionMutation(
            mtype=MutationType.CREATE,
            sdr_id=node.sid,
            project=project,
            topic=node.topic_id,
            title=node.title or node.summary,
            summary=node.summary,
            full_text=node.full_text,
            rationale=node.rationale,
            proposer=node.proposer or node.authority,
            executor=node.assignee,
            tags=node.tags,
            confidence=node.confidence,
            source=source,
            parent_id=node.parent_id,
            new_status=node.status.value,
            new_impact_level=node.impact_level.value,
            metadata={**trace_meta},
        )
        if await asyncio.to_thread(self._pipeline.apply_mutation, create):
            self._status.total_mutations_applied += 1
            logger.info("[Mutation] CREATE applied: sid=%s v1", node.sid[:12])
            if self._task_view_syncer:
                await asyncio.to_thread(self._task_view_syncer.sync_decision, node.sid)
                logger.info("[TaskView] Sync triggered for CREATE: sid=%s", node.sid[:12])
            if self._push_engine and self._push_engine._config.trigger_on_create:
                await asyncio.to_thread(self._push_engine.push_decision_card, node.sid, PushTrigger.CREATE)
        else:
            logger.warning("[Mutation] CREATE FAILED: sid=%s", node.sid[:12])

        conflicts = self._graph.detect_conflicts(node)
        if conflicts:
            logger.info("[Mutation] Detected %d conflict(s) for sid=%s", len(conflicts), node.sid[:12])
            for conflict in conflicts:
                logger.info("[Mutation] Conflict: %s ↔ %s — %.50s",
                            conflict.decision_a[:12], conflict.decision_b[:12], conflict.description)
                merge_mut = DecisionMutation(
                    mtype=MutationType.CONFLICT_KEEP_BOTH,
                    sdr_id=f"conflict_{node.sid}",
                    source_sdr_id=conflict.decision_a,
                    target_sdr_id=conflict.decision_b,
                    project=project,
                    topic=node.topic_id,
                    metadata={"description": conflict.description},
                )
                if await asyncio.to_thread(self._pipeline.apply_mutation, merge_mut):
                    self._status.total_mutations_applied += 1
                    logger.info("[Mutation] CONFLICT resolved: %s", conflict.decision_a[:12])
                    if self._push_engine and self._push_engine._config.trigger_on_conflict:
                        await asyncio.to_thread(
                            self._push_engine.push_conflict_card,
                            conflict.decision_a,
                            conflict.decision_b,
                            conflict.description,
                        )
        else:
            logger.info("[Mutation] No conflicts detected for sid=%s", node.sid[:12])

    # ==================== 存储同步 ====================

    async def _sync_loop(self) -> None:
        """定期同步脏决策到 GitStorage"""
        while self._running:
            try:
                await asyncio.sleep(self._config.graph_sync_interval)
                await self._sync_dirty_to_storage()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Sync loop error: %s", e)

    async def _hg_sync_loop(self) -> None:
        """定期 Git 提交 hypergraph state.json

        与 _sync_loop 不同的职责：
        - _sync_loop 同步 MemoryGraph 的脏决策（独立 .md 文件）
        - _hg_sync_loop 同步 Hypergraph 的 state.json（单一文件）

        两个回路用 graph_sync_interval 相同的调度频率，
        避免过多小提交。
        """
        while self._running:
            try:
                await asyncio.sleep(self._config.graph_sync_interval)
                if self._hypergraph_modified and self._hg_persistence and self._hypergraph:
                    try:
                        self._hg_persistence.save(self._hypergraph)
                        if self._storage:
                            await asyncio.to_thread(
                                self._storage.cli.run,
                                "add", "hypergraph/state.json",
                            )
                            await asyncio.to_thread(
                                self._storage.cli.run,
                                "commit", "-m", "hypergraph: auto-sync",
                            )
                        self._hypergraph_modified = False
                        logger.debug("Hypergraph synced to git")
                    except Exception as e:
                        logger.warning("Hypergraph git sync skipped: %s", str(e)[:60])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Hypergraph sync loop error: %s", e)

    async def _sleep_loop(self) -> None:
        """定时记忆整理（睡眠）后台循环

        受 MEMORY_SLEEP_ENABLED 环境变量控制：
        - true（默认）：按 MEMORY_SLEEP_INTERVAL 间隔自动运行
        - false：该 loop 只记录一行日志并退出，纯手动触发
        """
        sleep_enabled = os.getenv("MEMORY_SLEEP_ENABLED", "true").lower() == "true"
        if not sleep_enabled:
            logger.info("[Sleep] Auto-sleep disabled by MEMORY_SLEEP_ENABLED=false, manual only via scripts/sleep_mem.py")
            return

        interval = int(os.getenv("MEMORY_SLEEP_INTERVAL", "3600"))
        logger.info("[Sleep] Auto-sleep loop started (interval=%ds)", interval)

        while self._running:
            try:
                await asyncio.sleep(interval)
                if self._sleep_manager is None:
                    logger.debug("[Sleep] SleepManager not available, skipping")
                    continue
                logger.info("[Sleep] >>> Auto-sleep cycle triggered")
                report = await asyncio.to_thread(
                    self._sleep_manager.sleep,
                    self._processed_episode_hashes,
                )
                d = report.to_dict()
                logger.info("[Sleep] <<< Auto-sleep done: merged=%d pruned=%d promoted=%d errors=%d",
                            d.get("duplicates_merged", 0), d.get("noise_pruned", 0),
                            d.get("decisions_promoted", 0), len(d.get("errors", [])))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[Sleep] Auto-sleep cycle failed: %s", e)

    async def _sync_dirty_to_storage(self) -> None:
        if not self._storage or not self._config.graph_auto_sync:
            return
        try:
            dirty = self._graph.get_dirty_and_clean()
            if not dirty:
                return
            for node in dirty:
                node_dict = self._graph.node_to_dict(node)
                await asyncio.to_thread(self._storage.write_decision, node_dict)
            logger.info("Synced %d dirty decisions to storage", len(dirty))
        except Exception as e:
            logger.error("Storage sync failed: %s", e)

    # ==================== 公开 API ====================

    def process(self, content: str, source: str = "im") -> bool:
        """外部调用的同步处理接口"""
        if not self._detector:
            logger.warning("No detector configured")
            return False

        async def _process():
            result = await self._detector.detect(content)
            await self._process_detection(result)
            return True

        try:
            loop = self._loop or asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(_process(), loop)
                return True
            else:
                asyncio.run(_process())
                return True
        except Exception as e:
            logger.error("Process failed: %s", e)
            return False

    def sleep(self) -> dict:
        """手动触发一次记忆整理（睡眠）

        供 scripts/sleep_mem.py 或外部代码调用。
        MEMORY_SLEEP_ENABLED=false 时也可调用。
        """
        if self._sleep_manager:
            report = self._sleep_manager.sleep(self._processed_episode_hashes)
            return report.to_dict()
        logger.warning("[Sleep] SleepManager not initialized")
        return {"error": "SleepManager not initialized"}

    def retrieve(self, query: str, top_k: int = 10) -> List[DecisionNode]:
        """从 MemoryGraph 检索决策"""
        return self._graph.search_by_keywords(query)[:top_k]

    # ==================== 辅助 ====================

    @staticmethod
    def _dict_to_node(data: dict, source: str = "im") -> Optional[DecisionNode]:
        """从 dict 构建 DecisionNode"""
        try:
            import hashlib
            from datetime import datetime

            content = data.get("summary", "") or data.get("title", "") or data.get("content", "") or data.get("decision", "") or str(data)
            sid = hashlib.md5(content.encode()).hexdigest()[:12]

            topic_id = data.get("topic_id", "") or data.get("topic", "general")
            title = data.get("title", "") or ""
            summary = title or data.get("summary", "") or data.get("content", "") or data.get("decision", "") or ""
            full_text = data.get("content", "") or data.get("decision", "") or ""
            rationale = data.get("rationale", "") or ""

            status_str = data.get("status", "pending")
            try:
                status = DecisionStatus(status_str)
            except ValueError:
                status = DecisionStatus.PENDING

            impact_str = data.get("impact_level", "minor")
            try:
                impact = ImpactLevel(impact_str)
            except ValueError:
                impact = ImpactLevel.MINOR

            return DecisionNode(
                sid=sid,
                parent_id=data.get("parent_id", "") or "",
                topic_id=topic_id,
                title=title,
                summary=summary[:200],
                full_text=full_text,
                rationale=rationale,
                status=status,
                impact_level=impact,
                version=1,
                branch=f"decision/{sid}",
                tags=data.get("tags", []),
                confidence=data.get("confidence", 1.0),
                proposer=data.get("proposer", "") or data.get("authority", ""),
                authority=data.get("proposer", "") or data.get("authority", ""),
                assignee=data.get("executor", "") or data.get("assignee", ""),
                is_suggestion=bool(data.get("is_suggestion", False)),
                source=source,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        except Exception as e:
            logger.warning("Failed to convert dict to DecisionNode: %s", e)
            return None