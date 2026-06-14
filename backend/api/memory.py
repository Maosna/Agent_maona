"""记忆 API - 支持项目隔离 + 工作空间本地存储"""
from fastapi import APIRouter
from datetime import datetime
from memory import store, context as ctx

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/daily")
async def get_daily_memory(project: str = "default", date_str: str = None, workspace: str = None):
    """获取某天的项目记忆"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    content = store.read_daily(project, date_str, workspace)
    return {"project": project, "date": date_str, "content": content, "exists": bool(content)}


@router.get("/longterm")
async def get_longterm_memory(project: str = "default", workspace: str = None):
    """获取项目长期记忆"""
    content = store.read_longterm(project, workspace)
    return {"project": project, "content": content, "exists": bool(content)}


@router.post("/append")
async def append_memory(content: str, project: str = "default", date_str: str = None, workspace: str = None):
    """追加每日记忆"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    store.append_daily(project, content, date_str, workspace)
    return {"status": "ok", "project": project, "date": date_str}


@router.put("/longterm")
async def update_longterm(content: str, project: str = "default", workspace: str = None):
    """更新项目长期记忆"""
    store.write_longterm(project, content, workspace)
    return {"status": "ok", "project": project}


@router.get("/context")
async def get_context(project: str = "default", workspace: str = None):
    """获取当前项目的完整记忆上下文"""
    return {
        "project": project,
        "context": ctx.build_context(project, workspace),
    }


@router.get("/prefs")
async def get_user_prefs():
    """获取全局用户偏好"""
    return store.read_prefs()


@router.put("/prefs")
async def update_user_prefs(key: str, value: str):
    """更新全局用户偏好"""
    store.update_prefs(key, value)
    return {"status": "ok", "key": key}


@router.get("/projects")
async def get_projects():
    return {"projects": store.list_projects()}


@router.get("/logs")
async def get_daily_logs(project: str = "default", workspace: str = None):
    """获取工作空间的每日日志列表"""
    return {"logs": store.list_daily_logs(project, workspace)}


@router.get("/workspaces")
async def get_workspaces():
    """获取工作空间列表"""
    return {"workspaces": store.read_prefs().get("workspaces", [])}


@router.put("/workspaces")
async def save_workspaces(data: dict):
    """保存工作空间列表"""
    store.update_prefs("workspaces", data.get("workspaces", []))
    return {"status": "ok"}


@router.get("/default-workspace")
async def get_default_workspace():
    """获取默认工作空间路径"""
    return {"path": store.read_prefs().get("default_workspace", "")}


@router.put("/default-workspace")
async def set_default_workspace(path: str = ""):
    """设置默认工作空间路径"""
    store.update_prefs("default_workspace", path)
    return {"status": "ok", "path": path}
