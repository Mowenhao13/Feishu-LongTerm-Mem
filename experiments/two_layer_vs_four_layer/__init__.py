"""两层 vs 四层超图 — 对照实验

对比实验框架，在 argusbot_v3 数据集上验证简化后两层超图结构相对当前四层超图的性能差异。

实验组:
    A 组: 当前四层超图 (baseline)
    B 组: 简化两层结构 (Raw Data + Knowledge Entities)
    C 组: 两层 + SQLite 持久化

用法:
    python experiments/two_layer_vs_four_layer/run_experiments.py --all
"""

from __future__ import annotations