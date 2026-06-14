"""stdin Provider — 通过 decisions.jsonl 队列让 AI 驱动 Agent

协议：
1. Provider 写入 context.json（每轮覆盖）
2. Provider 从 decisions.jsonl 读取下一行作为决策
3. AI 逐行追加到 decisions.jsonl
"""
import sys, os, json, asyncio, time

sys.path.insert(0, r'F:/工具/Agent_maona/backend')

DECISIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "decisions.jsonl")


class StdinProvider:
    def __init__(self, clear_on_init=True):
        self.round = 0
        self._consumed = 0
        if clear_on_init:
            try: os.remove(DECISIONS_FILE)
            except: pass

    def _read_decision(self):
        """阻塞读取 decisions.jsonl 的下一个未消费行"""
        while True:
            try:
                with open(DECISIONS_FILE, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip()]
                if len(lines) > self._consumed:
                    decision = json.loads(lines[self._consumed])
                    self._consumed += 1
                    return decision
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(0.3)

    async def chat_non_stream(self, messages, tools=None, **kw):
        self.round += 1

        # 自动处理上下文压缩/摘要请求
        last_content = ""
        for m in reversed(messages):
            c = str(m.get("content", ""))
            if c and not c.startswith("["):
                last_content = c
                break
        if "请将以上对话总结" in last_content:
            return {"content": "## 对话摘要\n用户请求创建文件，任务已完成。", "tool_calls": None}

        tool_names = [t['function']['name'] for t in (tools or [])]

        ctx = {"round": self.round, "conversation": []}
        for m in messages[-15:]:
            role = m.get("role", "?")
            c = str(m.get("content", ""))
            if role == "system":
                ctx["system_hint"] = c[:200]
            elif role == "tool":
                ctx["conversation"].append({"role": "tool", "result": c[:200]})
            else:
                ctx["conversation"].append({"role": role, "content": c[:400]})
                tc = m.get("tool_calls")
                if tc:
                    ctx["conversation"][-1]["tool_calls"] = [
                        t.get("function", {}).get("name", "?") for t in tc
                    ]
        ctx["available_tools"] = tool_names[:30]

        # 输出状态
        last = ctx['conversation'][-1] if ctx['conversation'] else {}
        role = last.get('role', '?')
        content = last.get('content', '')[:80]
        sys.stdout.write(f"\nR{self.round} [{role}] {content}\n")
        sys.stdout.flush()

        # 写入 context.json
        with open("context.json", "w", encoding="utf-8") as f:
            json.dump(ctx, f, ensure_ascii=False)
            f.flush()

        # 阻塞等待决策
        decision = await asyncio.to_thread(self._read_decision)

        # 标准化 tool_calls 格式
        if decision.get("tool_calls"):
            for tc in decision["tool_calls"]:
                tc.setdefault("type", "function")
                tc.setdefault("id", f"call_{tc['function']['name']}")
                if isinstance(tc["function"].get("arguments"), dict):
                    tc["function"]["arguments"] = json.dumps(tc["function"]["arguments"])

        return {
            "content": decision.get("content", ""),
            "tool_calls": decision.get("tool_calls"),
        }
