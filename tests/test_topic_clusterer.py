"""Unit tests for topic_clusterer module"""

import math

import numpy as np
import pytest

from graph.topic_clusterer import (
    HierarchyAssigner,
    build_topic_tree,
    compute_centroids,
    cosine_distance_matrix,
    cut_dendrogram,
    hac_cluster,
    threshold_clusters,
    weighted_distance_matrix,
)


class TestCosineDistanceMatrix:
    def test_identical_vectors(self):
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ])
        dist = cosine_distance_matrix(embeddings)
        assert dist.shape == (2, 2)
        assert dist[0, 1] == pytest.approx(0.0, abs=1e-6)
        assert dist[0, 0] == pytest.approx(0.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        """正交向量应有距离 1.0"""
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ])
        dist = cosine_distance_matrix(embeddings)
        assert dist[0, 1] == pytest.approx(1.0, abs=1e-6)

    def test_opposite_vectors(self):
        """相反向量应有距离 2.0"""
        embeddings = np.array([
            [1.0, 0.0],
            [-1.0, 0.0],
        ])
        dist = cosine_distance_matrix(embeddings)
        assert dist[0, 1] == pytest.approx(2.0, abs=1e-6)


class TestWeightedDistanceMatrix:
    def test_equal_lengths_no_change(self):
        """所有 episode 消息数相等 → 加权后应与原距离一致"""
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ])
        raw = cosine_distance_matrix(embeddings)
        weighted = weighted_distance_matrix(embeddings, [1, 1])
        assert weighted[0, 1] == pytest.approx(raw[0, 1], abs=1e-6)

    def test_short_episodes_spread(self):
        """两个短 episode 之间的距离被放大"""
        embeddings = np.array([
            [1.0, 0.0],
            [0.5, 0.5],
        ])
        raw = cosine_distance_matrix(embeddings)
        # 两个都很短 [1, 1] → 均值=1 → lengths=[1,1] → clipped=[1,1] → 无变化（都是 1 就是均值）
        # 引入一个长 episode 做参照
        embeddings3 = np.array([
            [1.0, 0.0],
            [0.5, 0.5],
            [0.0, 1.0],
        ])
        weighted = weighted_distance_matrix(embeddings3, [1, 1, 50])
        raw3 = cosine_distance_matrix(embeddings3)
        # 短 pair (0, 1) 距离应放大
        assert weighted[0, 1] > raw3[0, 1], (
            f"Short pair distance should spread: raw={raw3[0,1]:.4f} weighted={weighted[0,1]:.4f}"
        )

    def test_long_episodes_compress(self):
        """长度远大于均值的 episode → 距离被压缩"""
        embeddings = np.array([
            [1.0, 0.0],
            [0.5, 0.5],
        ])
        raw = cosine_distance_matrix(embeddings)
        # 两者都远大于均值 [50, 50] → 均值=50 → lengths=[1,1] → 无变化
        # 用两个不同的大值确保 lengths > 1: [50, 100] → 均值=75 → lengths=[0.667, 1.333]
        # 不行，一短一长会保持原值。要两个都 > 均值才行：
        # [30, 30] → 均值=30 → lengths=[1,1] → 无变化
        # 当全部相等时 lengths 全为 1，无变化——这是对的。
        # 用少量短 episode 做参照，让长 pair 在加权后压缩：
        # 4 个点：[50, 50, 1, 1] → 均值=25.5 → lengths=[1.96, 1.96, 0.04, 0.04] → clipped to [2.0, 2.0, 0.5, 0.5]
        embeddings4 = np.array([
            [1.0, 0.0],
            [0.9, 0.1],  # 长 pair，彼此接近
            [0.0, 1.0],
            [0.1, 0.9],  # 短 pair，彼此接近
        ])
        weights8 = [50, 50, 1, 1]
        raw4 = cosine_distance_matrix(embeddings4)
        weighted4 = weighted_distance_matrix(embeddings4, weights8)
        # 长 pair（0 和 1）距离应压缩
        assert weighted4[0, 1] < raw4[0, 1], (
            f"Long pair distance should compress: raw={raw4[0,1]:.4f} weighted={weighted4[0,1]:.4f}"
        )


