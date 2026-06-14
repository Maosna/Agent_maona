"""人设模板存储"""
import json
from pathlib import Path

STORE_PATH = Path.home() / ".agent_maona" / "personas.json"

DEFAULT_PERSONAS = [
    {
        "id": "default",
        "name": "默认",
        "emoji": "",
        "prompt": "",
    },
    {
        "id": "coder",
        "name": "代码专家",
        "emoji": "",
        "prompt": "你是一位资深软件工程师。回复中优先给出代码方案，附带关键注释。解释原理时简洁明了。",
    },
    {
        "id": "pm",
        "name": "产品经理",
        "emoji": "",
        "prompt": "你是一位产品经理。分析需求、梳理流程、评估优先级。给出结构化的产品方案，包含用户场景和验收标准。",
    },
    {
        "id": "translator",
        "name": "翻译助手",
        "emoji": "",
        "prompt": "你是一个翻译工具。只做翻译，不要解释、不要补充。如果输入为中文则翻译为英文，反之亦然。",
    },
    {
        "id": "reviewer",
        "name": "代码审查",
        "emoji": "",
        "prompt": "你是一位严格的代码审查员。关注：潜在 Bug、安全问题、性能瓶颈、可读性、最佳实践。给出具体修改建议。",
    },
    {
        "id": "explainer",
        "name": "详细解释",
        "emoji": "",
        "prompt": "回复要详细全面。给出完整的分析过程、步骤、原因和示例。不要跳过任何细节。",
    },
    {
        "id": "concise",
        "name": "言简意赅",
        "emoji": "",
        "prompt": "回复要极其简洁。每条不超过三句话。直接给答案，不解释过程除非被要求。",
    },
]


def _load() -> dict:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        # 文件损坏 → 仅返回默认不覆盖现有文件
        return {"personas": DEFAULT_PERSONAS}
    # 文件不存在 → 写入默认
    data = {"personas": DEFAULT_PERSONAS}
    _save(data)
    return data


def _save(data: dict):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_personas() -> list[dict]:
    return _load().get("personas", [])


def get_persona(pid: str) -> dict | None:
    for p in list_personas():
        if p["id"] == pid:
            return p
    return None


def add_persona(persona: dict):
    data = _load()
    data.setdefault("personas", [])
    # 去重
    data["personas"] = [p for p in data["personas"] if p["id"] != persona["id"]]
    data["personas"].append(persona)
    _save(data)


def remove_persona(pid: str):
    if pid == "default":
        return
    data = _load()
    data["personas"] = [p for p in data.get("personas", []) if p["id"] != pid]
    _save(data)
