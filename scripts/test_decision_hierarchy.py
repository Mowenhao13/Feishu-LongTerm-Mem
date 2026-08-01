"""决策层级关系测试 —— 使用层级化测试数据验证决策树功能

流程:
  1. 在 MemoryGraph 中预创建根/父决策
  2. 运行 EvalRunner 处理层级化测试消息
  3. 基于主题匹配自动建立 PARENT_OF 关系
  4. 输出决策树测试报告（含 get_children / get_descendants / decision_tree）
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

os.environ["BITABLE_ENABLED"] = "false"

from src.node.node import DecisionNode, DecisionStatus, ImpactLevel, Relation, RelationType
from src.graph.memory_graph import MemoryGraph


SEP = "=" * 70


def make_sid(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _build_seed_decisions() -> List[DecisionNode]:
    """创建预定义的层级化决策树"""
    now = datetime.now()

    root_decisions = [
        DecisionNode(
            sid=make_sid("微服务架构"),
            parent_id="",
            topic_id="技术选型",
            title="微服务架构选型",
            summary="确定微服务架构整体方案为gRPC+Kong+Consul组合",
            full_text="经过讨论，微服务架构确定为gRPC（通信协议）+ Kong（API网关）+ Consul（服务发现）的组合方案",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("前端技术栈"),
            parent_id="",
            topic_id="技术选型",
            title="前端技术栈选型",
            summary="前端确定使用React+Next.js+Zustand+Ant Design",
            full_text="前端技术栈选型完成：React框架、Next.js服务端渲染、Zustand状态管理、Ant Design组件库",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("容器化方案"),
            parent_id="",
            topic_id="容器编排",
            title="容器化方案选型",
            summary="容器编排确定使用K8s+Prometheus+Calico",
            full_text="容器化整体方案：K8s编排、Prometheus+Grafana监控、Calico网络、Harbor镜像仓库",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("数据库选型定稿"),
            parent_id="",
            topic_id="技术选型",
            title="数据库选型",
            summary="数据库确定使用PostgreSQL RDS + PgBouncer",
            full_text="数据库选型定稿：PostgreSQL、阿里云RDS托管、PgBouncer连接池、WAL归档备份",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
    ]

    child_decisions = [
        DecisionNode(
            sid=make_sid("gRPC通信协议"),
            parent_id=make_sid("微服务架构"),
            topic_id="技术选型",
            title="gRPC通信协议定稿",
            summary="微服务间通信统一使用gRPC，Proto统一管理",
            full_text="gRPC通信协议定稿：HTTP/2、Protocol Buffers序列化、Proto文件统一管理、双向TLS认证",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("KongAPI网关"),
            parent_id=make_sid("微服务架构"),
            topic_id="技术选型",
            title="API网关选型Kong",
            summary="API网关确定使用Kong，插件机制灵活",
            full_text="Kong网关定稿：插件生态丰富（认证限流日志）、OAuth2+JWT认证、自动路由分发、syslog对接ELK",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("Consul服务发现"),
            parent_id=make_sid("微服务架构"),
            topic_id="技术选型",
            title="服务注册发现用Consul",
            summary="服务注册和发现统一使用Consul",
            full_text="Consul定稿：健康检查TCP+HTTP双模式、KV配置分层、ACL权限控制、多数据中心",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("gRPC负载均衡"),
            parent_id=make_sid("gRPC通信协议"),
            topic_id="技术选型",
            title="gRPC负载均衡策略",
            summary="gRPC客户端侧加权轮询+重试机制",
            full_text="gRPC通信负载均衡：客户端侧加权轮询策略、3次重试+指数退避、OpenTelemetry+Jaeger链路追踪",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MINOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("Kong网关限流"),
            parent_id=make_sid("KongAPI网关"),
            topic_id="技术选型",
            title="Kong网关限流策略",
            summary="Kong网关限流按API Key分级",
            full_text="Kong网关限流：Rate Limiting插件、按API Key分级限制流量",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MINOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("容器监控"),
            parent_id=make_sid("容器化方案"),
            topic_id="容器编排",
            title="容器监控方案",
            summary="容器监控使用Prometheus+Grafana+ELK",
            full_text="容器监控方案：Prometheus指标采集、Grafana可视化看板、Fluentd日志收集到ELK",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
        DecisionNode(
            sid=make_sid("容器网络插件"),
            parent_id=make_sid("容器化方案"),
            topic_id="容器编排",
            title="容器网络插件Calico",
            summary="容器网络使用Calico，支持NetworkPolicy",
            full_text="容器网络插件Calico定稿：网络策略支持、性能优于Flannel",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
            created_at=now,
            updated_at=now,
        ),
    ]

    return root_decisions + child_decisions


def _build_relations(decisions: List[DecisionNode]) -> None:
    for d in decisions:
        if d.parent_id:
            d.relations.append(Relation(
                type=RelationType.PARENT_OF,
                target_id=d.parent_id,
                description="子决策",
            ))


def _print_separator(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def _tree_string(decisions: List[DecisionNode], graph: MemoryGraph,
                  sid: str, indent: int = 0) -> str:
    node = graph.get_decision(sid)
    if not node:
        return ""
    prefix = "  " * indent + ("└─ " if indent > 0 else "")
    result = f"{prefix}{node.sid[:12]}  {node.summary[:50]}"
    if indent == 0:
        result += "  ← 根决策"
    result += "\n"
    children = graph.get_children_of(sid)
    for child in children:
        result += _tree_string(decisions, graph, child.sid, indent + 1)
    return result


def print_tree_report(graph: MemoryGraph) -> None:
    _print_separator("决策树结构报告")

    all_nodes = graph.get_all_decisions()
    roots = [d for d in all_nodes if not d.parent_id]

    print(f"  总决策数: {len(all_nodes)}")
    print(f"  根决策:   {len(roots)}")
    print(f"  子决策:   {len(all_nodes) - len(roots)}")

    for root in roots:
        children = graph.get_children_of(root.sid)
        if not children:
            continue
        print(f"\n  根: {root.sid[:12]}  {root.summary[:50]}")
        descendants = graph.get_descendants(root.sid)
        print(f"      后代总数: {len(descendants)}")
        print(_tree_string(all_nodes, graph, root.sid), end="")


def print_mcp_tree_demo(graph: MemoryGraph) -> None:
    """模拟 MCP decision_tree / decision_children 工具输出"""
    _print_separator("MCP 工具模拟输出")

    all_nodes = graph.get_all_decisions()
    roots = [d for d in all_nodes if not d.parent_id]

    for root in roots[:3]:
        children = graph.get_children_of(root.sid)
        if not children:
            continue

        # decision_children
        print(f"\n  ▶ decision_children('{root.sid[:12]}...')")
        print(f"    → {len(children)} 个子决策:")
        for c in children:
            print(f"      ├─ {c.sid[:12]}  {c.summary[:40]}")

        # decision_descendants
        descendants = graph.get_descendants(root.sid)
        print(f"  ▶ decision_descendants('{root.sid[:12]}...')")
        print(f"    → {len(descendants)} 个后代")

        # decision_ancestors (for leaf nodes)
        leaf = children[-1]
        ancestors = graph.get_ancestors(leaf.sid)
        print(f"  ▶ decision_ancestors('{leaf.sid[:12]}...')")
        print(f"    → 祖先路径: ", end="")
        print(" → ".join([f"{a.sid[:8]}({a.summary[:15]})" for a in ancestors]))

        # decision_tree
        print(f"  ▶ decision_tree('{root.sid[:12]}...')")
        tree = _build_tree_json(graph, root.sid)
        print(f"    → 树深度: {_tree_depth(tree)} 层")


def _build_tree_json(graph: MemoryGraph, sid: str) -> Dict:
    node = graph.get_decision(sid)
    if not node:
        return {}
    children = graph.get_children_of(sid)
    return {
        "sid": node.sid[:12],
        "summary": node.summary[:40],
        "children": [_build_tree_json(graph, c.sid) for c in children],
    }


def _tree_depth(tree: Dict) -> int:
    if not tree.get("children"):
        return 1
    return 1 + max(_tree_depth(c) for c in tree["children"])


def print_hierarchy_analysis(graph: MemoryGraph) -> None:
    """输出层级关系详细分析"""
    _print_separator("层级关系详细分析")

    all_nodes = graph.get_all_decisions()
    with_parent = [d for d in all_nodes if d.parent_id]

    print(f"  建立了层级关系的决策: {len(with_parent)}")
    print()

    for d in with_parent:
        parent = graph.get_decision(d.parent_id)
        p_sum = parent.summary[:30] if parent else "?"
        print(f"  {d.sid[:12]}  {d.summary[:45]}")
        print(f"    └─ parent → {d.parent_id[:12]}  ({p_sum})")
        print(f"    └─ topic → {d.topic_id}")

    total_relations = sum(len(d.relations) for d in all_nodes)
    print(f"\n  总关系数: {total_relations}")
    print()


async def main():
    print(f"\n  {'='*60}")
    print(f"  决策层级关系测试")
    print(f"  {'='*60}\n")

    print(f"  测试数据: eval_data/hierarchy_test.txt")
    print(f"  种子决策: 11 条预置决策（4 根 + 7 子）")
    print()

    graph = MemoryGraph()
    seed_nodes = _build_seed_decisions()
    for d in seed_nodes:
        graph.upsert_decision(d, "default")
        print(f"  + 载入种子决策: {d.sid[:12]}  {d.summary[:40]}")

    print(f"\n  {'='*60}")
    print(f"  种子决策树构建完成: {len(seed_nodes)} 条")
    print(f"  {'='*60}\n")

    print_tree_report(graph)
    print_hierarchy_analysis(graph)

    print(f"\n  ▶ 运行 EvalRunner 处理层级化测试数据...\n")
    from src.eval_runner import EvalRunner
    runner = EvalRunner(
        input_path=os.path.join(_PROJECT_ROOT, "eval_data", "hierarchy_test.txt"),
        delay=0.5,
        max_messages=0,
        group_num=3,
    )
    runner_duration = time.time()
    await runner.run()
    runner_duration = time.time() - runner_duration
    print(f"\n  Eval runner 耗时: {runner_duration:.1f}s\n")

    print(f"\n  ▶ 提取决策树...\n")

    all_after = graph.get_all_decisions()
    print(f"  种子决策:     {len(seed_nodes)}")
    print(f"  Eval 后决策:  {len(all_after)}")
    new_count = len(all_after) - len(seed_nodes)
    print(f"  新增决策:     {new_count}")
    print()

    seed_sids = set(d.sid for d in seed_nodes)
    new_nodes = [d for d in all_after if d.sid not in seed_sids]
    for d in new_nodes:
        parent_info = ""
        if d.parent_id:
            p = graph.get_decision(d.parent_id)
            p_sum = p.summary[:20] if p else d.parent_id[:12]
            parent_info = f"  ← parent={p_sum}"
        print(f"  + {d.sid[:12]}  {d.summary[:45]}{parent_info}")

    print()
    print_tree_report(graph)
    print_mcp_tree_demo(graph)

    _print_separator("测试完成")
    print(f"  种子决策: {len(seed_nodes)} 条")
    print(f"  新增决策: {new_count} 条")
    print(f"  总决策:   {len(all_after)} 条")
    roots = [d for d in all_after if not d.parent_id]
    print(f"  根决策:   {len(roots)} 条")
    leaf_count = sum(1 for d in all_after if not graph.get_children_of(d.sid))
    print(f"  叶子决策: {leaf_count} 条")
    print(f"\n  MCP 工具已就绪: decision_children / decision_descendants")
    print(f"                    decision_ancestors / decision_tree")
    print(SEP)


if __name__ == "__main__":
    asyncio.run(main())