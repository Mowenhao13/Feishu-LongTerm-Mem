from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from src.card.config import CardConfig
from src.card.renderer import CardRenderer, HotCategory
from src.node.node import DecisionNode
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PushTrigger(str, Enum):
    CREATE = "create"
    CONFLICT = "conflict"
    DECISION_UPDATE = "decision_update"
    HOT_SCORE_LOW = "hot_score_low"
    SCHEDULED_DAILY = "scheduled_daily"
    SCHEDULED_WEEKLY = "scheduled_weekly"
    MANUAL_QUERY = "manual_query"


class PushChannel(str, Enum):
    FEISHU = "feishu"
    TERMINAL = "terminal"
    OSASCRIPT = "osascript"


@dataclass
class PushEvent:
    trigger: PushTrigger
    channel: PushChannel
    sdr_ids: List[str]
    card_json: Optional[Dict[str, Any]] = None
    markdown_text: Optional[str] = None
    timestamp: str = ""


class PushEngine:
    def __init__(
        self,
        config: Optional[CardConfig] = None,
        memory_graph: Any = None,
        pipeline: Any = None,
        lark_client: Any = None,
    ) -> None:
        self._config = config or CardConfig.from_env()
        self._graph = memory_graph
        self._pipeline = pipeline
        self._lark = lark_client
        self._renderer = CardRenderer()
        self._pushed_set: Set[str] = set()
        self._running = False
        self._tasks: List[asyncio.Task] = []

    # ==================== 公开推送方法 ====================

    def set_lark_client(self, lark_client: Any) -> None:
        """设置飞书客户端（初始化时可调用）"""
        self._lark = lark_client
        if lark_client is not None:
            logger.info("PushEngine: lark_client set")
        else:
            logger.warning("PushEngine: lark_client cleared")

    def push_decision_card(self, sdr_id: str, trigger: PushTrigger = PushTrigger.MANUAL_QUERY) -> bool:
        """推送单条决策卡片到所有启用的渠道"""
        if self._graph is None:
            logger.warning("MemoryGraph not available, cannot push")
            return False

        node = self._graph.get_decision(sdr_id)
        if node is None:
            logger.warning("Decision %s not found in graph", sdr_id)
            return False

        hot_score = node.access_stats.hot_score if node.access_stats else 50.0
        card_json = self._renderer.render_decision_card(node, hot_score)
        markdown = self._render_markdown_from_node(node, hot_score)

        self._pushed_set.add(sdr_id)
        self._increment_hot_score(node)

        return self._dispatch(trigger, [sdr_id], card_json, markdown)

    def push_conflict_card(
        self,
        sdr_id_a: str,
        sdr_id_b: str,
        reason: str = "",
        trigger: PushTrigger = PushTrigger.CONFLICT,
    ) -> bool:
        if self._graph is None:
            return False
        node_a = self._graph.get_decision(sdr_id_a)
        node_b = self._graph.get_decision(sdr_id_b)
        if node_a is None or node_b is None:
            return False

        card_json = self._renderer.render_conflict_card(node_a, node_b, reason)
        markdown = f"## ⚠️ 决策冲突\n\n**A**: {node_a.summary}\n**B**: {node_b.summary}\n\n{reason}"

        self._pushed_set.add(sdr_id_a)
        self._pushed_set.add(sdr_id_b)
        self._increment_hot_score(node_a)
        self._increment_hot_score(node_b)

        return self._dispatch(trigger, [sdr_id_a, sdr_id_b], card_json, markdown)

    def push_daily_summary(self) -> bool:
        """推送每日摘要"""
        if self._graph is None:
            return False

        all_decisions = self._graph.get_all_decisions()
        new_decisions: List[tuple[str, str, float]] = []
        forgotten_decisions: List[tuple[str, str, float]] = []

        now = datetime.now()
        for d in all_decisions:
            hs = d.access_stats.hot_score if d.access_stats else 50.0
            if d.created_at and d.created_at > now - timedelta(days=1):
                new_decisions.append((d.sid, d.summary, hs))
            if d.access_stats and d.access_stats.hot_score < self._config.hot_score_low_threshold:
                forgotten_decisions.append((d.sid, d.summary, d.access_stats.hot_score))

        markdown = self._renderer.render_daily_summary_markdown(
            now.strftime("%Y-%m-%d"), new_decisions, forgotten_decisions
        )
        return self._dispatch(PushTrigger.SCHEDULED_DAILY, [], None, markdown)

    def push_decision_update_card(self, sdr_id: str, old_status: str, new_status: str) -> bool:
        node = self._graph.get_decision(sdr_id) if self._graph else None
        if node is None:
            return False
        hot_score = node.access_stats.hot_score if node.access_stats else 50.0
        card_json = self._renderer.render_decision_card(node, hot_score)
        markdown = f"## 🔄 决策状态更新\n\n**{node.summary}**\n`{old_status}` → `{new_status}`"
        self._pushed_set.add(sdr_id)
        self._increment_hot_score(node)
        return self._dispatch(PushTrigger.DECISION_UPDATE, [sdr_id], card_json, markdown)

    def push_low_hot_score_decisions(self) -> bool:
        if self._graph is None:
            return False
        all_decisions = self._graph.get_all_decisions()
        low = [d for d in all_decisions if d.access_stats and d.access_stats.hot_score < self._config.hot_score_low_threshold]
        if not low:
            return False

        markdown_lines = [f"## 💤 遗忘决策提醒 ({len(low)} 个)"]
        for d in low[:5]:
            hs = d.access_stats.hot_score if d.access_stats else 0
            markdown_lines.append(f"- **{d.sid[:8]}**: {d.summary[:40]} — 🔥{hs:.0f}")
            self._pushed_set.add(d.sid)
        markdown = "\n".join(markdown_lines)
        return self._dispatch(PushTrigger.HOT_SCORE_LOW, [d.sid for d in low[:5]], None, markdown)

    # ==================== 定时任务调度 ====================

    def start_push_scheduler(self) -> None:
        """启动推送调度器（注册 asyncio 定时任务）"""
        if self._running:
            logger.warning("Push scheduler already running")
            return
        self._running = True

        if self._config.trigger_on_conflict:
            logger.info("Push scheduler: conflict trigger enabled")
        if self._config.trigger_on_update:
            logger.info("Push scheduler: update trigger enabled")
        if self._config.trigger_on_hot_score_threshold:
            self._tasks.append(
                asyncio.create_task(
                    self._hot_score_scan_loop(),
                    name="push-hot-score-scan",
                )
            )
            logger.info("Push scheduler: hot score scan enabled (interval=%ds)", self._config.hot_score_scan_interval)
        if self._config.enable_daily_summary:
            self._tasks.append(
                asyncio.create_task(
                    self._scheduled_daily_task(),
                    name="push-daily-summary",
                )
            )
            logger.info("Push scheduler: daily summary enabled (time=%s)", self._config.daily_summary_time)
            if self._config.weekly_summary_day:
                self._tasks.append(
                    asyncio.create_task(
                        self._scheduled_weekly_task(),
                        name="push-weekly-summary",
                    )
                )
                logger.info("Push scheduler: weekly summary enabled (day=%s, time=%s)",
                            self._config.weekly_summary_day, self._config.weekly_summary_time)

        logger.info("Push scheduler started with %d background tasks", len(self._tasks))

    async def stop(self) -> None:
        """停止推送调度器"""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Push scheduler stopped")

    async def _scheduled_daily_task(self) -> None:
        """每日定时推送摘要"""
        while self._running:
            try:
                now = datetime.now()
                target = self._parse_time(self._config.daily_summary_time)
                next_run = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
                delay = (next_run - now).total_seconds()
                await asyncio.sleep(delay)
                if not self._running:
                    break
                self.push_daily_summary()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Daily summary task error: %s", e)
                await asyncio.sleep(60)

    async def _scheduled_weekly_task(self) -> None:
        """每周定时推送摘要"""
        while self._running:
            try:
                now = datetime.now()
                target = self._parse_time(self._config.weekly_summary_time)
                target_day = int(self._config.weekly_summary_day)
                days_ahead = (target_day - now.weekday()) % 7
                if days_ahead == 0 and now.time() >= target:
                    days_ahead = 7
                next_run = (now + timedelta(days=days_ahead)).replace(
                    hour=target.hour, minute=target.minute, second=0, microsecond=0
                )
                delay = (next_run - now).total_seconds()
                await asyncio.sleep(delay)
                if not self._running:
                    break
                self.push_daily_summary()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Weekly summary task error: %s", e)
                await asyncio.sleep(60)

    async def _hot_score_scan_loop(self) -> None:
        """热点值扫描循环 — 定期检查低热点决策并推送"""
        while self._running:
            try:
                await asyncio.sleep(self._config.hot_score_scan_interval)
                if not self._running:
                    break
                self._decay_all_hot_scores()
                self.push_low_hot_score_decisions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Hot score scan error: %s", e)

    # ==================== 热点值管理 ====================

    def _increment_hot_score(self, node: DecisionNode) -> None:
        """推送后递增热点值"""
        if node.access_stats:
            node.access_stats.hot_score = min(
                100.0,
                node.access_stats.hot_score + self._config.push_hot_score_increment,
            )
        if self._graph:
            self._graph.upsert_decision(node, "feishu-mem")

    def _decay_all_hot_scores(self) -> None:
        """所有决策的热点值随时间衰减"""
        if self._graph is None:
            return
        all_decisions = self._graph.get_all_decisions()
        for node in all_decisions:
            if node.access_stats:
                node.access_stats.hot_score = max(
                    0.0,
                    node.access_stats.hot_score * self._config.hot_score_decay_rate,
                )
        logger.debug("Decayed hot scores for %d decisions", len(all_decisions))

    # ==================== 调度 ====================

    def _dispatch(
        self,
        trigger: PushTrigger,
        sdr_ids: List[str],
        card_json: Optional[Dict],
        markdown: Optional[str],
    ) -> bool:
        """根据配置分发到启用的渠道"""
        success = False

        # 确定推送目标群聊列表
        target_ids = list(self._config.card_chat_ids) if self._config.card_chat_ids else []

        if self._config.enable_feishu and self._lark is not None and target_ids:
            from src.adapter.lark_im import MessageContent
            content = MessageContent.interactive(card_json) if card_json else MessageContent.text(markdown or "")
            for chat_id in target_ids:
                try:
                    self._lark.send_message(
                        chat_id,
                        content,
                        self._config.feishu_receive_id_type,
                    )
                    logger.info("Feishu push OK: trigger=%s, chat=%s, sdr_ids=%s",
                                trigger.value, chat_id[:16], sdr_ids)
                    success = True
                except Exception as e:
                    logger.warning("Feishu push failed (chat=%s, degraded to terminal): %s",
                                   chat_id[:16], e)

        if self._config.enable_terminal:
            self._output_to_terminal(trigger, markdown or card_json or {})
            success = True

        if self._config.enable_osascript:
            self._output_osascript(markdown or "")
            success = True

        return success

    def _output_to_terminal(self, trigger: PushTrigger, content: Any) -> None:
        """终端输出推送内容"""
        header = (
            f"\n{'='*60}\n"
            f"📬 决策推送 [trigger: {trigger.value}] — {datetime.now().strftime('%H:%M:%S')}\n"
            f"{'='*60}"
        )
        print(header)
        if isinstance(content, dict):
            print(json.dumps(content, ensure_ascii=False, indent=2)[:2000])
        else:
            print(str(content)[:2000])
        print(f"{'='*60}\n")

    def _output_osascript(self, text: str) -> None:
        """macOS 系统通知"""
        try:
            title = text.split("\n")[0][:50] if text else "决策推送"
            snippet = text[:150].replace('"', "'").replace("\n", " ") if text else ""
            cmd = f'osascript -e \'display notification "{snippet}" with title "{title}"\''
            subprocess.run(cmd, shell=True, timeout=3, capture_output=True)
        except Exception as e:
            logger.warning("osascript failed: %s", e)

    # ==================== 辅助 ====================

    @staticmethod
    def _render_markdown_from_node(node: DecisionNode, hot_score: float) -> str:
        return (
            f"## 📋 决策卡片 [{node.sid[:8]}]\n\n"
            f"**{node.summary}**\n\n"
            f"- 状态: `{node.status.value}`\n"
            f"- 影响: `{node.impact_level.value}`\n"
            f"- 议题: `{node.topic_id}`\n"
            f"- 提议者: {node.authority or '未知'}\n"
            f"- 🔥 热点值: {hot_score:.0f}/100\n"
        )

    @staticmethod
    def _parse_time(time_str: str) -> time:
        try:
            parts = time_str.split(":")
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return time(8, 0)