"""实验运行器 — topic 层次聚类质量验证

从 argusbot_v3 数据集构造 episode，运行层次聚类，评估聚类质量和粒度稳定性。

用法:
    python experiments/topic_hierarchy_experiment/run_clustering.py

输出:
    eval_reports/topic_hierarchy_experiment/clustering_report.json
    eval_reports/topic_hierarchy_experiment/hierarchy_tree.txt  (文本树状图)
    eval_reports/topic_hierarchy_experiment/quality_metrics.json
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_DIR))

from graph.topic_clusterer import (
    HierarchyAssigner,
    cosine_distance_matrix,
    cosine_similarity,
)

# 数据集
ARGUSBOT_V3 = PROJECT_ROOT / "eval_dataset" / "argusbot_v3"
MESSAGES_JSONL = ARGUSBOT_V3 / "messages.jsonl"

# 输出
REPORTS_DIR = PROJECT_ROOT / "eval_reports" / "topic_hierarchy_experiment"


def load_messages(path: Path) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    logger.info("Loaded %d messages from %s", len(messages), path)
    return messages


def build_episodes(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 chat_id + topic 分组消息，构造 episode

    如果消息有 expected_decision=True 或 msg 长度超过阈值，则视为独立的 episode。
    否则按 topic 字段合并同一 chat 内的连续同 topic 消息为 episode。
    """
    # 按 chat 分组
    chat_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for msg in messages:
        chat_groups[msg.get("chat_id", "default")].append(msg)

    episodes: List[Dict[str, Any]] = []
    for chat_id, chat_msgs in chat_groups.items():
        # 按 topic 分组（保留连续顺序）
        current_topic = None
        current_segment: List[Dict[str, Any]] = []

        for msg in sorted(chat_msgs, key=lambda x: x.get("timestamp", "")):
            topic = msg.get("topic", "general")

            # 如果消息本身是决策性消息，直接创建一个 episode
            if msg.get("expected_decision", False):
                if current_segment:
                    # flush 当前 segment
                    episodes.append(_make_episode(chat_id, current_segment))
                    current_segment = []
                episodes.append(_make_episode(chat_id, [msg]))
                current_topic = None
                continue

            # topic 切换或话题变换
            if topic != current_topic and current_segment:
                episodes.append(_make_episode(chat_id, current_segment))
                current_segment = []

            current_topic = topic
            current_segment.append(msg)

        if current_segment:
            episodes.append(_make_episode(chat_id, current_segment))

    logger.info("Built %d episodes from %d messages (%d chats)",
                len(episodes), len(messages), len(chat_groups))
    return episodes


