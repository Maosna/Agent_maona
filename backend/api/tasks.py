"""后台任务 API"""
import asyncio
from fastapi import APIRouter
from tasks.runner import create_task, get_task, run_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("")
async def start_task(prompt: str, provider: str = "", model: str = "",
                     project: str = "agent_maona", workspace: str = None):
    """启动后台任务"""
    if not prompt.strip():
        return {"error": "prompt 不能为空"}
    if len(prompt) > 50000:
        return {"error": "消息过长，单条消息不能超过 50000 字符"}
    task = create_task(prompt, provider, model, project, workspace)
    asyncio.create_task(run_task(task["id"]))
    return {"task_id": task["id"], "status": "pending"}


@router.get("/{task_id}")
async def check_task(task_id: str):
    """查询任务状态"""
    return get_task(task_id)
