from __future__ import annotations

import asyncio
import signal
import time
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
from src.storage.git_storage import GitStorage, GitStorageConfig
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

    # ==================== 入口 ====================

    def apply_mutation(self, mut: DecisionMutation) -> bool:
        """应用单个 Mutation

        对应 Go ApplyMutation, 按 mut.mtype 分发。
        """
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

            result = handler(mut)
            if result:
                self._applied_count += 1
            else:
                self._failed_count += 1
            return result

        except Exception as e:
            logger.error("Mutation failed: %s — %s", mut.mtype, e)
            self._failed_count += 1
            return False

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
        node = DecisionNode(
            sid=mut.sdr_id,
            topic_id=mut.topic,
            summary=mut.summary,
            full_text=mut.full_text,
            status=DecisionStatus(mut.new_status) if mut.new_status else DecisionStatus.PENDING,
            impact_level=ImpactLevel(mut.new_impact_level) if mut.new_impact_level else ImpactLevel.MINOR,
            authority=mut.proposer,
            assignee=mut.executor,
            tags=mut.tags,
            confidence=mut.confidence,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        errors = self.validate_decision(node)
        if errors:
            logger.warning("Create validation failed: %s", errors)
            return False

        self._graph.upsert_decision(node, mut.project)

        if self._storage:
            node_dict = self._graph.node_to_dict(node)
            self._storage.write_decision(node_dict)

        logger.info("Created decision: %s — %s", node.sid, node.summary[:60])
        return True

    def _apply_update(self, mut: DecisionMutation) -> bool:
        """UPDATE — 更新决策"""
        existing = self._graph.get_decision(mut.sdr_id)
        if existing is None:
            logger.warning("Update failed: decision %s not found", mut.sdr_id)
            return False

        if mut.summary:
            existing.summary = mut.summary
        if mut.full_text:
            existing.full_text = mut.full_text
        if mut.proposer:
            existing.authority = mut.proposer
        if mut.executor:
            existing.assignee = mut.executor
        if mut.tags:
            existing.tags = mut.tags
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
        existing.confidence = mut.confidence
        existing.updated_at = datetime.now()

        self._graph.upsert_decision(existing, mut.project)

        if self._storage:
            node_dict = self._graph.node_to_dict(existing)
            self._storage.write_decision(node_dict)

        logger.info("Updated decision: %s", mut.sdr_id)
        return True

    def _apply_status_change(self, mut: DecisionMutation) -> bool:
        """STATUS_CHANGE — 变更决策状态"""
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
        existing.status = new_status
        existing.updated_at = datetime.now()

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
        target.status = DecisionStatus.SUPERSEDED
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
        existing.status = DecisionStatus.DEPRECATED
        existing.updated_at = datetime.now()

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
        existing.status = DecisionStatus.PENDING
        existing.updated_at = datetime.now()

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

    def initialize(self) -> None:
        """初始化引擎

        1. 初始化 GitStorage（如果 STORAGE_PATH 可配置）
        2. 初始化 PipelineEngine
        3. 从 Git 加载已有决策到 MemoryGraph
        4. 初始化快照管理器
        """
        logger.info("Initializing MemoryEngine...")

        try:
            self._storage = GitStorage(
                config=GitStorageConfig(work_dir=self._config.storage_path)
            )
            logger.info("GitStorage initialized at %s", self._config.storage_path)
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

        self._push_engine = PushEngine(
            config=CardConfig.from_env(),
            memory_graph=self._graph,
            pipeline=self._pipeline,
            lark_client=None,
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

        self._sync_dirty_to_storage()

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
        content = getattr(detection_result, "content", "") or str(detection_result)
        source = getattr(detection_result, "source", "im")

        # Step 1: Save snapshot
        if self._config.detector_snapshot_enabled and self._snapshot_mgr:
            ctx = getattr(detection_result, "context", None)
            snapshot = DetectorSnapshot.from_detection(content, source, detection_result, ctx)
            self._snapshot_mgr.save_snapshot(snapshot)
            self._status.last_snapshot_time = snapshot.timestamp

        # Step 2: Extract decision via LLM
        node = await self._extract_decision(content, source)

        # Step 3: Apply mutations
        if node:
            await self._apply_decision_mutations(node, source)

    async def _extract_decision(self, content: str, source: str) -> Optional[DecisionNode]:
        """使用 LLM 提取决策"""
        if self._extractor is None:
            logger.warning("No extractor configured, skipping LLM extraction")
            return None

        try:
            if hasattr(self._extractor, "extract_decision"):
                if asyncio.iscoroutinefunction(self._extractor.extract_decision):
                    result = await self._extractor.extract_decision(content)
                else:
                    result = await asyncio.to_thread(self._extractor.extract_decision, content)
            elif hasattr(self._extractor, "extract"):
                if asyncio.iscoroutinefunction(self._extractor.extract):
                    result = await self._extractor.extract(content)
                else:
                    result = await asyncio.to_thread(self._extractor.extract, content)
            else:
                logger.warning("Extractor has no extract method")
                return None

            if isinstance(result, DecisionNode):
                return result
            if isinstance(result, dict):
                return self._dict_to_node(result, source)
            if result is None:
                return None
            return self._dict_to_node(result, source)

        except Exception as e:
            logger.error("Decision extraction failed: %s", e)
            self._status.error_count += 1
            self._status.last_error = str(e)
            return None

    async def _apply_decision_mutations(self, node: DecisionNode, source: str) -> None:
        """将提取的决策应用于超图和存储

        核心流程：
        1. 检查是否已有相同 sid 的决策（UPDATE）or (CREATE)
        2. 如果是已有决策，应用 StatusChange 如果状态变更
        3. 冲突检测
        4. 同步脏数据到 GitStorage
        """
        if self._pipeline is None:
            return

        project = self._config.project

        existing = self._graph.get_decision(node.sid)

        if existing:
            updates = DecisionMutation(
                mtype=MutationType.UPDATE,
                sdr_id=node.sid,
                project=project,
                topic=node.topic_id,
                summary=node.summary,
                full_text=node.full_text,
                proposer=node.authority,
                executor=node.assignee,
                tags=node.tags,
                confidence=node.confidence,
            )
            if self._pipeline.apply_mutation(updates):
                self._status.total_mutations_applied += 1
                if self._push_engine and self._push_engine._config.trigger_on_update:
                    self._push_engine.push_decision_update_card(
                        node.sid,
                        existing.status.value,
                        node.status.value,
                    )
        else:
            create = DecisionMutation(
                mtype=MutationType.CREATE,
                sdr_id=node.sid,
                project=project,
                topic=node.topic_id,
                summary=node.summary,
                full_text=node.full_text,
                proposer=node.authority,
                executor=node.assignee,
                tags=node.tags,
                confidence=node.confidence,
                new_status=node.status.value,
                new_impact_level=node.impact_level.value,
            )
            if self._pipeline.apply_mutation(create):
                self._status.total_mutations_applied += 1
                if self._push_engine:
                    self._push_engine.push_decision_card(node.sid, PushTrigger.DECISION_UPDATE)

        conflicts = self._graph.detect_conflicts(node)
        if conflicts:
            for conflict in conflicts:
                merge_mut = DecisionMutation(
                    mtype=MutationType.CONFLICT_KEEP_BOTH,
                    sdr_id=f"conflict_{node.sid}",
                    source_sdr_id=conflict.decision_a,
                    target_sdr_id=conflict.decision_b,
                    project=project,
                    topic=node.topic_id,
                    metadata={"description": conflict.description},
                )
                if self._pipeline.apply_mutation(merge_mut):
                    self._status.total_mutations_applied += 1
                    if self._push_engine and self._push_engine._config.trigger_on_conflict:
                        self._push_engine.push_conflict_card(
                            conflict.decision_a,
                            conflict.decision_b,
                            conflict.description,
                        )

    # ==================== 存储同步 ====================

    async def _sync_loop(self) -> None:
        """定期同步脏决策到 GitStorage"""
        while self._running:
            try:
                await asyncio.sleep(self._config.graph_sync_interval)
                self._sync_dirty_to_storage()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Sync loop error: %s", e)

    def _sync_dirty_to_storage(self) -> None:
        if not self._storage or not self._config.graph_auto_sync:
            return
        try:
            dirty = self._graph.get_dirty_and_clean()
            if not dirty:
                return
            for node in dirty:
                node_dict = self._graph.node_to_dict(node)
                self._storage.write_decision(node_dict)
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

    def retrieve(self, query: str, top_k: int = 10) -> List[DecisionNode]:
        """从 MemoryGraph 检索决策"""
        return self._graph.search_by_keywords(query)[:top_k]

    # ==================== 辅助 ====================

    @staticmethod
    def _dict_to_node(data: dict, source: str = "im") -> Optional[DecisionNode]:
        """从 dict 构建 DecisionNode"""
        try:
            import hashlib

            sid = data.get("sid", "") or data.get("id", "")
            if not sid:
                content = data.get("summary", "") or data.get("decision", "") or str(data)
                sid = hashlib.md5(content.encode()).hexdigest()[:12]

            topic_id = data.get("topic_id", "") or data.get("topic", "general")
            summary = data.get("title", "") or data.get("summary", "") or data.get("decision", "")
            full_text = data.get("content", "") or data.get("decision", "") or ""

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
                topic_id=topic_id,
                summary=summary[:200],
                full_text=full_text,
                status=status,
                impact_level=impact,
                tags=data.get("tags", []),
                confidence=data.get("confidence", 1.0),
                authority=data.get("proposer", "") or data.get("authority", ""),
                assignee=data.get("executor", "") or data.get("assignee", ""),
            )
        except Exception as e:
            logger.warning("Failed to convert dict to DecisionNode: %s", e)
            return None