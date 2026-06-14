"""图片 OCR 工具 — 把 base64 图片转为文字"""
import base64
import io
import os
import re
from pathlib import Path
from PIL import Image
import pytesseract

# Tesseract 路径检测
_tess_env = os.environ.get("TESSERACT_PATH", "")
_TESS_PATHS = [
    Path(__file__).parent.parent.parent / "tesseract" / "tesseract.exe",
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    Path("/usr/bin/tesseract"),
]
if _tess_env:
    _TESS_PATHS.insert(0, Path(_tess_env))
for p in _TESS_PATHS:
    if p.exists():
        pytesseract.pytesseract.tesseract_cmd = str(p)
        # TESSDATA 在 tessdata/ 子目录
        tessdata = p.parent / "tessdata"
        if tessdata.exists():
            os.environ["TESSDATA_PREFIX"] = str(tessdata)
        break

_TESS_READY = bool(pytesseract.pytesseract.tesseract_cmd)


def ocr_base64(data_url: str) -> str:
    """从 data:image/...;base64,xxx 提取文字（内部实现）"""
    return _do_ocr(data_url)


def ocr_preview(data_url: str) -> dict:
    """快速预检：返回 OCR 状态和文字预览"""
    if not _TESS_READY:
        return {"ok": False, "text": "", "hint": "OCR 未安装"}
    try:
        result = ocr_base64(data_url)
        # 去掉前缀
        clean = result.replace("(图片 OCR 结果):\n", "").replace("(图片 OCR 结果较少，建议用多模态模型): ", "")
        if result.startswith("(图片 OCR"):
            return {"ok": False, "text": clean[:200], "hint": result.split("):")[0] + ")"}
        return {"ok": True, "text": clean[:500], "hint": ""}
    except Exception as e:
        return {"ok": False, "text": "", "hint": str(e)}


def _do_ocr(data_url: str) -> str:
    """内部 OCR 实现"""
    if not _TESS_READY:
        return "(OCR 未配置：请安装 Tesseract OCR，或使用多模态模型)"
    try:
        b64 = re.sub(r"^data:image/\w+;base64,", "", data_url)
        img_bytes = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_bytes))

        # 预处理：转灰度 → 对比度增强 → 放大
        img = img.convert("L")
        w, h = img.size
        if w < 400 or h < 400:
            img = img.resize((w * 2, h * 2), Image.LANCZOS)

        # 自适应阈值二值化（对 UI 截图效果最好）
        try:
            from PIL import ImageFilter
            # 锐化
            img = img.filter(ImageFilter.SHARPEN)
            # 自适应二值化
            img = img.point(lambda x: 0 if x < 128 else 255)
        except:
            pass

        text = pytesseract.image_to_string(img, lang="chi_sim+eng",
            config="--psm 6 --oem 3")

        result = text.strip()
        if not result:
            return "(图片 OCR: 未识别到文字，可能是复杂的 UI 截图。建议用多模态模型如 GPT-4o 获得更好的图片理解)"
        if len(result) < 10:
            return f"(图片 OCR 结果较少，建议用多模态模型): {result}"
        return f"(图片 OCR 结果):\n{result}"
    except Exception as e:
        return f"(图片 OCR 失败: {e})"


# 已知支持多模态的模型名称模式
VISION_PATTERNS = [
    "gpt-4o", "gpt-4-turbo", "gpt-4-vision",
    "claude-3", "claude-3.5",
    "gemini-1.5", "gemini-2",
    "glm-4v", "cogview", "cogvlm",
    "qwen-vl", "qwen2-vl",
    "vision", "vl-", "-vl",
    "multimodal", "omni",
    "pixtral", "llava",
    "minicpm-v", "internvl",
]


def is_vision_model(model_id: str) -> bool:
    """检测模型是否支持多模态视觉"""
    if not model_id:
        return False
    lower = model_id.lower()
    return any(pattern in lower for pattern in VISION_PATTERNS)
