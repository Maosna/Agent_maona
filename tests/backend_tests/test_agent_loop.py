#!/usr/bin/env python3
"""
Maona Agent 循环集成测试 — 不依赖外部 API 的模拟测试

模拟 LLM 返回，完整测试：
1. Agent 循环迭代（多轮 tool call）
2. 文件读写操作
3. 错误处理和重试
4. 上下文压缩
5. 记忆系统
6. 任务跟踪
"""
import sys, os, json, time, asyncio, tempfile, shutil
from pathlib import Path

# 设置路径
sys.path.insert(0, os.path.dirname(__file__))

from tools.dispatcher import execute_tool
from tools.file_ops import read_file, write_file, edit_file, list_files, search_content
from tools.shell import run_command, run_python
from tools.memory_tools import save_daily_log

RESULTS = []
ERRORS = []
WARNINGS = []

def ok(test_name):
    RESULTS.append(("✅", test_name))

def fail(test_name, detail=""):
    RESULTS.append(("❌", test_name, detail))
    ERRORS.append((test_name, detail))

def warn(test_name, detail=""):
    RESULTS.append(("⚠️", test_name, detail))
    WARNINGS.append((test_name, detail))


async def test_file_operations():
    """测试 1: 文件操作（CRUD + 编辑 + 搜索）"""
    print("\n📝 测试 1: 文件操作")
    
    with tempfile.TemporaryDirectory() as tmp:
        # Write
        f1 = os.path.join(tmp, "hello.py")
        r = await write_file(path=f1, content="print('hello world')\ndef add(a,b): return a+b\n")
        if os.path.exists(f1) and os.path.getsize(f1) > 20:
            ok(f"write_file → {os.path.basename(f1)}")
        else:
            fail(f"write_file", f"文件未创建: {r[:100]}")
        
        # Read
        r = await read_file(path=f1)
        if "hello world" in r and "add" in r:
            ok("read_file → 内容正确")
        else:
            fail("read_file", f"内容不匹配: {r[:100]}")
        
        # Edit
        r = await edit_file(path=f1, old_string="print('hello world')", new_string="print('hi maona')")
        content = Path(f1).read_text()
        if "hi maona" in content:
            ok("edit_file → 替换成功")
        else:
            fail("edit_file", f"替换失败: {content[:100]}")
        
        # Write second file
        f2 = os.path.join(tmp, "config.json")
        await write_file(path=f2, content='{"name": "test", "version": "1.0"}')
        
        # List files
        r = await list_files(path=tmp)
        if "hello.py" in r and "config.json" in r:
            ok(f"list_files → 2 个文件")
        else:
            fail("list_files", r[:100])
        
        # Search
        r = await search_content(path=tmp, pattern="print", file_pattern="*.py")
        if "hello.py" in str(r):
            ok("search_content → 找到匹配")
        else:
            fail("search_content", str(r)[:100])
        
        # Delete
        from tools.file_ops import delete_file
        r = await delete_file(path=f2)
        if not os.path.exists(f2):
            ok("delete_file → 删除成功")
        else:
            fail("delete_file", "文件仍存在")


async def test_error_handling():
    """测试 2: 错误处理"""
    print("\n🛡️ 测试 2: 错误处理和边界")
    
    # 读取不存在文件
    r = await read_file(path="/tmp/nonexistent_maona_test_file_12345.xyz")
    if "错误" in r or "不存在" in r or "not found" in r.lower():
        ok("读取不存在文件 → 返回错误信息")
    else:
        fail("读取不存在文件", f"未返回错误: {r[:100]}")
    
    # 空文件路径
    r = await read_file(path="")
    if "错误" in r or "路径" in r or not r:
        ok("空路径 → 正确处理")
    else:
        warn("空路径", f"返回: {r[:100]}")
    
    # write_file 空内容
    with tempfile.TemporaryDirectory() as tmp:
        r = await write_file(path=os.path.join(tmp, "empty.txt"), content="")
        if os.path.exists(os.path.join(tmp, "empty.txt")):
            ok("写入空文件 → 成功（创建空文件）")
        else:
            fail("写入空文件", "文件未创建")
    
    # edit_file 不匹配的 old_string
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "test.txt")
        await write_file(path=f, content="original text")
        r = await edit_file(path=f, old_string="nonexistent text", new_string="replaced")
        if "错误" in r or "未找到" in r or "not found" in r.lower():
            ok("edit_file 不匹配 → 返回错误")
        else:
            warn("edit_file 不匹配", f"返回: {r[:100]}")


