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
            title=mut.title or mut.summary,
            summary=mut.summary,
            full_text=mut.full_text,
            rationale=mut.rationale,
            status=DecisionStatus(mut.new_status) if mut.new_status else DecisionStatus.PENDING,
            impact_level=ImpactLevel(mut.new_impact_level) if mut.new_impact_level else ImpactLevel.MINOR,
            version=1,
            branch=f"decision/{mut.sdr_id}",
            proposer=mut.proposer,
            authority=mut.proposer or "",
            assignee=mut.executor or "",
            tags=mut.tags or [],
            confidence=mut.confidence,
            source=mut.source or "",
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


DUPLICATE_JUDGE_PROMPT = """你是一个决策去重判断助手。判断两条决策是否是同一决策（内容相近、主题相同）。

新提取的决策：
标题: {new_title}
摘要: {new_summary}
内容: {new_content}
主题: {new_topic}

已有的决策：
标题: {existing_title}
摘要: {existing_summary}
内容: {existing_content}
主题: {existing_topic}

请判断：
1. 这两条决策是否描述同一个决策事项？（是/否）
2. 新决策是否应该覆盖旧决策？（是/否 — 如果新决策提供了更完整或更新的信息，则应覆盖）

返回 JSON：
{{"is_same": true/false, "should_overwrite": true/false, "reason": "简要说明"}}"""


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
        content = getattr(detection_result, "content", "") or str(detection_result)
        source = getattr(detection_result, "source", "im")
        content_preview = content[:80].replace("\n", " ")
        logger.info("[Engine] >>> _process_detection source=%s content=%.60s", source, content_preview)

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
            node = await self._extract_decision(content, source)

            # Step 3: Apply mutations
            if node:
                await self._apply_decision_mutations(node, source)
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
        content = episode.full_text
        chat_id = episode.chat_id
        episode_id = episode.id

        logger.info("[Engine] >>> _process_episode id=%s chat=%s msgs=%d len=%d",
                    episode_id[:12], chat_id[:12], episode.message_count, len(content))

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
            node = await self._extract_decision(content, "im")

            if node:
                await self._apply_decision_mutations(node, "im")
            else:
                logger.info("[Engine] No decision extracted from episode %s (len=%d)",
                            episode_id[:12], len(content))

            if episode_manager is not None:
                try:
                    episode_manager.register_closed_episode(episode)
                    similar = episode_manager.find_similar_episode(episode)
                    if similar is not None:
                        reconnected_episode_id = similar.episode_id
                        episode.topic = similar.topic
                        logger.info("[Engine] Episode %s reconnected to %s (topic=%s)",
                                    episode.id[:12], similar.episode_id[:12],
                                    similar.topic)
                except Exception as e:
                    logger.warning("[Engine] Semantic reconnection failed: %s", str(e)[:60])

            try:
                from src.graph.builder import HypergraphBuilder
                from src.structure import EpisodeRole

                builder = HypergraphBuilder(self._extractor)
                episode_dict = episode.to_dict()

                if reconnected_episode_id is not None:
                    episode_dict["_reconnect_to"] = reconnected_episode_id
                    episode_dict["_reconnect_role"] = EpisodeRole.RECURRING.value

                hypergraph = builder.build_from_episodes([episode_dict], self._extractor)
                stats = hypergraph.get_stats()
                if stats.get("episodes", 0) > 0:
                    logger.info("[Engine] Hypergraph built: stats=%s", stats)
            except Exception as hg_err:
                logger.warning("[Engine] Hypergraph build skipped: %s", str(hg_err)[:60])

            elapsed = time.time() - proc_start
            logger.info("[Engine] <<< _process_episode done time=%.2fs", elapsed)

        except Exception as e:
            elapsed = time.time() - proc_start
            logger.error("[Engine] _process_episode FAILED after %.2fs: %s", elapsed, e)
            import traceback
            logger.error("[Engine] Traceback:\n%s", traceback.format_exc())

    async def _extract_decision(self, content: str, source: str) -> Optional[DecisionNode]:
        """使用 LLM 提取决策"""
        if self._extractor is None:
            logger.warning("[LLM] No extractor configured, skipping LLM extraction")
            return None

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

            if isinstance(result, DecisionNode):
                logger.info("[LLM] Extracted decision: sid=%s summary=%.50s status=%s",
                            result.sid[:12], result.summary, result.status.value)
                return result
            if isinstance(result, dict):
                logger.info("[LLM] Extracted decision dict with %d keys", len(result))
                return self._dict_to_node(result, source)
            if result is None:
                logger.info("[LLM] No decision found in content (%.60s)", content_preview)
                return None
            logger.info("[LLM] Converting result dict to node")
            return self._dict_to_node(result, source)

        except Exception as e:
            elapsed = time.time() - extract_start
            logger.error("[LLM] Decision extraction FAILED after %.2fs: %s", elapsed, str(e)[:100])
            self._status.error_count += 1
            self._status.last_error = str(e)
            return None

    def set_embedding_reranker(self, embedder: Any = None, reranker: Any = None) -> None:
        """设置 embedding + reranker 模型用于相似度检索（可选）"""
        self._embedder = embedder
        self._reranker = reranker
        if embedder:
            logger.info("Embedding provider set for similarity search")
        if reranker:
            logger.info("Reranker provider set for similarity search")

    async def _find_similar_decision(self, node: DecisionNode, project: str) -> Optional[DecisionNode]:
        """查找同一 topic 下内容相似的已有决策

        Strategy:
        1. 如果 embedding provider 可用，用 embedding+reranker 语义检索
        2. 否则 fallback 到字符二重相似度

        同步阻塞 IO（embedding HTTP、reranker HTTP）通过 asyncio.to_thread 卸到线程池，
        避免阻塞主事件循环，确保 IM WS 长连接和防抖循环不被打断。
        """
        same_topic = self._graph.query_by_topic(project, node.topic_id)
        if not same_topic:
            return None

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
                    return top_candidates[0][0]

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
            if bigram_similarity(node.summary, existing.summary) >= 0.35:
                logger.info("[Similar] Found by bigram: sid=%s", existing.sid[:12])
                return existing

        return None

    async def _judge_decision_duplicate(self, new_node: DecisionNode, existing_node: DecisionNode) -> tuple:
        """用 LLM 判断新决策是否与已有决策重复

        Returns:
            (is_same: bool, should_overwrite: bool, reason: str)
        """
        if self._extractor is None:
            return False, False, "no LLM"

        prompt = DUPLICATE_JUDGE_PROMPT.format(
            new_title=new_node.title or new_node.summary,
            new_summary=new_node.summary,
            new_content=(new_node.full_text or new_node.summary)[:300],
            new_topic=new_node.topic_id,
            existing_title=existing_node.title or existing_node.summary,
            existing_summary=existing_node.summary,
            existing_content=(existing_node.full_text or existing_node.summary)[:300],
            existing_topic=existing_node.topic_id,
        )
        try:
            if hasattr(self._extractor, "_llm") and hasattr(self._extractor._llm, "generate"):
                resp = await self._extractor._llm.generate(
                    prompt,
                    response_format={"type": "json_object"},
                )
                import json
                result = json.loads(resp)
                is_same = result.get("is_same", False)
                should_overwrite = result.get("should_overwrite", False)
                reason = result.get("reason", "")
                logger.info("[Dedup] LLM judge: is_same=%s overwrite=%s reason=%.60s",
                            is_same, should_overwrite, reason)
                return is_same, should_overwrite, reason
        except Exception as e:
            logger.warning("[Dedup] LLM judge failed: %s", str(e)[:60])
        return False, False, "judge_failed"

    async def _apply_decision_mutations(self, node: DecisionNode, source: str) -> None:
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
            )
            if await asyncio.to_thread(self._pipeline.apply_mutation, updates):
                self._status.total_mutations_applied += 1
                logger.info("[Mutation] UPDATE applied: sid=%s v%d", node.sid[:12], existing.version + 1)
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

        similar = await self._find_similar_decision(node, project)
        if similar:
            logger.info("[Mutation] Similar found: sid=%s summary=%.40s — judging by LLM",
                        similar.sid[:12], similar.summary[:40])
            is_same, should_overwrite, reason = await self._judge_decision_duplicate(node, similar)
            if is_same and should_overwrite:
                logger.info("[Mutation] LLM confirmed duplicate, overwriting: old_sid=%s new_sid=%s reason=%.40s",
                            similar.sid[:12], node.sid[:12], reason)
                node.sid = similar.sid
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
                )
                if await asyncio.to_thread(self._pipeline.apply_mutation, updates):
                    self._status.total_mutations_applied += 1
                    logger.info("[Mutation] OVERWRITE applied: sid=%s v%d", node.sid[:12], similar.version + 1)
                    if self._push_engine:
                        await asyncio.to_thread(self._push_engine.push_decision_card, node.sid, PushTrigger.DECISION_UPDATE)
                else:
                    logger.warning("[Mutation] OVERWRITE FAILED: sid=%s", node.sid[:12])
                return
            elif is_same and not should_overwrite:
                logger.info("[Mutation] LLM says same but don't overwrite: %s", reason)
                return
            else:
                logger.info("[Mutation] LLM says not same: %s", reason)

        logger.info("[Mutation] New decision: sid=%s status=%s impact=%s",
                    node.sid[:12], node.status.value, node.impact_level.value)
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
            new_status=node.status.value,
            new_impact_level=node.impact_level.value,
        )
        if await asyncio.to_thread(self._pipeline.apply_mutation, create):
            self._status.total_mutations_applied += 1
            logger.info("[Mutation] CREATE applied: sid=%s v1", node.sid[:12])
            if self._push_engine:
                await asyncio.to_thread(self._push_engine.push_decision_card, node.sid, PushTrigger.DECISION_UPDATE)
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

            sid = data.get("sid", "") or data.get("id", "")
            if not sid:
                content = data.get("summary", "") or data.get("decision", "") or str(data)
                sid = hashlib.md5(content.encode()).hexdigest()[:12]

            topic_id = data.get("topic_id", "") or data.get("topic", "general")
            title = data.get("title", "") or ""
            summary = title or data.get("summary", "") or data.get("decision", "") or ""
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
                source=source,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        except Exception as e:
            logger.warning("Failed to convert dict to DecisionNode: %s", e)
            return None