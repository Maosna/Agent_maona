"""创意生成工具 — 图片生成 + 自动技能 + 定时任务"""
import json, asyncio, tempfile, subprocess
from pathlib import Path


# ===== 图片生成 =====
async def image_generate(prompt: str = "", size: str = "1024x1024", **kw) -> str:
    """调用 OpenAI 兼容的图片生成 API（仅 Pro 级 Provider）"""
    if not prompt:
        return "请提供图片描述"
    try:
        from providers.store import list_providers, _unmask
        from providers.model_settings import get_settings
    except ImportError:
        return "图片生成: 无法加载 Provider 配置"

    settings = get_settings()
    img_url = settings.get("image_api_url", "")
    img_key = settings.get("image_api_key", "")

    if not img_url:
        # 自动检测支持图片的 Provider（OpenAI / GLM / SiliconFlow / Azure）
        for p in list_providers():
            name = p.get("name", "").lower()
            if any(k in name for k in ["openai", "azure", "silicon", "glm"]):
                base = p.get("api_url", "").rstrip("/").replace("/chat/completions", "")
                img_url = f"{base}/images/generations"
                img_key = _unmask(p.get("api_key", ""))
                if img_key: break

    if not img_url or not img_key:
        return "图片生成: 未找到支持图片 API 的 Provider（需要 OpenAI/GLM/SiliconFlow），或请在设置中配置 image_api_url"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                img_url,
                json={"prompt": prompt, "n": 1, "size": size},
                headers={"Authorization": f"Bearer {img_key}", "Content-Type": "application/json"}
            )
            if r.status_code != 200:
                return f"图片生成失败: HTTP {r.status_code} - {r.text[:300]}"
            data = r.json()
            img_url_result = data.get("data", [{}])[0].get("url", "")
            if img_url_result:
                return f"图片已生成: {img_url_result}\n提示词: {prompt}"
            return f"图片已完成但无 URL: {str(data)[:500]}"
    except Exception as e:
        return f"图片生成异常: {e}"


# ===== HTML 预览 =====
def preview_html(content: str = "", filepath: str = "", **kw) -> str:
    """在应用内预览 HTML 内容或文件"""
    import tempfile
    p = None
    if filepath:
        p = Path(filepath)
        if not p.exists():
            return f"文件不存在: {filepath}"
    elif content:
        p = Path(tempfile.gettempdir()) / f"maona_preview_{Path(tempfile.gettempdir()).stat().st_ino}.html"
        p.write_text(content, encoding='utf-8')
    else:
        return "请提供 HTML 内容或文件路径"

    # 通知 Electron 打开预览窗口（如果可用）
    try:
        import os as _os; _os.startfile(str(p))
    except:
        pass

    return f"预览已打开: {p}\n\n提示: 如果应用内预览不可用，请在浏览器中打开该文件"


# ===== 自动技能积累 =====
def skill_auto_save(name: str = "", prompt_template: str = "", **kw) -> str:
    """完成任务后自动保存为可复用技能"""
    if not name or not prompt_template:
        return "请提供技能名称和模板"

    try:
        from skills import SKILLS_DIR, scan_skills
        skill_dir = SKILLS_DIR / name.replace(" ", "-").lower()
        skill_dir.mkdir(parents=True, exist_ok=True)

        # 写 SKILL.md
        skill_md = f"""---
id: {name.replace(' ', '-').lower()}
name: {name}
description: 自动生成的技能 - {name}
enabled: true
agent_created: true
---

# {name}

## 用途
自动从对话中积累的技能。

## 指令
{prompt_template}

## 触发条件
{kw.get('trigger', '用户明确要求执行此任务时')}
"""
        (skill_dir / "SKILL.md").write_text(skill_md, encoding='utf-8')

        # 注册到 state
        state_file = SKILLS_DIR / "state.json"
        state = {}
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding='utf-8'))
            except:
                pass
        state[name.replace(' ', '-').lower()] = {"enabled": True}
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))

        return f"技能已保存: {name}\n路径: {skill_dir}\n下次说「加载技能 {name}」即可复用"
    except Exception as e:
        return f"保存技能失败: {e}"


# ===== 定时任务 =====
_scheduled_tasks: list[dict] = []
_scheduler_started: bool = False


async def _scheduler_loop():
    """后台定时任务执行器（每分钟检查一次）"""
    import asyncio, subprocess, shlex
    while True:
        await asyncio.sleep(60)
        now = asyncio.get_event_loop().time()
        for t in _scheduled_tasks:
            if t.get("next_run", 0) <= now:
                try:
                    # 安全执行：分离命令和参数，禁止 shell 注入
                    cmd_parts = shlex.split(t["command"])
                    subprocess.run(cmd_parts, timeout=300, capture_output=True, text=True)
                except Exception:
                    pass
                t["next_run"] = now + t["interval"]


def _ensure_scheduler():
    """确保调度器只启动一次"""
    global _scheduler_started
    if _scheduler_started:
        return
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        loop.create_task(_scheduler_loop())
        _scheduler_started = True
    except Exception:
        pass


def schedule_task(command: str = "", interval_minutes: int = 0, description: str = "", **kw) -> str:
    """创建定时任务（进程内 cron）"""
    if not command or interval_minutes <= 0:
        return "请提供执行命令和间隔时间（分钟）"

    task = {
        "id": f"sched_{len(_scheduled_tasks)}",
        "command": command,
        "interval": interval_minutes * 60,
        "description": description or command[:50],
        "next_run": 0  # 立即执行
    }
    _scheduled_tasks.append(task)
    _ensure_scheduler()  # 确保后台调度器在运行
    return f"定时任务已创建: {task['description']}\n间隔: {interval_minutes} 分钟\n任务 ID: {task['id']}"


def list_scheduled_tasks(**kw) -> str:
    """列出所有定时任务"""
    if not _scheduled_tasks:
        return "没有定时任务"
    lines = ["定时任务列表:"]
    for t in _scheduled_tasks:
        lines.append(f"  [{t['id']}] {t['description']} - 每 {t['interval']//60} 分钟")
    return '\n'.join(lines)


def cancel_scheduled_task(task_id: str = "", **kw) -> str:
    """取消定时任务"""
    global _scheduled_tasks
    before = len(_scheduled_tasks)
    _scheduled_tasks = [t for t in _scheduled_tasks if t["id"] != task_id]
    if len(_scheduled_tasks) < before:
        return f"已取消任务: {task_id}"
    return f"未找到任务: {task_id}"


# 工具映射
CREATIVE_TOOLS = {
    "image_generate": image_generate,
    "preview_html": preview_html,
    "skill_auto_save": skill_auto_save,
    "schedule_task": schedule_task,
    "list_scheduled_tasks": list_scheduled_tasks,
    "cancel_scheduled_task": cancel_scheduled_task,
}
