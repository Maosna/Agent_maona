"""混合记忆检索 —— 向量语义 + 图谱关系

结构:
- 向量索引：已有 RAG (rag_build/rag_search)，语义相似
- 图谱：实体间关系，用于确定性遍历查询
  {
    "nodes": {"entity_name": {"type": "file|concept|task|pref", "attrs": {...}}},
    "edges": [{"from": "A", "to": "B", "relation": "depends_on|contains|similar_to|..."}]
  }

查询策略：
1. 向量搜索 → 候选实体
2. 图谱遍历 → 扩展关联实体
3. 重排序 → 返回最佳结果
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

GRAPH_PATH = Path.home() / ".agent_maona" / "knowledge_graph.json"


def _load_graph() -> dict:
    if GRAPH_PATH.exists():
        try:
            return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            pass
    return {"nodes": {}, "edges": []}


def _save_graph(g: dict):
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GRAPH_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(GRAPH_PATH)


def add_node(name: str, node_type: str = "concept", **attrs):
    """添加或更新图谱节点"""
    g = _load_graph()
    g["nodes"][name] = {
        "type": node_type,
        "updated_at": datetime.now().isoformat(),
        **attrs,
    }
    _save_graph(g)


def add_edge(from_node: str, to_node: str, relation: str = "related_to"):
    """添加关系边"""
    g = _load_graph()
    # 去重
    for e in g["edges"]:
        if e["from"] == from_node and e["to"] == to_node and e["relation"] == relation:
            return
    g["edges"].append({
        "from": from_node,
        "to": to_node,
        "relation": relation,
        "created_at": datetime.now().isoformat(),
    })
    _save_graph(g)


def traverse(from_node: str, relation: str = None, depth: int = 2) -> list[dict]:
    """从指定节点出发，BFS 遍历关系图"""
    g = _load_graph()
    edges = g["edges"]
    nodes = g["nodes"]

    visited = {from_node}
    results = []
    queue = [(from_node, 0)]

    while queue and depth > 0:
        current, d = queue.pop(0)
        if d > depth:
            continue

        for e in edges:
            if relation and e["relation"] != relation:
                continue

            neighbor = None
            if e["from"] == current and e["to"] not in visited:
                neighbor = e["to"]
            elif e["to"] == current and e["from"] not in visited:
                neighbor = e["from"]

            if neighbor and neighbor in nodes:
                visited.add(neighbor)
                queue.append((neighbor, d + 1))
                results.append({
                    "name": neighbor,
                    "relation": e["relation"],
                    "depth": d + 1,
                    **nodes[neighbor],
                })

    return results


def search_related(query: str, top_k: int = 5) -> list[dict]:
    """综合搜索：先向量匹配，再图谱扩展"""
    g = _load_graph()
    nodes = g["nodes"]

    # 简单关键词匹配（可升级为向量搜索）
    results = []
    query_lower = query.lower()
    for name, attrs in nodes.items():
        score = 0
        if query_lower in name.lower():
            score = 1.0
        elif any(query_lower in str(v).lower() for v in attrs.values()):
            score = 0.5
        if score > 0:
            # 扩展关联
            related = traverse(name, depth=1)
            results.append({
                "name": name,
                "score": score,
                "type": attrs.get("type", "concept"),
                "related": [r["name"] for r in related[:3]],
                **attrs,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def auto_build_from_memory():
    """从长期记忆自动构建知识图谱"""
    from memory.store import read_longterm
    import re

    content = read_longterm("agent_maona")
    if not content:
        return

    # 提取项目名和关联
    projects = re.findall(r'##\s+(.+)', content)
    for proj in projects:
        add_node(proj.strip(), "project")

    # 提取文件路径关系
    paths = re.findall(r'`([^`]+\.(?:py|js|html|css|json|md))`', content)
    for i, p1 in enumerate(paths):
        for p2 in paths[i+1:]:
            if p1.split("/")[0] == p2.split("/")[0]:  # 同目录
                add_edge(p1, p2, "same_dir")
