"""后台任务系统 — 异步执行 Agent 任务，完成后保存结果"""
import json
import asyncio
import uuid
from pathlib import Path
from datetime import datetime, timedelta

TASK_DIR = Path.home() / ".agent_maona" / "tasks"
TASK_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_old_tasks(max_age_hours: int = 24):
    """清理超过指定时间的任务文件"""
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    for f in TASK_DIR.glob("*.json"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
        except:
            pass


def create_task(prompt: str, provider_name: str, model: str, project: str, workspace: str = None) -> dict:
    """创建后台任务，返回任务信息"""
    task_id = uuid.uuid4().hex[:12]
    task = {
        "id": task_id,
        "prompt": prompt,
        "provider": provider_name,
        "model": model,
        "project": project,
        "workspace": workspace,
        "status": "pending",
        "result": "",
        "error": "",
        "created_at": datetime.now().isoformat(),
        "done_at": None,
    }
    _save(task_id, task)
    return task


def get_task(task_id: str) -> dict:
    f = TASK_DIR / f"{task_id}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"error": "任务不存在"}


def _save(task_id: str, task: dict):
    f = TASK_DIR / f"{task_id}.json"
    f.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")


def _update(task_id: str, **kw):
    task = get_task(task_id)
    task.update(kw)
    _save(task_id, task)


async def run_task(task_id: str):
    """在后台执行 Agent 任务"""
    from providers import manager as pm, store as ps
    from tools.definitions import TOOLS
    from tools.dispatcher import execute_tool
    from config import SYSTEM_PROMPT
    from memory.context import build_context
    from memory.conversations import ensure_project, create_conversation, save_message
    from memory.store import append_daily

    task = get_task(task_id)
    try:
        _update(task_id, status="running")

        provider = pm.get_provider(task["provider"], task["model"])
        project = task["project"]
        workspace = task.get("workspace")

        # 构建上下文
        memory_ctx = build_context(project, workspace)
        tailored_prompt = SYSTEM_PROMPT
        if memory_ctx:
            tailored_prompt += f"\n\n## 工作空间记忆\n{memory_ctx}"

        messages = [
            {"role": "system", "content": tailored_prompt},
            {"role": "user", "content": task["prompt"]},
        ]

        # Agent 循环
        MAX_ROUNDS = 20
        result = ""
        for _ in range(MAX_ROUNDS):
            resp = await provider.chat_non_stream(messages, TOOLS)
            if resp.get("error"):
                result = f"[错误: {resp['error']}]"
                break

            tool_calls = resp.get("tool_calls")
            reasoning = resp.get("reasoning")
            if tool_calls:
                msg = {"role": "assistant", "tool_calls": tool_calls}
                if resp.get("content"):
                    msg["content"] = resp["content"]
                if reasoning:
                    msg["reasoning_content"] = reasoning
                messages.append(msg)
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "unknown")
                    args_str = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}
                    exec_result = await execute_tool(name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id") or f"call_{name}",
                        "content": exec_result[:2000],
                    })
                continue

            result = resp.get("content") or ""
            break

        _update(task_id, status="done", result=result, done_at=datetime.now().isoformat())

        # 保存到对话记录
        await ensure_project(project)
        conv_id = await create_conversation(project, task["prompt"][:30])
        await save_message(conv_id, "user", task["prompt"])
        if result:
            await save_message(conv_id, "assistant", result)

        # 写入每日日志
        try:
            summary = f"## 后台任务\n- 请求: {task['prompt'][:200]}\n- 结果: {result[:500]}"
            append_daily(project, summary, workspace=workspace)
        except:
            pass

    except Exception as e:
        _update(task_id, status="error", error=str(e), done_at=datetime.now().isoformat())
