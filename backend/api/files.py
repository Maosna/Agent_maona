"""文件操作 API"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from tools.file_ops import _is_path_safe
from tools.ocr import ocr_preview, is_vision_model

router = APIRouter(prefix="/files", tags=["files"])


def _check_path(target: Path):
    if not _is_path_safe(target):
        raise HTTPException(status_code=403, detail="安全限制：不允许访问系统目录或敏感文件")


@router.get("/list")
async def list_files(path: str = ""):
    """列出目录内容"""
    if not path:
        path = str(Path.home())

    target = Path(path).resolve()
    _check_path(target)
    if not target.exists():
        raise HTTPException(status_code=404, detail="路径不存在")
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="不是目录")

    try:
        items = []
        for p in sorted(target.iterdir()):
            items.append({
                "name": p.name,
                "path": str(p),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else 0,
            })
        return {"path": str(target), "items": items}
    except PermissionError:
        raise HTTPException(status_code=403, detail="无权限访问")


@router.get("/read")
async def read_file(path: str):
    """读取文件内容"""
    target = Path(path).resolve()
    _check_path(target)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="不是文件")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": str(target), "content": content, "size": len(content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/home")
async def get_home():
    """获取用户主目录"""
    return {"path": str(Path.home())}


class OCRPreviewReq(BaseModel):
    data_url: str

@router.post("/ocr-preview")
async def ocr_preview_api(req: OCRPreviewReq):
    """预检图片 OCR 效果"""
    return ocr_preview(req.data_url)


# ===== 技能管理 =====
import skills as skills_mod

@router.get("/skills/list")
async def get_skills():
    """列出所有技能及其激活状态"""
    all_skills = skills_mod.list_skills()
    active = skills_mod.get_active_skills()
    for s in all_skills:
        s["active"] = s["id"] in active
    return {"skills": all_skills, "active": list(active)}

class SkillToggleReq(BaseModel):
    skill_ids: list[str]

@router.post("/skills/toggle")
async def toggle_skills(req: SkillToggleReq):
    """更新技能激活状态"""
    skills_mod.set_active_skills(req.skill_ids)
    return {"status": "ok", "active": req.skill_ids}
