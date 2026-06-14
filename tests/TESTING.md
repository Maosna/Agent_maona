# Maona 模拟调试指南

> 对其他 Agent 说的话：这个框架让你**不花一分钱 API** 就能模拟整个 Maona Agent 循环，完全按真实代码路径执行。用来找 Bug、验证修复、跑回归。

---

## 快速上手（3 步）

```bash
# 1. 进入测试目录
cd F:\工具\Agent_maona\test_env

# 2. 跑全部预设场景（7 个基础场景，不费 API）
python run_scenarios.py

# 3. 看结果
# 通过 7/7 = 一切正常
# 有失败 = 看 scenario_results.json 找哪个场景挂了
```

---

## 文件速查

| 文件 | 功能 | 用 API? |
|------|------|---------|
| `run_scenarios.py` | 7 个基础场景回放 | ❌ Smart Mock |
| `full_stress_test.py` | 5 场景连续对话压力测试 | ❌ Smart Mock |
| `real_llm_test.py` | 2 场景真 LLM 驱动 | ✅ 需要 Key |
| `complex_final.py` | 3 对话图书管理系统 | ✅ 需要 Key |
| `auto_mcp_real_test.py` | MCP 工具链测试 | ❌ Smart Mock |
| `stdin_provider.py` | Smart Mock LLM 实现 | — |

---

## Smart Mock 原理

```python
# decisions.jsonl — 每行一个决策
{"content": "我先创建文件", "tool_calls": [
  {"name": "write_file", "arguments": {"path": "x.py", "content": "print(1)"}}
]}
{"content": "完成", "tool_calls": null}
```

`stdin_provider.py` 接管了 LLM 调用，**按你的决策脚本逐行返回**，但 Maona 的所有其他代码——Agent 循环、工具执行、记忆、MCP——全部走真实路径。

**这意味着**：你可以在 `decisions.jsonl` 里故意写错参数、调用不存在的工具、写无限循环——看 Maona 怎么响应。

---

## 怎么用它来找 Bug

### 1. 测工具参数错误处理
```json
{"content": "试试看", "tool_calls": [
  {"name": "write_file", "arguments": {"wrong_param": 123}}
]}
```
→ 看 Maona 是否优雅报错、是否自动重试、重试消息是否包含具体错误信息。

### 2. 测边界值
```json
{"content": "", "tool_calls": [
  {"name": "write_file", "arguments": {"path": "x" * 10000, "content": "x"}}
]}
```
→ 极端长路径是否被拦截。

### 3. 测并发工具
```json
{"content": "并行创建", "tool_calls": [
  {"name": "write_file", "arguments": {"path": "a.py", "content": "1"}},
  {"name": "write_file", "arguments": {"path": "b.py", "content": "2"}},
  {"name": "write_file", "arguments": {"path": "c.py", "content": "3"}}
]}
```
→ 三工具同一轮是否正确并行执行。

### 4. 测记忆系统
```json
{"content": "记住：用户叫张三", "tool_calls": [
  {"name": "save_memory", "arguments": {"content": "用户叫张三", "category": "user_profile"}}
]}
```
然后新对话：
```json
{"content": "查记忆", "tool_calls": [
  {"name": "read_memory", "arguments": {"query": "张三"}}
]}
```
→ 跨对话记忆是否命中。

### 5. 测回退逻辑
```json
{"content": "读取不存在文件", "tool_calls": [
  {"name": "read_file", "arguments": {"path": "/nonexistent.txt"}},
  {"name": "edit_file", "arguments": {"path": "/real_file.py", "old_string": "...", "new_string": "..."}}
]}
```
→ 第一个失败后第二个是否正常执行（之前测出过 ghost.txt bug）。

---

## MCP 工具测试

```bash
python auto_mcp_real_test.py
```
这是**真 MCP 连接**测试。如果 Godot 编辑器开着（9080 端口），会直接调 16 个原子工具（create_scene/create_node/save_scene 等）。Smart Mock 在这里只模拟 LLM 决策，工具执行是真实的。

---

## 真 LLM 测试

```bash
python real_llm_test.py     # 仅当 DeepSeek Key 可用
python complex_final.py     # 3 对话连续任务
```
这些会**真正调 LLM**，用来看最终用户体验。smart mock 阶段通过后再跑。

---

## 写新测试场景

继承 `TestCase` 类写你的场景：

```python
tc = TestCase("测大文件", ws,
    "帮我处理一个100MB的文件",
    [
        {"content": "先检查文件大小", "tool_calls": [
            {"name": "list_files", "arguments": {"path": ws}}
        ]},
        {"content": "太大了，拒绝操作", "tool_calls": None},
    ])
await run_test(tc)
```

---

## Agent 自助调试工作流

```
1. 读这个文档 → 了解框架
2. 跑 run_scenarios.py → 确认基线是否通过
3. 看 scenario_results.json → 定位失败场景
4. 改对应 decisions.jsonl → 复现 Bug
5. 修代码 → 重跑 → 确认通过
6. 加新场景到 run_scenarios.py 防止回退
```