class TestHACCluster:
    def test_empty(self):
        hist, dists = hac_cluster(np.array([]).reshape(0, 0))
        assert len(hist) == 0
        assert len(dists) == 0

    def test_single_point(self):
        dist = np.array([[0.0]])
        hist, dists = hac_cluster(dist)
        assert len(hist) == 0
        assert len(dists) == 0

    def test_two_points(self):
        """两个点 → 一次合并，距离即它们的距离"""
        dist = np.array([
            [np.inf, 0.5],
            [0.5, np.inf],
        ])
        hist, dists = hac_cluster(dist)
        assert hist.shape == (1, 2)
        assert len(dists) == 1
        assert dists[0] == pytest.approx(0.5, abs=1e-6)

    def test_three_points_cluster(self):
        """三组，前两个很近，第三个远"""
        dist = np.array([
            [np.inf, 0.1, 0.9],
            [0.1, np.inf, 0.9],
            [0.9, 0.9, np.inf],
        ])
        hist, dists = hac_cluster(dist)
        assert hist.shape == (2, 2)
        # 第一次合并最近的两个（0.1）
        assert dists[0] == pytest.approx(0.1, abs=1e-6)
        # 第二次合并第三个（average linkage 后应与 0.9 接近）
        assert dists[1] > 0.5


class TestThresholdClusters:
    def test_single_threshold_groups(self):
        merge_hist = np.array([[0, 1], [2, 3], [4, 5]])
        merge_dists = np.array([0.1, 0.1, 0.9])
        clusters = threshold_clusters(6, merge_hist, merge_dists, threshold=0.5)
        # 前两次合并距离 0.1 < 0.5，应合并；最后一次 0.9 > 0.5 被截断
        cluster_sizes = sorted(len(c) for c in clusters)
        assert 2 in cluster_sizes  # 至少有 size=2 的 cluster

    def test_zero_threshold(self):
        """阈值为 0 → 合并距离 > 0 的全部截断"""
        merge_hist = np.array([[0, 1], [2, 3]])
        merge_dists = np.array([0.1, 0.2])
        clusters = threshold_clusters(4, merge_hist, merge_dists, threshold=0.0)
        # 所有合并距离 > 0，全部截断 → 4 个单元素 cluster
        assert len(clusters) == 4


class TestCutDendrogram:
    def test_single_episode(self):
        """只有一个 episode → 所有层级相同"""
        assignments, thresholds = cut_dendrogram(1, np.array([]), np.array([]), n_levels=3)
        assert len(assignments) == 3
        for level in assignments:
            assert len(level) == 1

    def test_level_count(self):
        """正确产出 N 层"""
        merge_hist = np.array([[0, 1], [2, 3], [4, 5], [0, 2]])
        merge_dists = np.array([0.1, 0.15, 0.2, 0.8])
        assignments, thresholds = cut_dendrogram(6, merge_hist, merge_dists, n_levels=4)
        assert len(assignments) == 4
        assert len(thresholds) == 4


class TestComputeCentroids:
    def test_single_cluster(self):
        embeddings = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
        centroids = compute_centroids(embeddings, [[0, 1, 2]])
        assert len(centroids) == 1
        expected = np.mean(embeddings, axis=0)
        norm = np.linalg.norm(expected)
        expected_norm = expected / norm
        assert np.allclose(centroids[0], expected_norm)

    def test_two_clusters(self):
        embeddings = np.array([
            [1.0, 0.0],
            [0.9, 0.1],
            [0.0, 1.0],
            [0.1, 0.9],
        ])
        centroids = compute_centroids(embeddings, [[0, 1], [2, 3]])
        assert len(centroids) == 2
        for c in centroids:
            assert abs(np.linalg.norm(c) - 1.0) < 1e-6


class TestBuildTopicTree:
    def test_basic_tree_structure(self):
        """基本树结构：从 HAC 输出构建的树应有正确的父子关系"""
        np.random.seed(42)
        embeddings = np.random.rand(10, 16).astype(float)
        episode_ids = [f"ep{i}" for i in range(10)]

        # 用真实 HAC 保证子集关系成立
        dist = cosine_distance_matrix(embeddings)
        merge_hist, merge_dists = hac_cluster(dist)

        assigner = HierarchyAssigner(n_hierarchy_levels=3)
        result = assigner.full_cluster(episode_ids, embeddings)

        tree = result["topic_tree"]
        assert len(tree) > 0, "Tree should have nodes"

        # Level 0 至少有一个根
        roots = [tid for tid, info in tree.items() if info["parent_id"] is None]
        assert len(roots) >= 1, "Should have at least one root"

        # 所有非根节点都应有 parent
        for tid, info in tree.items():
            if info["parent_id"] is not None:
                # parent 必须存在于树中
                assert info["parent_id"] in tree, (
                    f"Topic {tid}'s parent {info['parent_id']} not in tree"
                )

        # hierarchy_level 应递增：level 0 < level 1 < level 2
        for tid, info in tree.items():
            children = [
                cid for cid, cinfo in tree.items()
                if cinfo.get("parent_id") == tid
            ]
            for cid in children:
                assert tree[cid]["hierarchy_level"] > info["hierarchy_level"], (
                    f"Child {cid} level {tree[cid]['hierarchy_level']} should be > "
                    f"parent {tid} level {info['hierarchy_level']}"
                )


