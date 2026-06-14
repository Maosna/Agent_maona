import sys, os, json, re

sys.path.insert(0, r'F:/工具/Agent_maona/backend')

CSS_CONTENT = (
    "* { margin: 0; padding: 0; box-sizing: border-box; }\n"
    "body { font-family: sans-serif; min-height: 100vh; "
    "display: flex; align-items: center; justify-content: center; "
    "background: linear-gradient(135deg, #667eea, #764ba2); }\n"
    ".container { text-align: center; background: white; "
    "padding: 40px 60px; border-radius: 16px; "
    "box-shadow: 0 20px 60px rgba(0,0,0,0.2); }\n"
    "h1 { color: #333; margin-bottom: 12px; }\n"
    "button { background: linear-gradient(135deg, #667eea, #764ba2); "
    "color: white; border: none; padding: 12px 32px; "
    "border-radius: 8px; font-size: 16px; cursor: pointer; }\n"
    "button:hover { transform: scale(1.05); }\n"
    "#msg { margin-top: 16px; font-size: 18px; color: #764ba2; font-weight: bold; }"
)

HTML_CONTENT = (
    '<!DOCTYPE html>\n<html lang="zh">\n<head>\n'
    '<meta charset="UTF-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    '<title>Demo Page</title>\n'
    '<link rel="stylesheet" href="style.css">\n</head>\n<body>\n'
    '<div class="container">\n<h1>Welcome to Maona</h1>\n'
    '<p>Created by AI assistant.</p>\n'
    '<button onclick="showMsg()">Click me</button>\n'
    '<p id="msg"></p>\n</div>\n'
    '<script src="app.js"></script>\n</body>\n</html>'
)

JS_CONTENT = (
    'function showMsg() {\n'
    '  document.getElementById("msg").textContent = "Hello from Maona!";\n'
    '}'
)

README_CONTENT = "# Demo Project\n\nCreated by Maona AI.\n\n## Usage\nOpen index.html in browser."


class SmartMockProvider:

    def __init__(self, workspace=""):
        self.ws = workspace
        self.round = 0
        self.stage = {}

    def _parse(self, msg):
        m = msg.lower().strip()
        # greeting: 以问候开头，或纯问候
        if m in ['你好', 'hello', 'hi', '嗨', 'hey'] or m.startswith(('你好', 'hello', 'hi ', '嗨', 'hey')):
            return 'greeting'
        if any(w in m for w in ['网页', 'html', 'css', 'web', '项目']) and any(w in m for w in ['创建', '写', '做', '生成', 'make', 'create', 'build']):
            return 'create_web'
        if any(w in m for w in ['搜索', 'search', 'find', 'grep']):
            return 'search'
        if any(w in m for w in ['python', '运行', '计算', '执行', 'run', 'code']):
            return 'python'
        if any(w in m for w in ['创建', '写', '新建', 'touch']):
            return 'create'
        if any(w in m for w in ['读', 'read', '查看', 'cat']):
            return 'read'
        return 'chat'

    async def chat_non_stream(self, messages, tools=None, **kw):
        self.round += 1
        last_user = ""
        for m in reversed(messages):
            c = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
            if c and not str(c).startswith("["):
                last_user = str(c)[:300]
                break

        task = self._parse(last_user)
        # 防止重复执行：同任务多轮后自动结束
        task_key = f"{task}_{last_user[:40]}"
        prev = self.stage.get(task_key, 0)
        self.stage[task_key] = prev + 1
        if prev >= 1:
            # 已经执行过一轮，直接完成
            return {"content": "任务处理完成！还有其他需要吗？", "tool_calls": None}

        resp = {"content": "", "tool_calls": None}

        if task == 'greeting':
            resp["content"] = (
                "你好！我是 Maona，你的 AI 桌面助手。有什么可以帮你的吗？\n\n"
                "我可以帮你：\n- 创建和管理文件\n- 编写代码\n"
                "- 搜索文件内容\n- 执行 Python 脚本\n- 网页浏览和搜索\n\n请随时告诉我你的需求！"
            )

        elif task == 'create_web':
            resp["content"] = "好的，我来为你创建网页项目。"
            resp["tool_calls"] = [
                mk_tc("write_file", {"path": f"{self.ws}/index.html", "content": HTML_CONTENT}),
                mk_tc("write_file", {"path": f"{self.ws}/style.css", "content": CSS_CONTENT}),
                mk_tc("write_file", {"path": f"{self.ws}/app.js", "content": JS_CONTENT}),
                mk_tc("write_file", {"path": f"{self.ws}/README.md", "content": README_CONTENT}),
            ]

        elif task == 'create_web' and self.round == 2:
            resp["content"] = "让我验证一下文件。"
            resp["tool_calls"] = [
                mk_tc("list_files", {"path": self.ws}),
                mk_tc("read_file", {"path": f"{self.ws}/index.html"}),
            ]

        elif task == 'create_web':
            resp["content"] = (
                "项目创建完成！包含以下文件：\n\n"
                "- index.html — 主页面\n- style.css — 样式\n"
                "- app.js — 交互逻辑\n- README.md — 说明文档\n\n"
                "用浏览器打开 index.html 即可查看效果。"
            )

        elif task == 'create' and self.round == 1:
            name = "script.py"
            resp["content"] = f"好的，创建 {name}。"
            resp["tool_calls"] = [
                mk_tc("write_file", {"path": f"{self.ws}/{name}", "content": "# Created by Maona\nprint('Hello!')\n"})
            ]

        elif task == 'read' and self.round == 1:
            name = "script.py"
            resp["content"] = f"读取 {name}。"
            resp["tool_calls"] = [mk_tc("read_file", {"path": f"{self.ws}/{name}"})]

        elif task == 'search':
            pattern = "hello"
            m = re.search(r'["\'](.+?)["\']', last_user)
            if m:
                pattern = m.group(1)
            resp["content"] = f"搜索 {pattern}。"
            resp["tool_calls"] = [mk_tc("search_content", {"path": self.ws, "pattern": pattern})]

        elif task == 'python':
            code = "print(sum(range(1, 101)))"
            resp["content"] = "执行 Python 代码。"
            resp["tool_calls"] = [mk_tc("run_python", {"code": code, "timeout": 30})]

        else:
            resp["content"] = "明白了。我可以帮您处理这个。需要创建文件、搜索内容还是运行代码？"

        return resp


def mk_tc(name, args):
    return {
        "type": "function",
        "id": f"call_{name}",
        "function": {"name": name, "arguments": json.dumps(args)}
    }
