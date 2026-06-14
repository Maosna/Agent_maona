"""本地用户画像 — 每轮对话自动分析积累，等效 Cloud Memory 自动注入 profile"""
import json, asyncio, os, re, math, tempfile
from pathlib import Path
from datetime import datetime
from collections import Counter

PROFILE_PATH = Path.home() / ".agent_maona" / "memory" / "global" / "user_profile.json"
_profile_lock = asyncio.Lock()


def _load() -> dict:
    """加载当前画像"""
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            pass
    return {
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "total_conversations": 0,
        "total_tool_calls": 0,
        "top_tools": {},
        "top_keywords": {},
        "workspaces": {},
        "recent_topics": [],
    }


def _save(profile: dict):
    """原子写入画像（临时文件 + 重命名，避免并发写损坏）"""
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    profile["updated_at"] = datetime.now().isoformat()
    fd, tmp = tempfile.mkstemp(dir=str(PROFILE_PATH.parent), suffix=".json")
    try:
        os.write(fd, json.dumps(profile, ensure_ascii=False, indent=2).encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, str(PROFILE_PATH))  # 原子替换


def _tokenize(text: str) -> list[str]:
    """中文分词 + 英文分词 + 去停用词"""
    text = text.lower()
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'[_\-/.]', ' ', text)
    en_tokens = re.findall(r'[a-z0-9]+', text)
    cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
    stops = {'the','a','an','is','are','was','were','be','been','being',
             'have','has','had','do','does','did','will','would','could',
             'should','may','might','can','shall','to','of','in','for',
             'on','with','at','by','from','as','into','through','during',
             'and','but','or','not','no','if','then','else','this','that',
             'it','its','we','you','they','he','she','his','her','their',
             'i','my','me','our','us'}
    cn_stops = {'的','了','在','是','我','有','和','就','不','人','都','一',
                '个','上','也','很','到','说','要','去','你','会','着','没有',
                '看','好','自己','这','他','她','它','们','那','些','所','为'}
    result = [t for t in en_tokens if t not in stops and len(t) > 1 and not t.isdigit()]
    for i in range(len(cn_chars)):
        if cn_chars[i] not in cn_stops:
            result.append(cn_chars[i])
        if i < len(cn_chars) - 1:
            bigram = cn_chars[i] + cn_chars[i+1]
            if bigram not in cn_stops:
                result.append(bigram)
    return result


async def update_profile(project_id: str, workspace: str, messages: list):
    """
    对话结束后调用：从本轮对话中提取信息，累积更新用户画像。

    Args:
        project_id: 项目 ID
        workspace: 工作空间路径
        messages: 本轮对话的完整消息列表 [{role, content, tool_calls?}, ...]
    """
    if not messages or len(messages) < 2:
        return

    async with _profile_lock:
        profile = _load()
    profile["total_conversations"] += 1

    # 1. 统计工具调用
    tool_counter = Counter(profile.get("top_tools", {}))
    for m in messages:
        tc = m.get("tool_calls")
        if tc:
            if isinstance(tc, str):
                try:
                    tc = json.loads(tc)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(tc, list):
                for t in tc:
                    name = t.get("function", {}).get("name", "") if isinstance(t, dict) else str(t)
                    if name:
                        tool_counter[name] += 1
    # 保留 top 20 工具，超过 50 次调用则降权重新计算
    profile["top_tools"] = dict(tool_counter.most_common(20))
    profile["total_tool_calls"] = sum(tool_counter.values())

    # 2. 提取用户消息关键词
    all_user_text = " ".join(
        m.get("content", "") for m in messages
        if m.get("role") == "user" and m.get("content")
    )
    tokens = _tokenize(all_user_text)
    keyword_counter = Counter(profile.get("top_keywords", {}))
    for t in tokens:
        if len(t) >= 2:
            keyword_counter[t] += 1
    profile["top_keywords"] = dict(keyword_counter.most_common(30))

    # 3. 工作空间统计
    ws_counter = Counter(profile.get("workspaces", {}))
    if workspace:
        ws_counter[workspace] += 1
    profile["workspaces"] = dict(ws_counter.most_common(10))

    # 4. 对话主题（取前两条用户消息的前 40 字）
    topics = profile.get("recent_topics", [])
    user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
    if user_msgs:
        topic = user_msgs[0][:40].replace("\n", " ")
        if topic not in topics:
            topics.insert(0, topic)
    profile["recent_topics"] = topics[:10]

    _save(profile)


def get_profile_text() -> str:
    """
    返回格式化的画像文本，用于注入 system prompt。
    如果画像为空或只有基础数据，返回空字符串。
    """
    profile = _load()
    if profile.get("total_conversations", 0) < 1:
        return ""

    lines = ["## 用户画像（跨对话自动积累）"]
    lines.append(f"已进行 {profile['total_conversations']} 轮对话，累计 {profile['total_tool_calls']} 次工具调用。")

    # 常用工具
    top_tools = profile.get("top_tools", {})
    if top_tools:
        top5 = list(top_tools.items())[:5]
        lines.append(f"常用工具：{'、'.join(f'{k}({v}次)' for k, v in top5)}")

    # 关键主题
    top_kw = profile.get("top_keywords", {})
    if top_kw:
        top5 = list(top_kw.items())[:8]
        lines.append(f"高频词汇：{'、'.join(k for k, v in top5)}")

    # 常用工作空间
    workspaces = profile.get("workspaces", {})
    if workspaces:
        lines.append(f"工作空间：{'、'.join(workspaces.keys())}")

    # 最近话题
    recent = profile.get("recent_topics", [])
    if recent:
        lines.append(f"最近讨论：{'; '.join(recent[:5])}")

    return "\n".join(lines)
