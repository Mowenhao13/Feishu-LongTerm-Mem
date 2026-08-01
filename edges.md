HyperMem的图构建逻辑主要通过`HypergraphExtractor`类实现，构建一个三层超图结构（L1: 事实层，L2: 事件层，L3: 主题层）。<cite repo="EverMind-AI/EverOS" path="methods/HyperMem/hypermem/extractors/hypergraph_extractor.py" start="48-54" />

## 图构建流程

### 1. 构建L2层 - 事件节点
首先遍历所有episodes，为每个episode创建`EpisodeNode`并添加到超图中：<cite repo="EverMind-AI/EverOS" path="methods/HyperMem/hypermem/extractors/hypergraph_extractor.py" start="85-98" />

```python
for episode in episodes:
    episode_node = EpisodeNode.from_episode(
        episode=episode,
        fact_hyperedge_id="",
        hyperedge={}
    )
    hypergraph.episodes[episode_id] = episode_node
```

### 2. 构建L3层 - 主题节点和事件超边
为每个topic创建`TopicNode`，并添加对应的episode hyperedge来连接episodes到topics：<cite repo="EverMind-AI/EverOS" path="methods/HyperMem/hypermem/extractors/hypergraph_extractor.py" start="100-140" />

```python
hypergraph.add_hyperedge(
    layer="episode",
    hyperedge_id=episode_hyperedge.id,
    relation=episode_hyperedge.relation,
    weights=episode_hyperedge.weights,
    topic_node_id=episode_hyperedge.topic_node_id,
    created_at=episode_hyperedge.created_at,
    coherence_score=episode_hyperedge.coherence_score
)
```

### 3. 超边添加逻辑
`add_hyperedge`方法负责在指定层添加超边，并更新连接节点的邻接表：<cite repo="EverMind-AI/EverOS" path="methods/HyperMem/hypermem/structure.py" start="441-476" />

- **事实层超边**：连接facts到episodes，每个节点在`relation`字典中有一个角色（如"core", "temporal", "context"）<cite repo="EverMind-AI/EverOS" path="methods/HyperMem/hypermem/structure.py" start="449-460" />
- **事件层超边**：连接episodes到topics，同样使用relation字典和weights来表示关联强度<cite repo="EverMind-AI/EverOS" path="methods/HyperMem/hypermem/structure.py" start="462-473" />

## 超边结构
超边通过`relation`字典（节点ID → 角色）和`weights`字典（节点ID → 权重）来捕获高阶关联：<cite repo="EverMind-AI/EverOS" path="methods/HyperMem/hypermem/structure.py" start="867-880" />

```python
relation={
    "fact_1": "core",
    "fact_2": "temporal", 
    "fact_3": "context"
},
weights={
    "fact_1": 1.0,
    "fact_2": 0.7,
    "fact_3": 0.3
}
```