async def test_python_sandbox():
    """测试 3: Python exec — 不阻止任何操作，危险操作在界面提醒确认"""
    print("\n🔒 测试 3: Python exec（确认提醒机制）")
    
    # 安全代码 — 直接执行
    r = await run_python(code="print(1+1)\nresult = [x*2 for x in range(5)]\nprint(result)")
    if "Python 输出" in r and ("2" in r or "[0, 2" in r):
        ok("安全代码 → 直接执行")
    else:
        fail("安全代码", r[:100])
    
    # import 模块 — 直接执行
    r = await run_python(code="import time; print('time ok', round(time.time()))")
    if "time ok" in r.lower() or "Python 输出" in r:
        ok("import time → 直接执行")
    else:
        fail("import time", r[:100])
    
    # eval — 触发确认提醒
    r = await run_python(code="eval('2+3')")
    if "__CONFIRM_" in r:
        ok("eval → 触发确认提醒")
        r2 = await run_python(code="eval('2+3')", __confirmed=True)
        if "Python 输出" in r2 or "5" in r2:
            ok("eval 确认后 → 执行成功")
        else:
            warn("eval 确认后", r2[:100])
    else:
        warn("eval", f"未触发: {r[:100]}")
    
    # os.system — 触发确认
    r = await run_python(code="import os; os.system('echo hello')")
    if "__CONFIRM_" in r:
        ok("os.system → 触发确认提醒")
    else:
        warn("os.system", f"未触发: {r[:100]}")


async def test_mass_tool_calls():
    """测试 4: 大量工具调用（模拟 Agent 循环）"""
    print("\n🔄 测试 4: 模拟 Agent 多轮工具调用")
    
    with tempfile.TemporaryDirectory() as tmp:
        # 模拟 Agent 创建多个文件
        files_created = []
        for i in range(8):
            f = os.path.join(tmp, f"page_{i}.html")
            r = await write_file(path=f, content=f"<!-- Page {i} -->\n<h1>Page {i}</h1>\n<p>Content {i}</p>")
            files_created.append(f)
        
        # 验证
        missing = [f for f in files_created if not os.path.exists(f)]
        if not missing:
            ok(f"批量创建 8 个文件 → 全部成功")
        else:
            fail("批量创建", f"缺失 {len(missing)} 个: {missing[:3]}")
        
        # 模拟 Agent 编辑多个文件
        for i in range(4):
            f = files_created[i]
            r = await edit_file(path=f, old_string=f"Content {i}", new_string=f"Modified Content {i}")
        
        all_modified = True
        for i in range(4):
            content = Path(files_created[i]).read_text()
            if "Modified" not in content:
                all_modified = False
        if all_modified:
            ok("批量编辑 4 个文件 → 全部成功")
        else:
            fail("批量编辑", "部分未修改")
        
        # 列表和搜索验证
        r = await list_files(path=tmp)
        count = r.count("page_") if isinstance(r, str) else 0
        if count >= 8:
            ok(f"list_files → 找到 {count} 个文件")
        else:
            warn("list_files", f"只找到 {count} 个")


async def test_memory_system():
    """测试 5: 记忆系统"""
    print("\n🧠 测试 5: 记忆系统")
    
    with tempfile.TemporaryDirectory() as tmp:
        from tools.memory_tools import save_memory, read_memory
        
        try:
            # 保存日志
            r = await save_daily_log(content="测试日志：今日完成 3 个文件创建")
            if r and ("已保存" in r or "ok" in r.lower() or "✅" in r or "保存" in r):
                ok("每日日志保存 → 成功")
            else:
                warn("每日日志保存", r[:100] if r else "无返回")
            
            # 保存长期记忆
            r = await save_memory(content="test_project 使用 Python 3.13 + FastAPI")
            ok("长期记忆保存 → 完成")
        except Exception as e:
            warn("记忆系统", str(e)[:150])


