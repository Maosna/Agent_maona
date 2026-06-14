"""验证闭环 —— 生成→验证→自动修复循环

当 AI 完成代码/文件生成后，自动触发验证流程：
1. 语法检查 (run_check / lsp_diagnose)
2. 功能测试 (run_test)
3. 预览确认 (preview_html / deploy_preview)
4. 差异对比 → 自动修复

集成到系统提示词中：要求 AI 在生成代码后自动验证。
"""

VALIDATION_PROMPT = """
## 验证闭环（强制执行）

每完成一项代码生成或文件创建任务后，你必须执行以下验证步骤，不可跳过：

1. **语法验证**: 对 Python/JS 代码调用 run_check(path) 或 lsp_diagnose(filepath)
2. **功能测试**: 如项目有测试，调用 run_test(path)
3. **预览确认**: 对 HTML/CSS 调用 preview_html(content) 查看效果
4. **自动修复**: 如任何验证失败(SYNTAX ERROR / FAILED / test failed)：
   - 分析错误信息
   - 修正代码
   - 重新验证，直到通过（最多 3 轮）
   - 如果 3 轮后仍未通过，向用户报告并请求指导

拒绝在没有验证的情况下声称"完成"。用户期待的"完成"包含验证通过。
"""

# 验证管道的模式定义
VERIFY_PIPELINES = {
    ".py": ["run_check", "lsp_diagnose"],
    ".js": ["run_check"],
    ".html": ["preview_html"],
    ".css": ["preview_html"],
    ".gd": ["validate_gdscript"],
}

def get_verify_pipeline(file_path: str) -> list[str]:
    """根据文件类型返回验证工具链"""
    import os
    ext = os.path.splitext(file_path)[1].lower()
    return VERIFY_PIPELINES.get(ext, ["lsp_diagnose"])
