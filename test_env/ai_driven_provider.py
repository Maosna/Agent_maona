"""
AI 驱动 Mock Provider — 通过文件桥接，让 WorkBuddy Agent 充当 Maona 的 LLM

协议：
1. Maona 调用 chat_non_stream(messages, tools)
2. Provider 将上下文写入 context.json，等待 decision.json
3. WorkBuddy Agent 读到 context.json，决策后写入 decision.json
4. Provider 读到决策，返回给 Maona
"""
import sys, os, json, asyncio, time

sys.path.insert(0, r'F:/工具/Agent_maona/backend')

CONTEXT_FILE = os.path.join(os.path.dirname(__file__), "context.json")
DECISION_FILE = os.path.join(os.path.dirname(__file__), "decision.json")
LOCK_FILE = os.path.join(os.path.dirname(__file__), "maona_ai.lock")
READY_FILE = os.path.join(os.path.dirname(__file__), "ai_ready.txt")


def show_context(round_num, messages, tools):
    """向 AI 展示当前上下文，便于分析"""
    last_user = ""
    last_assistant = ""
    tool_results = []

    for m in reversed(messages):
        role = m.get("role", "")
        c = str(m.get("content", ""))[:300]
        if role == "user" and not c.startswith("[") and not last_user:
            last_user = c
        elif role == "assistant" and not last_assistant:
            last_assistant = c
        elif role == "tool" and len(tool_results) < 5:
            tool_results.append(c)

    print(f"""
╔══════════════════════════════════════════════╗
║  Maona Agent 循环 — 第 {round_num} 轮               ║
╠══════════════════════════════════════════════╣
║  用户最后消息: {last_user[:70]}
║  AI 上一轮回复: {last_assistant[:70]}
║  最近工具结果 ({len(tool_results)}): 
""")
    for i, r in enumerate(tool_results):
        print(f"║    [{i}] {r[:80]}")
    print(f"║  可用工具 ({len(tools)}): {', '.join(t[:25] for t in tools[:10])}...")
    print(f"╚══════════════════════════════════════════════╝")


def format_prompt(messages, tools):
    """将 messages 格式化为可读的 prompt"""
    tool_names = [t['function']['name'] for t in (tools or [])]
    lines = ["=== 当前对话上下文 ===\n"]
    for i, m in enumerate(messages[-20:]):
        role = m.get("role", "?")
        content = str(m.get("content", ""))[:500]
        tc = m.get("tool_calls")
        if tc:
            names = [t.get('function', {}).get('name', '?') for t in tc]
            content += f"\n  [tool_calls: {', '.join(names)}]"
        lines.append(f"[{role}] {content}")
    lines.append(f"\n=== 可用工具 ({len(tool_names)}) ===")
    lines.append(", ".join(tool_names[:30]))
    lines.append("\n=== 你的决策 ===")
    lines.append("你需要决定下一步：")
    lines.append("1. 回复文本 → 写 {\"content\": \"你的回复\"}")
    lines.append("2. 调用工具 → 写 {\"tool_calls\": [{\"name\": \"工具名\", \"args\": {...}}]}")
    lines.append("3. 既有文本又有工具 → 同时包含 content 和 tool_calls")
    return "\n".join(lines)


class AIDrivenProvider:
    """通过文件桥接让外部 AI（WorkBuddy Agent）驱动决策"""

    def __init__(self):
        self.round = 0

    async def chat_non_stream(self, messages, tools=None, **kw):
        self.round += 1

        # 提取工具名列表
        tool_names = [t['function']['name'] for t in (tools or [])]

        # 展示上下文
        show_context(self.round, messages, tool_names)

        # 生成 prompt 写入文件
        prompt = format_prompt(messages, tools)

        # 写入 context.json（供外部 AI 读取）
        context = {
            "round": self.round,
            "prompt": prompt,
            "messages": messages[-30:],  # 最近 30 条
            "tool_names": tool_names,
        }
        with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2, default=str)

        # 写入就绪信号
        with open(READY_FILE, "w") as f:
            f.write(str(self.round))

        # 等待 AI 决策（轮询 decision.json）
        print(f"  ⏳ 等待 AI 决策（第 {self.round} 轮）...")
        print(f"  📄 上下文: {CONTEXT_FILE}")
        print(f"  📄 决策文件: {DECISION_FILE}")

        deadline = time.time() + 120
        while time.time() < deadline:
            if os.path.exists(DECISION_FILE):
                try:
                    with open(DECISION_FILE, "r", encoding="utf-8") as f:
                        decision = json.load(f)
                    # 清理文件，准备下一轮
                    os.remove(DECISION_FILE)
                    print(f"  ✅ AI 已决策: content={bool(decision.get('content'))}, tools={len(decision.get('tool_calls', []) or [])}")
                    return {
                        "content": decision.get("content", ""),
                        "tool_calls": decision.get("tool_calls"),
                    }
                except json.JSONDecodeError:
                    pass  # 文件正在写入，等待
            await asyncio.sleep(0.5)

        print(f"  ❌ AI 超时未响应")
        return {"content": "AI 驱动超时，请检查 decision.json", "tool_calls": None}


# ========== 辅助：生成 tool_calls JSON ==========
def mk_tc(name, args):
    return {
        "type": "function",
        "id": f"call_{name}",
        "function": {"name": name, "arguments": json.dumps(args)}
    }