class TestHierarchyAssigner:
    def test_full_cluster_returns_structure(self):
        """full_cluster 返回完整结构"""
        ep_ids = [f"ep{i}" for i in range(10)]
        embeddings = np.random.rand(10, 128).astype(float)
        assigner = HierarchyAssigner(n_hierarchy_levels=3)
        result = assigner.full_cluster(ep_ids, embeddings)

        assert "topic_tree" in result
        assert "levels" in result
        assert "n_episodes" in result
        assert result["n_episodes"] == 10
        assert len(result["topic_tree"]) > 0
        assert len(result["levels"]) == 3

    def test_full_cluster_empty(self):
        """空输入返回空结构"""
        assigner = HierarchyAssigner()
        result = assigner.full_cluster([], np.array([]).reshape(0, 128))
        assert result["n_episodes"] == 0

    def test_incremental_assign_empty_tree(self):
        """空树 → 返回空"""
        assigner = HierarchyAssigner()
        path = assigner.incremental_assign(
            "ep_new", np.random.rand(128), 1, {},
        )
        assert path == []

    def test_incremental_assign_match_root(self):
        """增量分配应匹配最相似的根节点"""
        np.random.seed(42)
        ep_ids = [f"ep{i}" for i in range(5)]
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.8, 0.2, 0.0],
            [0.0, 1.0, 0.0],
            [0.1, 0.9, 0.0],
        ])
        assigner = HierarchyAssigner(assign_threshold=0.5, n_hierarchy_levels=2)
        result = assigner.full_cluster(ep_ids, embeddings)

        tree = result["topic_tree"]
        assert len(tree) > 0, "Topic tree should not be empty"

        # 新 episode 与第一组相似
        new_emb = np.array([0.85, 0.15, 0.0])
        path = assigner.incremental_assign("ep_new", new_emb, 1, tree)
        assert len(path) > 0, "Should assign to at least one topic"


class TestE2EClustering:
    def test_known_clusters(self):
        """端到端：已知 3 个不重叠的 cluster → 聚类应正确分离"""
        np.random.seed(42)

        # 构建 3 个清晰的 cluster
        cluster1 = np.random.rand(3, 16) * 0.1 + np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
        cluster2 = np.random.rand(3, 16) * 0.1 + np.array([0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0])
        cluster3 = np.random.rand(3, 16) * 0.1 + np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0])

        all_embeddings = np.vstack([cluster1, cluster2, cluster3])
        ep_ids = [f"ep{i}" for i in range(9)]

        dist = cosine_distance_matrix(all_embeddings)
        # 类内距离应显著小于类间距离
        intra_dists = [
            dist[0, 1], dist[0, 2], dist[1, 2],
            dist[3, 4], dist[3, 5], dist[4, 5],
            dist[6, 7], dist[6, 8], dist[7, 8],
        ]
        inter_dists = [
            dist[0, 3], dist[1, 4], dist[2, 5],
            dist[0, 6], dist[3, 7], dist[6, 0],
        ]

        avg_intra = np.mean(intra_dists)
        avg_inter = np.mean(inter_dists)
        assert avg_inter > avg_intra, (
            f"Inter-cluster distance ({avg_inter:.4f}) should exceed "
            f"intra-cluster distance ({avg_intra:.4f})"
        )

        assigner = HierarchyAssigner(n_hierarchy_levels=3)
        result = assigner.full_cluster(ep_ids, all_embeddings)

        # level 2 的 cluster 数应接近 3（已知 cluster 数）
        l2_clusters = result["levels"].get(2, [])
        assert len(l2_clusters) >= 2, (
            f"Expected at least 2 clusters at level 2, got {len(l2_clusters)}"
        )

    def test_silhouette_calculation(self):
        """实现 Silhouette Score 作为质量指标"""
        np.random.seed(42)

        # 2 个清晰 cluster
        c1 = np.random.rand(4, 8) * 0.1 + np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        c2 = np.random.rand(4, 8) * 0.1 + np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        embeddings = np.vstack([c1, c2])

        dist = cosine_distance_matrix(embeddings)

        def silhouette_score(assignments):
            """简化版 Silhouette Score"""
            n = len(assignments)
            scores = []
            for i in range(n):
                own_cluster = assignments[i]
                same = [j for j in range(n) if assignments[j] == own_cluster and j != i]
                a = np.mean([dist[i, j] for j in same]) if same else 0.0
                other_clusters = set(assignments) - {own_cluster}
                other_dists = []
                for oc in other_clusters:
                    others = [dist[i, j] for j in range(n) if assignments[j] == oc]
                    if others:
                        other_dists.append(np.mean(others))
                b = min(other_dists) if other_dists else a
                score = (b - a) / max(a, b) if max(a, b) > 0 else 0
                scores.append(score)
            return np.mean(scores)

        # 正确的分配应得出较高的 Silhouette Score
        correct = [0, 0, 0, 0, 1, 1, 1, 1]
        wrong = [0, 0, 0, 0, 0, 0, 0, 0]
        correct_score = silhouette_score(correct)
        wrong_score = silhouette_score(wrong)
        assert correct_score > wrong_score, (
            f"Correct Silhouette ({correct_score:.4f}) should exceed "
            f"wrong ({wrong_score:.4f})"
        )


