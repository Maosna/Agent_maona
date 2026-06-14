#!/usr/bin/env python3
"""复杂长任务模拟器 — 模拟 agent 循环，观察压缩/token/上下文行为

用法: python scripts/simulate_complex_task.py
"""

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from api.chat import (
    estimate_tokens, TOKEN_BUDGET, COMPRESS_THRESHOLD,
    MAX_TOOL_ROUNDS, KEEP_RECENT_ROUNDS
)


class FakeMsg:
    def __init__(self, role="", content="", tool_calls=None, tool_call_id=None):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id


def gen_large_file(filename: str, size_kb: int = 3) -> str:
    lines = [f"// File: {filename} // Line {i}" for i in range(size_kb * 40)]
    return "\n".join(lines)


def simulate():
    messages = [
        FakeMsg("system",
            "你是 Maona，AI 办公助手。\n" * 30  # ~900 chars
            + "当前工作空间: F:/游戏/项目/0/galgame\n"
            + "\n## 会话环境（已缓存）\n- hasProject: ✅\n- hasEditor: ✅\n- editorListening: ✅\n- gameDir: F:/游戏/项目/0/galgame\n"
            + "⚠️ 以上环境信息在本轮对话开始时已确认，不要重新探测。\n"
        )
    ]

    all_rounds = []
    compression_rounds = []
    total_tools = 0

    print(f"=== 复杂长任务模拟器 ===")
    print(f"MAX_ROUNDS={MAX_TOOL_ROUNDS}  BUDGET={TOKEN_BUDGET:,}  THRESHOLD={COMPRESS_THRESHOLD}")
    print()

    for round_i in range(MAX_TOOL_ROUNDS):
        # User message every 4 rounds
        if round_i % 4 == 0:
            messages.append(FakeMsg("user",
                f"继续完善 Godot 项目，第 {round_i} 步：需要修改 "
                f"{['角色控制器','对话系统','存档系统','UI层','战斗逻辑','地图系统'][min(round_i//4, 5)]}"
                f"，涉及 {2 + (round_i % 3)} 个文件。"
            ))

        # Round text
        round_text = (
            f"好的，我来处理第 {round_i} 步。"
            f"{'这是一个复杂的跨文件修改，需要先阅读现有代码。' if round_i % 10 == 0 else ''}"
            f"{'需要检查 signal 连接和 autoload API。' if round_i % 7 == 0 else ''}"
        )
        messages.append(FakeMsg("assistant", round_text))

        # Tool calls: 1-3 per round
        num_tools = min(3, 1 + (round_i % 3))
        for t in range(num_tools):
            total_tools += 1
            tool_names = ["read_file", "write_file", "edit_file", "search_content", "validate_gdscript",
                         "task_create", "task_update", "godot_setup", "cache_env", "run_command"]
            tool = tool_names[(round_i + t) % len(tool_names)]

            tc_id = f"call_{tool}_{round_i}_{t}"

            if tool == "read_file":
                args = json.dumps({"file_path": f"scripts/module_{round_i % 15}.gd"})
                result = gen_large_file(f"module_{round_i % 15}.gd", size_kb=3)
            elif tool == "write_file":
                args = json.dumps({"file_path": f"scripts/new_{round_i}_{t}.gd",
                                  "content": "extends Node\nfunc _ready(): pass\n"})
                result = f"文件 scripts/new_{round_i}_{t}.gd 创建成功（15行）"
            elif tool == "edit_file":
                args = json.dumps({"file_path": f"scripts/module_{round_i % 15}.gd",
                                  "old_string": "extends Node", "new_string": "extends CharacterBody2D"})
                result = "编辑成功，1处替换"
            elif tool == "search_content":
                args = json.dumps({"path": "scripts", "query": "signal"})
                result = f"找到 {5 + round_i % 20} 个信号声明"
            elif tool == "validate_gdscript":
                result = f"✅ 检查通过，{round_i % 3} 个警告（类型标注相关）"
                args = json.dumps({"project_dir": "F:/游戏/项目/0/galgame"})
            elif tool == "task_create":
                args = json.dumps({"subject": f"步骤{round_i}", "description": f"第{round_i}步操作"})
                result = f"任务已创建: task_{round_i}"
            elif tool == "task_update":
                args = json.dumps({"taskId": f"task_{round_i}", "status": "completed"})
                result = "任务已标记完成"
            else:
                args = "{}"
                result = f"操作完成：{tool}"

            # assistant tool_call message
            messages.append(FakeMsg("assistant", "",
                tool_calls=[{
                    "id": tc_id, "type": "function",
                    "function": {"name": tool, "arguments": args}
                }]
            ))
            # tool result
            messages.append(FakeMsg("tool", result, tool_call_id=tc_id))

        # Check token budget
        est = estimate_tokens(messages)
        all_rounds.append({
            "round": round_i, "msgs": len(messages),
            "tokens": est, "pct": round(est / TOKEN_BUDGET * 100, 1),
            "tools": total_tools,
        })

        # Simulate compression
        if round_i >= 3 and round_i % 4 == 0:
            if est > TOKEN_BUDGET * COMPRESS_THRESHOLD:
                compression_rounds.append(round_i)
                system_msg = messages[0]
                recent = messages[-6:]
                old_count = len(messages) - 7
                messages = [system_msg] + recent
                after_est = estimate_tokens(messages)
                print(f"  [压缩#{len(compression_rounds)}] 第{round_i}轮: {old_count}条 → "
                      f"tokens {est:,}→{after_est:,} ({est/TOKEN_BUDGET*100:.1f}%→{after_est/TOKEN_BUDGET*100:.1f}%)")

    return all_rounds, compression_rounds, total_tools, messages


# ---- Main ----

if __name__ == "__main__":
    rounds, comps, tools, msgs = simulate()

    print(f"\n=== 结果 ===")
    print(f"模拟轮数: {len(rounds)}  工具调用: {tools}  压缩: {len(comps)}次")
    print(f"最终消息: {len(msgs)}条  tokens: {estimate_tokens(msgs):,} ({estimate_tokens(msgs)/TOKEN_BUDGET*100:.1f}%)")

    # 指标
    print(f"\n=== 指标 ===")
    if comps:
        gaps = [comps[i+1] - comps[i] for i in range(len(comps)-1)]
        if gaps:
            print(f"压缩间隔: avg={sum(gaps)/len(gaps):.1f} min={min(gaps)} max={max(gaps)}")

    # Token 曲线
    first, last = rounds[:10], rounds[-10:]
    print(f"Token使用率: 前10轮avg={sum(r['pct'] for r in first)/10:.1f}%  "
          f"后10轮avg={sum(r['pct'] for r in last)/10:.1f}%")

    # 上下文幸存
    final_text = " ".join([m.content for m in msgs if m.content])
    for label, keyword in [("早期(0)", "第 0 步"), ("中期(50)", "第 50 步"), ("后期(140)", "第 140 步")]:
        print(f"上下文幸存 {label}: {'是' if keyword in final_text else '否（已丢失）'}")

    # 边界条件
    print(f"\n=== 边界检查 ===")
    if len(rounds) >= MAX_TOOL_ROUNDS:
        print(f"🔴 达到 MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}) ！")
    print(f"ℹ️ 子Agent: 5轮/30工具 — 复杂子任务可能不够")
    if comps and min(gaps) < 5 if 'gaps' in dir() and gaps else False:
        print(f"⚠️ 压缩间隔过短(m={min(gaps)}) — 摘要可能质量下降")
    print(f"\n=== 模拟完成 ===")