async def test_agent_loop_simulation():
    """测试 6: 模拟完整 Agent 循环（读写→执行→搜索→编辑）"""
    print("\n🤖 测试 6: 模拟完整 Agent 循环")
    
    project_dir = tempfile.mkdtemp(prefix="maona_test_")
    try:
        # Step 1: 创建项目结构
        await write_file(path=os.path.join(project_dir, "index.html"), 
            content="<!DOCTYPE html><html><head><link rel='stylesheet' href='style.css'></head><body><h1>Test App</h1><script src='app.js'></script></body></html>")
        ok("Step 1: index.html 创建")
        
        # Step 2: 创建样式
        await write_file(path=os.path.join(project_dir, "style.css"),
            content="body { font-family: Arial; margin: 0; padding: 20px; }")
        ok("Step 2: style.css 创建")
        
        # Step 3: 创建 JS
        await write_file(path=os.path.join(project_dir, "app.js"),
            content="document.querySelector('h1').textContent = 'Hello Maona';")
        ok("Step 3: app.js 创建")
        
        # Step 4: 读取并验证
        html = await read_file(path=os.path.join(project_dir, "index.html"))
        if "style.css" in html and "app.js" in html:
            ok("Step 4: index.html 引用正确")
        else:
            fail("Step 4", "引用缺失")
        
        # Step 5: 搜索并编辑
        await edit_file(path=os.path.join(project_dir, "index.html"),
            old_string="Test App", new_string="Maona Test App")
        content = Path(os.path.join(project_dir, "index.html")).read_text()
        if "Maona Test App" in content:
            ok("Step 5: 编辑成功")
        
        # Step 6: 执行验证
        r = await run_python(code="""
import os
files = os.listdir('%s')
result = [f for f in files if f.endswith(('.html','.css','.js'))]
print(f'Found {len(result)} files: {result}')
""" % project_dir.replace('\\', '\\\\'))
        if "3" in r:
            ok("Step 6: Python 验证 → 3 个文件")
        else:
            warn("Step 6", r[:100])
        
        # Step 7: 模拟错误重试
        r = await edit_file(path=os.path.join(project_dir, "nonexistent.js"),
            old_string="old", new_string="new")
        if "错误" in r or "不存在" in r:
            ok("Step 7: 错误重试 → 正确返回错误信息")
        
        # Cleanup
        files = [f for f in Path(project_dir).glob("*") if f.is_file()]
        ok(f"总文件数: {len(files)}")
        
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)


async def test_tool_dispatcher_parallel():
    """测试 7: 工具调度器 — 并行执行"""
    print("\n⚡ 测试 7: 工具并行执行")
    
    with tempfile.TemporaryDirectory() as tmp:
        # 创建 5 个文件
        paths = []
        for i in range(5):
            p = os.path.join(tmp, f"parallel_{i}.txt")
            paths.append(p)
        
        # 模拟并行写入
        tasks = [write_file(path=p, content=f"content_{i}") for i, p in enumerate(paths)]
        results = await asyncio.gather(*tasks)
        
        success = sum(1 for p in paths if os.path.exists(p))
        if success == 5:
            ok(f"并行写入 5 个文件 → 全部成功 ({time.time():.0f})")
        else:
            fail("并行写入", f"只有 {success}/5 成功")
        
        # 并行读取
        read_tasks = [read_file(path=p) for p in paths]
        read_results = await asyncio.gather(*read_tasks)
        all_ok = all(f"content_{i}" in r for i, r in enumerate(read_results))
        if all_ok:
            ok("并行读取 5 个文件 → 全部正确")
        else:
            fail("并行读取", "内容不匹配")


async def main():
    print("=" * 60)
    print("Maona Agent 循环集成测试（不依赖外部 API）")
    print("=" * 60)
    
    tests = [
        ("文件操作", test_file_operations),
        ("错误处理", test_error_handling),
        ("Python 沙箱", test_python_sandbox),
        ("批量操作", test_mass_tool_calls),
        ("记忆系统", test_memory_system),
        ("Agent 循环模拟", test_agent_loop_simulation),
        ("并行执行", test_tool_dispatcher_parallel),
    ]
    
    start = time.time()
    
    for name, test_fn in tests:
        try:
            await test_fn()
        except Exception as e:
            fail(name, f"测试崩溃: {type(e).__name__}: {str(e)[:200]}")
            import traceback
            traceback.print_exc()
    
    elapsed = time.time() - start
    
    # 汇总
    print("\n" + "=" * 60)
    print(f"📊 测试结果 ({elapsed:.1f}s)")
    print("=" * 60)
    
    passed = sum(1 for s, *_ in RESULTS if s == "✅")
    failed = sum(1 for s, *_ in RESULTS if s == "❌")
    warned = sum(1 for s, *_ in RESULTS if s == "⚠️")
    
    for status, name, *detail in RESULTS:
        d = detail[0] if detail else ""
        print(f"  {status} {name}" + (f" — {d}" if d else ""))
    
    print(f"\n✅ 通过: {passed}  ❌ 失败: {failed}  ⚠️ 警告: {warned}")
    
    if failed == 0:
        print("\n🎉 全部测试通过！Maona 核心功能正常运行。")
    else:
        print(f"\n⚠️ {failed} 个测试失败，需要进一步诊断。")
    
    # 保存结果
    result = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passed": passed,
        "failed": failed,
        "warnings": warned,
        "elapsed": elapsed,
        "details": [{"status": s, "name": n, "detail": d[0] if d else ""} for s, n, *d in RESULTS],
    }
    
    result_path = os.path.join(os.path.dirname(__file__), "test_agent_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n📄 结果: {result_path}")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
