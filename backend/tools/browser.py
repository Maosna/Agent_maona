"""浏览器自动化 — Playwright 集成"""
import asyncio
from pathlib import Path

_BROWSER = None
_PAGE = None
_BROWSER_INSTANCE = None  # 实际的 Chromium browser 实例


async def _get_page():
    """懒加载浏览器实例"""
    global _BROWSER, _PAGE, _BROWSER_INSTANCE
    if _PAGE and not _PAGE.is_closed():
        return _PAGE
    try:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        _BROWSER = pw  # Playwright 管理器
        _BROWSER_INSTANCE = await pw.chromium.launch(headless=True)
        _PAGE = await _BROWSER_INSTANCE.new_page()
        await _PAGE.set_viewport_size({"width": 1280, "height": 720})
        return _PAGE
    except Exception:
        # 启动失败时清理已创建的资源
        await _cleanup_browser()
        return None


async def browser_navigate(url: str, **kw) -> str:
    """导航到 URL 并返回页面文本"""
    page = await _get_page()
    if not page:
        return "Playwright 未安装，请运行: pip install playwright && playwright install chromium"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        text = await page.inner_text("body")
        title = await page.title()
        return f"页面标题: {title}\nURL: {page.url}\n\n内容:\n{text[:5000]}"
    except Exception as e:
        return f"导航失败: {e}"


async def browser_screenshot(url: str = "", selector: str = "", full_page: bool = False, **kw) -> str:
    """截图当前页面或指定区域，保存到临时文件"""
    page = await _get_page()
    if not page:
        return "Playwright 未安装"
    try:
        if url and page.url != url:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        import tempfile, os
        out = Path(tempfile.gettempdir()) / f"maona_screenshot_{os.getpid()}.png"
        if selector:
            el = await page.query_selector(selector)
            if el:
                await el.screenshot(path=str(out))
            else:
                return f"未找到选择器: {selector}"
        else:
            await page.screenshot(path=str(out), full_page=full_page)

        return f"截图已保存: {out}\n尺寸: {out.stat().st_size} bytes"
    except Exception as e:
        return f"截图失败: {e}"


async def browser_click(selector: str, **kw) -> str:
    """点击页面元素"""
    page = await _get_page()
    if not page:
        return "Playwright 未安装"
    try:
        await page.click(selector, timeout=10000)
        return f"已点击: {selector}"
    except Exception as e:
        return f"点击失败: {e}"


async def browser_fill(selector: str, value: str, **kw) -> str:
    """填写表单字段"""
    page = await _get_page()
    if not page:
        return "Playwright 未安装"
    try:
        await page.fill(selector, value, timeout=10000)
        return f"已填写 {selector}: {value[:100]}"
    except Exception as e:
        return f"填写失败: {e}"


async def browser_extract(selector: str = "body", **kw) -> str:
    """提取页面元素的文本/HTML"""
    page = await _get_page()
    if not page:
        return "Playwright 未安装"
    try:
        text = await page.inner_text(selector)
        return text[:8000] if text else "(空)"
    except Exception as e:
        return f"提取失败: {e}"


async def browser_wait(ms: int = 1000, **kw) -> str:
    """等待指定毫秒"""
    await asyncio.sleep(ms / 1000)
    return f"已等待 {ms}ms"


async def _cleanup_browser():
    """安全清理浏览器资源"""
    global _BROWSER, _PAGE, _BROWSER_INSTANCE
    try:
        if _PAGE and not _PAGE.is_closed():
            await _PAGE.close()
    except Exception:
        pass
    try:
        if _BROWSER_INSTANCE:
            await _BROWSER_INSTANCE.close()
    except Exception:
        pass
    try:
        if _BROWSER:
            await _BROWSER.stop()
    except Exception:
        pass
    _PAGE = None
    _BROWSER_INSTANCE = None
    _BROWSER = None


async def browser_close(**kw) -> str:
    """关闭浏览器"""
    try:
        await _cleanup_browser()
        return "浏览器已关闭"
    except Exception as e:
        return f"关闭失败: {e}"


# 工具映射
BROWSER_TOOLS = {
    "browser_navigate": browser_navigate,
    "browser_screenshot": browser_screenshot,
    "browser_click": browser_click,
    "browser_fill": browser_fill,
    "browser_extract": browser_extract,
    "browser_wait": browser_wait,
    "browser_close": browser_close,
}