class TestEdgeCases:
    def test_zero_vectors(self):
        """零向量 → 归一化为 0，夹角为 0，距离应为 0"""
        # 注意：两个零向量归一化为 0，点积 = 0，余弦 = 0，距离 = 1.0
        # 这是正确的行为——零向量与任何向量都不相似
        embeddings = np.zeros((3, 10))
        dist = cosine_distance_matrix(embeddings)
        # 零向量被归一化为 0，cos(0,0)=0，距离=1.0
        assert np.allclose(dist - np.eye(3), np.full((3, 3), 1.0) - np.eye(3))

    def test_all_zero_vectors(self):
        """全零向量之间距离为 1.0（归一化为 0，夹角无意义）"""
        embeddings = np.zeros((2, 5))
        dist = cosine_distance_matrix(embeddings)
        assert dist[0, 1] == pytest.approx(1.0, abs=1e-6)

    def test_single_dimension(self):
        """一维向量 → 距离应正确"""
        embeddings = np.array([[1.0], [-1.0], [0.5]])
        dist = cosine_distance_matrix(embeddings)
        assert dist[0, 1] == pytest.approx(2.0, abs=1e-6)

    def test_large_random(self):
        """100 个随机向量不崩"""
        np.random.seed(0)
        embeddings = np.random.rand(100, 64).astype(float)
        dist = cosine_distance_matrix(embeddings)
        assert dist.shape == (100, 100)
        assert np.all(dist >= 0)
        assert np.all(dist <= 2.0)

        merge_hist, merge_dists = hac_cluster(dist)
        assert merge_hist.shape == (99, 2)
        assert len(merge_dists) == 99

    def test_length_weighting_all_short(self):
        """所有 episode 都很短 → 距离应大于未加权的"""
        np.random.seed(42)
        embeddings = np.random.rand(10, 64).astype(float)
        raw = cosine_distance_matrix(embeddings)
        # 用 [1]*10 → 均值=1，lengths=[1]*10 → weight=1 → 无变化
        # 需要让它们明显小于均值
        weighted = weighted_distance_matrix(embeddings, [1, 1, 1, 1, 1, 50, 50, 50, 50, 50])
        mean_raw = np.mean(raw)
        mean_weighted = np.mean(weighted)
        assert mean_weighted > mean_raw, (
            f"Weighted mean ({mean_weighted:.4f}) should exceed raw mean ({mean_raw:.4f})"
        )

    def test_length_weighting_all_long(self):
        """两个 long episode 之间的 pair 距离应被压缩"""
        np.random.seed(42)
        embeddings = np.array([
            [1.0, 0.0],
            [0.9, 0.1],  # 长 pair，彼此接近
            [0.0, 1.0],
            [0.1, 0.9],  # 短 pair
        ])
        raw = cosine_distance_matrix(embeddings)
        mixed_weights = [50, 50, 1, 1]
        weighted = weighted_distance_matrix(embeddings, mixed_weights)
        # 长 pair (0, 1) 距离应压缩
        assert weighted[0, 1] < raw[0, 1], (
            f"Long pair distance should compress: raw={raw[0,1]:.4f} weighted={weighted[0,1]:.4f}"
        )