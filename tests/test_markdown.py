import re

text = """## ✅ 修改完成


本次修复了以下问题：



### 后端

- **OpenAIProvider** 添加 aclose() 方法

- skills.py 移除 nest_asyncio.apply()


### 前端

| 组件 | 变更 |
|------|------|
| 侧栏 | 新增任务分区 |
| 输入框 | 修复文件读取 |

示例代码：

```js
app.requestSingleInstanceLock()
if (!gotTheLock) app.quit()
```


所有修改已通过测试 ✅"""

# Simulate simpleMarkdown
s = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# Step 1: compress blank lines
s = re.sub(r'\n{2,}', '\n\n', s)
print("=== After blank line compression ===")
print(s)
print("=== End ===")
print()

# Count blank line pairs
blanks = len(re.findall(r'\n\n', s))
print(f"Count of '\\n\\n' pairs: {blanks}")
print(f"Each pair = 1 visible blank line with pre-line CSS")