def _make_episode(chat_id: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从消息列表构造 episode dict"""
    import hashlib

    texts = [m.get("msg", "") for m in messages]
    full_text = "\n".join(texts)
    ep_id = hashlib.md5(full_text.encode()).hexdigest()[:12]

    # 提取参与者
    participants = list(dict.fromkeys(m.get("speaker", "") for m in messages if m.get("speaker")))
    participants = [p for p in participants if p]

    # 取最早时间戳
    timestamps = [m.get("timestamp", "") for m in messages if m.get("timestamp")]
    first_ts = timestamps[0] if timestamps else ""

    # 使用数据集的 topic 或从消息中推断
    topics = [m.get("topic", "general") for m in messages if m.get("topic")]
    topic = max(set(topics), key=topics.count) if topics else "general"

    return {
        "id": ep_id,
        "chat_id": chat_id,
        "participants": participants,
        "full_text": full_text,
        "summary": full_text[:200],
        "message_count": len(messages),
        "topic": topic,
        "timestamp": first_ts,
        "messages": texts[:10],  # 保留前 10 条做预览
        "n_messages": len(messages),
    }


def compute_and_embed(
    episodes: List[Dict[str, Any]],
    embedder: Any = None,
) -> Optional[np.ndarray]:
    """计算 episode embedding 向量

    优先用 embedder，fallback 到随机 mock。
    """
    texts = [
        ep.get("summary", "") or ep.get("full_text", "")
        for ep in episodes
    ]
    if not texts:
        return None

    if embedder is not None:
        logger.info("Computing embeddings for %d episodes...", len(texts))
        t0 = time.time()
        vecs = embedder.embed(texts)
        elapsed = time.time() - t0
        logger.info("Embedding done: %.2fs (%.1f ms/ep)", elapsed, elapsed / len(texts) * 1000)
        return np.array(vecs)
    else:
        logger.warning("No embedder — using synthetic random embeddings for testing")
        np.random.seed(42)
        vectors = np.random.rand(len(texts), 128).astype(float)
        return vectors


def evaluate_hierarchy_quality(
    result: Dict[str, Any],
    episodes: List[Dict[str, Any]],
    embeddings: np.ndarray,
) -> Dict[str, Any]:
    """评估层次聚类质量

    指标：
    1. 每层级 topic 数量
    2. 平均 class-inner / inter-cluster distance（Silhouette-like）
    3. 短 episode 是否分配到更高层次（hierarchy_level 更大）
    4. 数据集 ground truth topic 与聚类层级的匹配度
    """
    metrics: Dict[str, Any] = {}
    levels = result.get("levels", {})
    topic_tree = result.get("topic_tree", {})

    # 1. 每层级 topic 数量
    level_counts = {}
    for level, clusters in levels.items():
        level_counts[str(level)] = {
            "n_topics": len(clusters),
            "cluster_sizes": [c["n_episodes"] for c in clusters],
        }
    metrics["level_counts"] = level_counts

    # 2. 每层级的类内/类间距离
    level_scores = {}
    for level, clusters in levels.items():
        dist = cosine_distance_matrix(embeddings)
        n = len(embeddings)

        # 构建 assignment 数组
        assignments = np.full(n, -1, dtype=int)
        for cluster_idx, c in enumerate(clusters):
            for ep_id in c["episode_ids"]:
                for ep_idx, ep in enumerate(episodes):
                    if ep["id"] == ep_id:
                        assignments[ep_idx] = cluster_idx
                        break

        # 计算简化版 Silhouette Score
        intra_dists = []
        inter_dists = []
        for i in range(n):
            if assignments[i] < 0:
                continue
            own = assignments[i]
            same = [j for j in range(n) if assignments[j] == own and j != i]
            if same:
                intra_dists.append(np.mean([dist[i, j] for j in same]))
            for j in range(n):
                if assignments[j] != own and assignments[j] >= 0:
                    inter_dists.append(dist[i, j])
                    break

        avg_intra = np.mean(intra_dists) if intra_dists else 0
        avg_inter = np.mean(inter_dists) if inter_dists else 0
        level_scores[str(level)] = {
            "avg_intra_cluster_distance": round(float(avg_intra), 4),
            "avg_inter_cluster_distance": round(float(avg_inter), 4),
            "separation_ratio": round(float(avg_inter / max(avg_intra, 1e-9)), 4),
            "n_clusters_per_episode": n / max(len(clusters), 1),
        }
    metrics["level_coherence"] = level_scores

    # 3. 短 episode 是否分配到更具体层级
    # 对每个 episode 看它属于哪个 hierarchy_level
    ep_assignments: Dict[str, int] = {}
    for level, clusters in levels.items():
        for c in clusters:
            for ep_id in c["episode_ids"]:
                if ep_id not in ep_assignments:
                    ep_assignments[ep_id] = level
                else:
                    # 取最高的 level（最具体）
                    ep_assignments[ep_id] = max(ep_assignments[ep_id], level)

    short_eps = [ep for ep in episodes if ep.get("message_count", 1) <= 3]
    long_eps = [ep for ep in episodes if ep.get("message_count", 1) > 5]

    short_levels = [ep_assignments.get(ep["id"], -1) for ep in short_eps]
    long_levels = [ep_assignments.get(ep["id"], -1) for ep in long_eps]

    metrics["granularity_bias"] = {
        "n_short_episodes": len(short_eps),
        "n_long_episodes": len(long_eps),
        "short_ep_mean_level": round(float(np.mean(short_levels)), 2) if short_levels else 0,
        "long_ep_mean_level": round(float(np.mean(long_levels)), 2) if long_levels else 0,
        "short_vs_long_level_diff": (
            round(float(np.mean(short_levels) - np.mean(long_levels)), 2)
            if short_levels and long_levels else 0
        ),
    }

    # 4. 与 ground truth topic 的匹配度
    # 数据集的每个 message 有 topic 字段，看同一 cluster 内的 topic 一致性
    gt_topics: Dict[str, str] = {}  # episode_id -> majority topic
    for ep in episodes:
        ep_id = ep["id"]
        # 从 messages 重建 topic
        topics: List[str] = []
        chat_id = ep.get("chat_id", "")
        # 用 dataset 的 topic 字段
        dataset_topic = ep.get("topic", "general")
        gt_topics[ep_id] = dataset_topic

    # 对每个 cluster，统计 topic 分布
    topic_purity = {}
    for level, clusters in levels.items():
        cluster_purities = []
        for c in clusters:
            ep_topics = [gt_topics.get(eid, "unknown") for eid in c["episode_ids"]]
            if ep_topics:
                topic_counts = defaultdict(int)
                for t in ep_topics:
                    topic_counts[t] += 1
                majority = max(topic_counts.values())
                purity = majority / len(ep_topics)
                cluster_purities.append(purity)
        if cluster_purities:
            topic_purity[str(level)] = {
                "mean_purity": round(float(np.mean(cluster_purities)), 4),
                "min_purity": round(float(np.min(cluster_purities)), 4),
                "max_purity": round(float(np.max(cluster_purities)), 4),
            }
    metrics["topic_purity"] = topic_purity

    return metrics


def print_hierarchy_tree(result: Dict[str, Any]) -> str:
    """打印 hierarchy 树状图文本"""
    topic_tree = result.get("topic_tree", {})
    levels = result.get("levels", {})

    lines = []
    lines.append("# Topic Hierarchy Tree")
    lines.append("")
    lines.append(f"Total episodes: {result.get('n_episodes', 0)}")
    lines.append(f"Total topic nodes: {len(topic_tree)}")
    lines.append(f"Hierarchy levels: {len(levels)}")
    lines.append("")

    def print_node(topic_id: str, indent: int = 0):
        info = topic_tree.get(topic_id)
        if not info:
            return
        prefix = "  " * indent
        ep_count = len(info.get("episode_ids", []))
        level = info.get("hierarchy_level", 0)
        lines.append(f"{prefix}▸ {topic_id} [L{level}, {ep_count} eps]")

        children = [
            tid for tid, cinfo in topic_tree.items()
            if cinfo.get("parent_id") == topic_id
        ]
        for child in children:
            print_node(child, indent + 1)

    roots = [
        tid for tid, info in topic_tree.items()
        if info.get("parent_id") is None
    ]
    for root in roots:
        print_node(root, 0)

    lines.append("")
    lines.append("## Level Overview")
    lines.append("")
    for level, clusters in sorted(levels.items(), key=lambda x: int(x[0])):
        sizes = [c["n_episodes"] for c in clusters]
        lines.append(f"Level {level}: {len(clusters)} topics, "
                     f"ep per topic: min={min(sizes)} max={max(sizes)} avg={np.mean(sizes):.1f}")

    return "\n".join(lines)


def main():
    logger.info("=" * 60)
    logger.info("Topic Hierarchy Clustering Experiment")
    logger.info("=" * 60)

    # 0. 初始化 embedder
    try:
        from src.model.embedding_provider import EmbeddingProvider
        embedder = EmbeddingProvider()
        logger.info("Embedder initialized: %s", type(embedder).__name__)
    except Exception as e:
        logger.warning("Failed to init embedder: %s — falling back to random", e)
        embedder = None

    # 1. 加载数据
    if not MESSAGES_JSONL.exists():
        logger.error("Dataset not found: %s", MESSAGES_JSONL)
        return

    messages = load_messages(MESSAGES_JSONL)

    # 2. 构造 episode
    episodes = build_episodes(messages)
    logger.info("Episodes: min_msg=%d max_msg=%d avg_msg=%.1f",
                min(ep["message_count"] for ep in episodes),
                max(ep["message_count"] for ep in episodes),
                np.mean([ep["message_count"] for ep in episodes]))

    # 3. 计算 embedding
    embeddings = compute_and_embed(episodes, embedder=embedder)
    if embeddings is None:
        logger.error("Failed to compute embeddings")
        return

    # 4. 测试不同层级的聚类
    for n_levels in [2, 4, 6]:
        logger.info("---")
        logger.info("Testing with %d hierarchy levels", n_levels)

        assigner = HierarchyAssigner(n_hierarchy_levels=n_levels)
        msg_counts = [ep.get("message_count", 1) for ep in episodes]
        t0 = time.time()
        result = assigner.full_cluster(
            [ep["id"] for ep in episodes],
            embeddings,
            message_counts=msg_counts,
        )
        elapsed = time.time() - t0

        levels = result.get("levels", {})
        tree = result.get("topic_tree", {})
        logger.info("  Clustering: %.2fs", elapsed)
        logger.info("  Topic nodes: %d", len(tree))
        for level, clusters in levels.items():
            logger.info("  Level %s: %d topics", level, len(clusters))

        # 质量评估
        quality = evaluate_hierarchy_quality(result, episodes, embeddings)
        logger.info("  Cluster coherence (level 0): %s",
                     quality.get("level_coherence", {}).get("0", {}))
        logger.info("  Granularity bias: %s",
                     quality.get("granularity_bias", {}))

    # 5. 以 4 层为例，输出详细结果
    logger.info("---")
    logger.info("Detailed analysis with 4 hierarchy levels")

    assigner = HierarchyAssigner(n_hierarchy_levels=4)
    msg_counts = [ep.get("message_count", 1) for ep in episodes]
    result = assigner.full_cluster(
        [ep["id"] for ep in episodes],
        embeddings,
        message_counts=msg_counts,
    )

    # 6. 输出报告
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 质量指标
    quality = evaluate_hierarchy_quality(result, episodes, embeddings)
    report = {
        "dataset": "argusbot_v3",
        "n_messages": len(messages),
        "n_episodes": len(episodes),
        "n_levels": 4,
        "n_topic_nodes": len(result.get("topic_tree", {})),
        "level_overview": {
            str(level): {
                "n_topics": len(clusters),
                "n_episodes_covered": sum(c["n_episodes"] for c in clusters),
            }
            for level, clusters in result.get("levels", {}).items()
        },
        "quality": quality,
        "length_weighted": True,
    }
    report_path = REPORTS_DIR / "clustering_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("Report saved to %s", report_path)

    # 树状图
    tree_text = print_hierarchy_tree(result)
    tree_path = REPORTS_DIR / "hierarchy_tree.txt"
    with open(tree_path, "w", encoding="utf-8") as f:
        f.write(tree_text)
    logger.info("Tree saved to %s", tree_path)

    # 单独的质量指标（用于横向对比）
    quality_path = REPORTS_DIR / "quality_metrics.json"
    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump(quality, f, ensure_ascii=False, indent=2)
    logger.info("Quality metrics saved to %s", quality_path)

    logger.info("=" * 60)
    logger.info("Experiment complete.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()