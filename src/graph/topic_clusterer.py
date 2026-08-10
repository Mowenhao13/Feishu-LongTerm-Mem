"""层次化 Topic 聚类引擎

基于 Episode embedding 的层次凝聚聚类（HAC），构建 topic 层级树。

核心流程：
1. 对所有 episode 文本计算 embedding 向量
2. 对 embedding 做 HAC 聚类（average linkage）
3. 在 N 个不同阈值处切割树状图，产生 N 层 topic 层级
4. 短 episode（消息数少）的距离被加权放大 → 更倾向形成具体 cluster
   长 episode（消息数多）的距离被加权压缩 → 更倾向归入抽象 cluster

用法：
    clusterer = TopicClusterer(embedding_provider)
    hierarchy = clusterer.full_cluster(episodes)
    # hierarchy 包含 TopicNode 列表 + parent/children 关系

    assigner = HierarchyAssigner(threshold=0.7)
    assigned = assigner.incremental_assign(episode, hierarchy)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
#  数据类型
# ============================================================


@dataclass
class ClusterResult:
    """单个聚类结果"""
    cluster_id: int
    episode_ids: List[str]
    centroid: np.ndarray
    hierarchy_level: int


@dataclass
class HierarchyResult:
    """完整层次聚类结果"""
    topic_tree: Dict[str, Any]  # parent_id -> children
    clusters_by_level: Dict[int, List[ClusterResult]]
    merge_history: np.ndarray  # (n-1, 2) merge pairs
    merge_distances: np.ndarray  # (n-1,) merge distances
    level_thresholds: List[float]
    n_episodes: int


# ============================================================
#  距离矩阵
# ============================================================


def cosine_distance_matrix(embeddings: np.ndarray) -> np.ndarray:
    """计算两两余弦距离矩阵

    Args:
        embeddings: (n, d) numpy array

    Returns:
        (n, n) 距离矩阵，范围 [0, 2]
    """
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / np.maximum(norms, 1e-9)
    similarity = np.dot(normalized, normalized.T)
    # 裁剪浮点误差
    similarity = np.clip(similarity, -1.0, 1.0)
    return 1.0 - similarity


def weighted_distance_matrix(
    embeddings: np.ndarray,
    message_counts: List[int],
) -> np.ndarray:
    """基于消息数的长度加权距离矩阵

    短 episode（消息数少）→ 距离放大 → 更倾向形成具体 cluster
    长 episode（消息数多）→ 距离压缩 → 更倾向归入抽象 cluster

    Args:
        embeddings: (n, d) numpy array
        message_counts: 每个 episode 的消息数（必须与 embeddings 下标对齐）

    Returns:
        (n, n) 加权距离矩阵
    """
    n = embeddings.shape[0]
    dist = cosine_distance_matrix(embeddings)

    # 归一化消息数到 [0.5, 2.0] 范围
    lengths = np.array(message_counts, dtype=float)
    length_mean = np.mean(lengths)
    if length_mean > 0:
        lengths = lengths / length_mean  # 居中于 1.0
    else:
        lengths = np.ones(n)
    lengths = np.clip(lengths, 0.5, 2.0)

    # 归一化消息数
    lengths = np.array(message_counts, dtype=float)
    length_mean = np.mean(lengths)
    if length_mean > 0:
        lengths = lengths / length_mean  # 居中于 1.0
    else:
        lengths = np.ones(n)
    lengths = np.clip(lengths, 0.5, 2.0)

    for i in range(n):
        for j in range(i + 1, n):
            # 两个都短（length < 1）：放大距离 → 各自形成具体 topic
            # 两个都长（length > 1）：压缩距离 → 归入抽象 topic
            # 一短一长：保持原距离
            if lengths[i] < 1.0 and lengths[j] < 1.0:
                factor = (2.0 - np.sqrt(lengths[i] * lengths[j]))
                dist[i, j] = dist[i, j] * factor
            elif lengths[i] > 1.0 and lengths[j] > 1.0:
                factor = np.sqrt(lengths[i] * lengths[j])
                dist[i, j] = dist[i, j] / factor

    return dist


# ============================================================
#  HAC 聚类（纯 numpy，average linkage）
# ============================================================


def hac_cluster(dist_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """层次凝聚聚类（HAC），average linkage

    纯 numpy 实现 O(n³)。大量数据（n>500）时应考虑换用 priority-queue 变体，
    或用 scipy.cluster.hierarchy.linkage。

    实现策略：维护一个缩小的距离矩阵 D，每次合并后：
    1. 用合并后的 cluster 更新行 i
    2. 将行/列 j 替换为最后一行/列后裁剪矩阵
    3. 更新 cluster_sizes 和 cluster_labels 追踪映射

    Args:
        dist_matrix: (n, n) 距离矩阵

    Returns:
        merge_history: (n-1, 2) 每次合并的两个 cluster 索引（原始索引）
        merge_distances: (n-1,) 每次合并时的距离
    """
    n = dist_matrix.shape[0]
    if n == 0:
        return np.array([]).reshape(0, 2), np.array([])
    if n == 1:
        return np.array([]).reshape(0, 2), np.array([])

    # 工作距离矩阵
    D = dist_matrix.copy().astype(float)
    np.fill_diagonal(D, np.inf)

    # cluster_sizes[i] = 当前 active cluster i 包含的原始元素数
    cluster_sizes = np.ones(n, dtype=float)

    # cluster_labels[i] = active cluster i 中第一个原始元素的索引（用于 merge_history 追踪）
    cluster_labels = np.arange(n, dtype=int)

    merge_history: List[List[int]] = []
    merge_distances: List[float] = []

    # 当前 active cluster 数 = n - iteration
    m = n
    for _ in range(n - 1):
        # 找最小距离
        flat_idx = np.argmin(D)
        i, j = divmod(flat_idx, m)

        # 确保 i < j，方便处理
        if i > j:
            i, j = j, i

        distance = D[i, j]
        merge_history.append([int(cluster_labels[i]), int(cluster_labels[j])])
        merge_distances.append(float(distance))

        # 合并 i 和 j：用 i 做合并后的 cluster
        new_size = cluster_sizes[i] + cluster_sizes[j]

        # average linkage 更新
        for k in range(m):
            if k != i and k != j:
                # 加权平均
                new_dist = (cluster_sizes[i] * D[i, k] + cluster_sizes[j] * D[j, k]) / new_size
                D[i, k] = new_dist
                D[k, i] = new_dist

        # 把行/列 j 替换为最后一行/列
        if j != m - 1:
            D[j, :] = D[m - 1, :]
            D[:, j] = D[:, m - 1]
            cluster_sizes[j] = cluster_sizes[m - 1]
            cluster_labels[j] = cluster_labels[m - 1]

        # 裁剪
        D = D[:-1, :-1]
        cluster_sizes = cluster_sizes[:-1]
        cluster_labels = cluster_labels[:-1]
        m -= 1

        # 更新合并后 cluster 的 size
        if i < m:
            cluster_sizes[i] = new_size
            if D.shape[0] > 0:
                np.fill_diagonal(D, np.inf)

    return np.array(merge_history), np.array(merge_distances)


# ============================================================
#  树状图切割
# ============================================================


def threshold_clusters(
    n: int,
    merge_history: np.ndarray,
    merge_distances: np.ndarray,
    threshold: float,
) -> List[List[int]]:
    """在给定阈值处切割树状图，产生 cluster 分配

    Args:
        n: 原始 episode 数
        merge_history: (n-1, 2)
        merge_distances: (n-1,)
        threshold: 切割阈值——合并距离 > threshold 的操作被截断

    Returns:
        每个 cluster 包含的元素索引列表
    """
    # 初始化：每个元素独立一个 cluster
    clusters = {i: [i] for i in range(n)}
    active = set(range(n))
    next_id = n

    for pair, dist in zip(merge_history, merge_distances):
        if dist > threshold:
            break  # 截断
        a, b = int(pair[0]), int(pair[1])
        # 找到 a 和 b 所在的当前 cluster ID
        a_cluster = None
        b_cluster = None
        for cid in list(active):
            if a in clusters[cid]:
                a_cluster = cid
            if b in clusters[cid]:
                b_cluster = cid
        if a_cluster is not None and b_cluster is not None and a_cluster != b_cluster:
            # 合并
            new_cluster = clusters[a_cluster] + clusters[b_cluster]
            clusters[next_id] = new_cluster
            active.remove(a_cluster)
            active.remove(b_cluster)
            active.add(next_id)
            next_id += 1

    return [clusters[cid] for cid in sorted(active)]


def cut_dendrogram(
    n: int,
    merge_history: np.ndarray,
    merge_distances: np.ndarray,
    n_levels: int = 4,
) -> Tuple[List[List[List[int]]], List[float]]:
    """在 N 个不同阈值处切割树状图，产生 N 层 cluster 分配

    Level 0: 最抽象（1 个 cluster — 所有 episode 归为一个超大类）
    Level 1: 粗粒度
    Level 2: 中粒度
    ...
    Level L-1: 最具体（接近叶节点）

    Args:
        n: 原始 episode 数
        merge_history: (n-1, 2)
        merge_distances: (n-1,)
        n_levels: 层级数

    Returns:
        all_assignments: 每层的 cluster 分配
        thresholds: 每层对应的切割阈值
    """
    if n == 0:
        return [], []
    if n == 1:
        # 只有一个 episode，所有层级都一样
        single = [[0]]
        return [single] * n_levels, [0.0] * n_levels

    sorted_distances = np.sort(merge_distances)

    if len(sorted_distances) <= n_levels:
        # 数据太少，均匀分割
        indices = np.linspace(0, len(sorted_distances) - 1, n_levels, dtype=int)
        thresholds = sorted_distances[indices].tolist()
    else:
        # 从高到低选取百分位
        percentiles = np.linspace(0.90, 0.10, n_levels - 1)
        indices = (percentiles * (len(sorted_distances) - 1)).astype(int)
        thresholds = sorted_distances[indices].tolist()
        # level 0：略高于最大合并距离 → 1 个 cluster
        thresholds.append(sorted_distances[-1] + 0.01)

    # 从粗到细分配阈值（从最大阈值到最小阈值）
    sorted_thresholds = sorted(thresholds, reverse=True)
    all_assignments = []
    for thr in sorted_thresholds:
        assignments = threshold_clusters(n, merge_history, merge_distances, thr)
        all_assignments.append(assignments)

    return all_assignments, sorted_thresholds


# ============================================================
#  中心点计算
# ============================================================


def compute_centroids(
    embeddings: np.ndarray,
    cluster_assignments: List[List[int]],
) -> List[np.ndarray]:
    """计算每个 cluster 的中心点向量

    Args:
        embeddings: (n, d) numpy array
        cluster_assignments: 每个 cluster 包含的元素索引列表

    Returns:
        每个 cluster 的 centroid vector
    """
    centroids = []
    for indices in cluster_assignments:
        cluster_vecs = embeddings[indices]
        centroid = np.mean(cluster_vecs, axis=0)
        # 归一化
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        centroids.append(centroid)
    return centroids


# ============================================================
#  Topic 树构建
# ============================================================


def build_topic_tree(
    level_assignments: List[List[List[int]]],
    centroids_by_level: List[List[np.ndarray]],
    embeddings: np.ndarray,
    episode_ids: List[str],
) -> Dict[str, Any]:
    """构建跨层的 topic parent/children 树

    通过追踪层级间 cluster 的包含关系构建树：
    - Level L 的 cluster ⊆ Level L-1 的某个 cluster
    - 父子关系 = 包含关系

    Args:
        level_assignments: 每层每 cluster 的 episode 索引
        centroids_by_level: 每层每 cluster 的中心点
        embeddings: (n, d)
        episode_ids: 原始 episode ID 列表（与 embeddings 下标对齐）

    Returns:
        {
            "topic_id": {
                "id": str,
                "episode_ids": [str, ...],
                "hierarchy_level": int,
                "children": [{...}, ...],  # 递归
                "centroid": [...],
            }
        }
    """
    if not level_assignments:
        return {}

    def make_topic_id(level: int, cluster_idx: int) -> str:
        return f"hier_topic_l{level}_c{cluster_idx}"

    def build_node(
        level: int,
        cluster_idx: int,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        assignments = level_assignments[level][cluster_idx]
        ep_ids = [episode_ids[i] for i in assignments]
        centroid = centroids_by_level[level][cluster_idx]

        node = {
            "id": make_topic_id(level, cluster_idx),
            "episode_ids": ep_ids,
            "hierarchy_level": level,
            "parent_id": parent_id,
            "centroid": centroid.tolist(),
            "children": [],
        }

        # 找下一层的子 cluster
        if level + 1 < len(level_assignments):
            # 下一层的哪个 cluster 是这个 cluster 的子集
            child_ep_ids = set(ep_ids)
            for child_idx, child_assign in enumerate(level_assignments[level + 1]):
                child_set = set(child_assign)
                if child_set.issubset(child_ep_ids):
                    child_node = build_node(level + 1, child_idx, node["id"])
                    node["children"].append(child_node)

        return node

    # 从 level 0 开始递归
    roots = []
    for i in range(len(level_assignments[0])):
        roots.append(build_node(0, i))

    # 展平为 dict
    result = {}
    def flatten(nodes):
        for n in nodes:
            result[n["id"]] = {k: v for k, v in n.items() if k != "children"}
            children_ids = []
            for c in n["children"]:
                children_ids.append(c["id"])
                flatten([c])
            result[n["id"]]["children_ids"] = children_ids
    flatten(roots)

    return result


# ============================================================
#  层次分配器
# ============================================================


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个向量的余弦相似度"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class HierarchyAssigner:
    """层次分配器

    支持两种模式：
    1. full_cluster() — 对所有 episode 全量聚类，构建完整 hierarchy
    2. incremental_assign() — 对新 episode 增量分配，不做全量重聚类
    """

    def __init__(
        self,
        assign_threshold: float = 0.7,
        weak_attach_threshold: float = 0.5,
        n_hierarchy_levels: int = 4,
    ):
        self._assign_threshold = assign_threshold
        self._weak_attach_threshold = weak_attach_threshold
        self._n_levels = n_hierarchy_levels

    def full_cluster(
        self,
        episode_ids: List[str],
        embeddings: np.ndarray,
        message_counts: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """全量聚类 — 构建完整 hierarchy

        Args:
            episode_ids: episode ID 列表
            embeddings: (n, d) embedding 向量
            message_counts: 每个 episode 的消息数（可选，用于长度加权）

        Returns:
            {
                "topic_tree": {...},  # build_topic_tree 的输出
                "levels": {...},       # 每层的 cluster 分配
                "merge_history": ...,
                "merge_distances": ...,
            }
        """
        n = len(episode_ids)
        if n == 0:
            return {"topic_tree": {}, "levels": {}, "n_episodes": 0}

        logger.info(
            "[HierarchyAssigner] Starting full cluster: %d episodes, %d levels",
            n, self._n_levels,
        )

        # 1. 距离矩阵
        if message_counts and len(message_counts) == n:
            dist = weighted_distance_matrix(embeddings, message_counts)
            logger.info("[HierarchyAssigner] Using length-weighted distance")
        else:
            dist = cosine_distance_matrix(embeddings)

        # 2. HAC
        merge_hist, merge_dists = hac_cluster(dist)
        logger.info(
            "[HierarchyAssigner] HAC complete: %d merges, distance range [%.4f, %.4f]",
            len(merge_dists),
            merge_dists[0] if len(merge_dists) > 0 else 0,
            merge_dists[-1] if len(merge_dists) > 0 else 0,
        )

        # 3. 树状图切割
        level_assignments, thresholds = cut_dendrogram(
            n, merge_hist, merge_dists, self._n_levels,
        )
        logger.info(
            "[HierarchyAssigner] Dendrogram cut at %d levels, thresholds=%s",
            len(level_assignments),
            [f"{t:.4f}" for t in thresholds],
        )

        # 4. 计算中心点
        centroids_by_level = []
        for level_assign in level_assignments:
            centroids = compute_centroids(embeddings, level_assign)
            centroids_by_level.append(centroids)

        # 5. 构建 topic 树
        topic_tree = build_topic_tree(
            level_assignments, centroids_by_level, embeddings, episode_ids,
        )

        # 6. 按层组织 cluster 信息
        levels = {}
        for level_idx, (assignments, centroids) in enumerate(
            zip(level_assignments, centroids_by_level)
        ):
            clusters = []
            for cluster_idx, (indices, centroid) in enumerate(
                zip(assignments, centroids)
            ):
                ep_ids = [episode_ids[i] for i in indices]
                clusters.append({
                    "cluster_id": cluster_idx,
                    "episode_ids": ep_ids,
                    "n_episodes": len(ep_ids),
                    "centroid": centroid.tolist(),
                })
            levels[level_idx] = clusters

        return {
            "topic_tree": topic_tree,
            "levels": levels,
            "merge_history": merge_hist.tolist() if len(merge_hist) > 0 else [],
            "merge_distances": merge_dists.tolist() if len(merge_dists) > 0 else [],
            "level_thresholds": thresholds,
            "n_episodes": n,
        }

    def incremental_assign(
        self,
        episode_id: str,
        episode_embedding: np.ndarray,
        message_count: int,
        topic_tree: Dict[str, Any],
    ) -> List[str]:
        """增量分配 — 将新 episode 分配到已有 hierarchy

        自上而下遍历 topic 树，在每一层找最匹配的 topic：
        - 相似度 ≥ assign_threshold → 分配到该 topic，继续深入
        - 相似度 < assign_threshold 但 ≥ weak_attach_threshold → 创建子 topic
        - 相似度 < weak_attach_threshold → 分配到根级，不深入

        Args:
            episode_id: 新 episode 的 ID
            episode_embedding: 新 episode 的 embedding 向量
            message_count: 新 episode 的消息数
            topic_tree: full_cluster 输出的 topic_tree

        Returns:
            该 episode 所属的全部 topic ID 列表（根→叶路径）
        """
        if not topic_tree:
            return []

        assigned: List[str] = []

        # 找根节点（parent_id 为 None 或不在树中）
        roots = [
            tid for tid, info in topic_tree.items()
            if info.get("parent_id") is None
        ]
        if not roots:
            return []

        # 从根开始递归分配
        def assign_recursive(topic_id: str, depth: int) -> None:
            info = topic_tree[topic_id]
            centroid = info.get("centroid")
            if centroid is None:
                return

            score = cosine_similarity(
                episode_embedding,
                np.array(centroid),
            )

            if score >= self._assign_threshold:
                assigned.append(topic_id)
                # 继续找子 topic
                children = [
                    cid for cid, cinfo in topic_tree.items()
                    if cinfo.get("parent_id") == topic_id
                ]
                if children:
                    # 找最匹配的子 topic
                    best_child = None
                    best_score = -1.0
                    for cid in children:
                        c_info = topic_tree[cid]
                        c_centroid = c_info.get("centroid")
                        if c_centroid is not None:
                            c_score = cosine_similarity(
                                episode_embedding,
                                np.array(c_centroid),
                            )
                            if c_score > best_score:
                                best_score = c_score
                                best_child = cid
                    if best_child is not None and best_score >= self._assign_threshold:
                        assign_recursive(best_child, depth + 1)
            elif score >= self._weak_attach_threshold and depth < 3:
                # 弱匹配 → 在该 topic 下创建新的子 topic
                assigned.append(topic_id)

        for root_id in roots:
            assign_recursive(root_id, 0)

        return assigned


# ============================================================
#  TopicClusterer — 完整编排
# ============================================================


class TopicClusterer:
    """Topic 聚类编排器

    整合 embedding 计算 + HAC 聚类 + hierarchy 构建 + LLM 标签生成
    """

    def __init__(
        self,
        embedding_provider: Any = None,
        llm_provider: Any = None,
        n_hierarchy_levels: int = 4,
        assign_threshold: float = 0.7,
    ):
        self._embedder = embedding_provider
        self._llm = llm_provider
        self._assigner = HierarchyAssigner(
            n_hierarchy_levels=n_hierarchy_levels,
            assign_threshold=assign_threshold,
        )

    def cluster_episodes(
        self,
        episodes: List[Dict[str, Any]],
        existing_topic_tree: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """对 episode 列表执行层次聚类

        每个 episode dict 应包含：
            id: str, summary: str, full_text: str (二选一),
            message_count: int (可选)

        Args:
            episodes: episode dict 列表
            existing_topic_tree: 已有 topic 树（增量模式）

        Returns:
            result dict 包含 topic_tree, levels, 或增量分配结果
        """
        if not episodes:
            return {"topic_tree": {}, "levels": {}, "n_episodes": 0}

        # 收集文本
        texts = []
        ep_ids = []
        msg_counts = []
        for ep in episodes:
            text = ep.get("summary", "") or ep.get("full_text", "")
            if not text:
                continue
            texts.append(text)
            ep_ids.append(ep.get("id", ""))
            msg_counts.append(ep.get("message_count", 1))

        if not texts:
            return {"topic_tree": {}, "levels": {}, "n_episodes": 0}

        # 计算 embedding
        if self._embedder is not None:
            embeddings = np.array(self._embedder.embed(texts))
        else:
            logger.warning("[TopicClusterer] No embedder — using random vectors for mock")
            embeddings = np.random.rand(len(texts), 128).astype(float)

        # 增量或全量模式
        if existing_topic_tree:
            assigned_ids = []
            for i, ep_id in enumerate(ep_ids):
                path = self._assigner.incremental_assign(
                    ep_id, embeddings[i], msg_counts[i], existing_topic_tree,
                )
                assigned_ids.append(path)
            return {
                "mode": "incremental",
                "assignments": assigned_ids,
                "n_episodes": len(ep_ids),
            }
        else:
            return self._assigner.full_cluster(
                ep_ids, embeddings, msg_counts,
            )

    def label_cluster_with_llm(
        self,
        episode_summaries: List[str],
        cluster_info: Dict[str, Any],
    ) -> Dict[str, str]:
        """用 LLM 为 cluster 生成 title 和 summary

        复用 _enrich_topic_with_llm 模式。
        """
        if not self._llm or not episode_summaries:
            return {"title": "", "summary": ""}

        text = "\n".join(
            f"- {s[:100]}" for s in episode_summaries[:10]
        )
        prompt = (
            f"以下是一组对话片段的摘要，请总结它们共同讨论的主题：\n\n"
            f"{text}\n\n"
            f"返回 JSON：{{\"title\": \"简洁主题标题（10字内）\", "
            f"\"summary\": \"一句话总结\", "
            f"\"keywords\": [\"关键词1\", \"关键词2\"]}}"
        )

        try:
            if hasattr(self._llm, "generate"):
                resp = self._llm.generate(prompt, response_format={"type": "json_object"})
            elif hasattr(self._llm, "chat"):
                resp = self._llm.chat(prompt)

            import json
            raw = resp.strip()
            if isinstance(raw, str):
                result = json.loads(raw)
            else:
                result = raw
            return {
                "title": result.get("title", ""),
                "summary": result.get("summary", ""),
                "keywords": json.dumps(result.get("keywords", []), ensure_ascii=False),
            }
        except Exception as e:
            logger.warning("[TopicClusterer] LLM labeling failed: %s", str(e)[:60])
            return {"title": "", "summary": ""}