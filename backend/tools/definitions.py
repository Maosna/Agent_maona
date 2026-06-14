"""工具定义 - OpenAI Function Calling 格式

每个工具包含 name, description, parameters (JSON Schema)
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取本地文件内容。用于查看代码、配置、数据文件等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入内容到本地文件。会覆盖已有内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文本内容"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出目录中的文件和子目录。当用户询问文件夹内容时，默认使用工作空间路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录的绝对路径，默认为工作空间路径（前端设置中配置）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在终端中执行命令并返回输出。支持 git, npm, python 等。注意：此工具会实际执行系统命令。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "使用搜索引擎搜索互联网信息。返回搜索结果摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "抓取并读取指定 URL 的网页内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要抓取的网页 URL"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_content",
            "description": "在目录下递归搜索包含指定文本的文件，返回匹配行及位置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "要搜索的文本"},
                    "path": {"type": "string", "description": "搜索路径，默认工作空间"},
                    "file_pattern": {"type": "string", "description": "文件名通配符，如 *.py"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "精确替换文件中的文本。old_string 必须唯一出现一次。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件绝对路径"},
                    "old_string": {"type": "string", "description": "要替换的原文本（必须唯一）"},
                    "new_string": {"type": "string", "description": "新文本"}
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "保存一条长期记忆。用于记录重要信息、用户偏好、项目约定等需要在未来对话中回忆的内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要保存的记忆内容"},
                    "category": {"type": "string", "description": "分类标签，如 preference/convention/decision"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "读取长期记忆。可选关键词搜索历史记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，为空则返回全部记忆"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_daily_log",
            "description": "追加一条今天的日志。用于跨对话记忆——下次对话会通过工作日志了解本次做了什么。必须记录：①创建/修改了哪些文件（路径清单）②使用了什么工具/Skill ③遇到了什么错误及如何修复。每完成一项实质性工作（≥3 步操作）就追加一条。只写事实，不写感想。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "日志内容，格式：## [时间] 事项标题\n- 操作：...\n- 文件：...\n- 结果：..."}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_bug_fix",
            "description": "记录一个已验证的错误及其修复方案，供未来同类任务自动参考。每次修完 bug 后调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_pattern": {"type": "string", "description": "错误关键词（如 'TSCN load_steps 不一致'）"},
                    "fix_description": {"type": "string", "description": "修复步骤"},
                    "file_path": {"type": "string", "description": "出错文件路径（可选）"}
                },
                "required": ["error_pattern", "fix_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "查看 git 仓库中的文件变更（vs HEAD）。用于审查代码修改。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "仓库目录或文件路径"},
                    "staged": {"type": "boolean", "description": "是否查看暂存区变更"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "查看 git 仓库的最近提交历史。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "仓库目录或文件路径"},
                    "n": {"type": "integer", "description": "显示的提交数，默认 10"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_read",
            "description": "读取 PDF 文件的文本内容。支持 PyPDF2 和 pdfplumber 两种后端。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "PDF 文件的绝对路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sql_query",
            "description": "对 SQLite 数据库执行 SELECT 查询。仅允许只读操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "SQLite 数据库文件路径"},
                    "query": {"type": "string", "description": "SELECT 查询语句"}
                },
                "required": ["path", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "api_post",
            "description": "发送 HTTP POST 请求到远程 API。带 SSRF 防护。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "请求 URL"},
                    "body": {"type": "string", "description": "请求体（JSON 字符串或普通文本）"},
                    "headers": {"type": "string", "description": "请求头（JSON 格式或行格式 Key: Value）"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_file",
            "description": "下载远程文件到本地。带 SSRF 防护和 1GB 大小限制。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "文件的下载 URL"},
                    "path": {"type": "string", "description": "保存的本地路径"}
                },
                "required": ["url", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "执行 Python 代码片段并返回输出。用于计算、数据处理、快速测试。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python 代码"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_csv",
            "description": "读取 CSV 文件并展示表格预览（前 N 行）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "CSV 文件路径"},
                    "n": {"type": "integer", "description": "显示行数，默认 20"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "获取系统资源信息：CPU 使用率、内存占用、磁盘空间。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "image_info",
            "description": "获取图片文件的尺寸、格式、拍摄时间等信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "图片文件路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "截取当前主屏幕并保存为 PNG 文件。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "用系统默认浏览器打开指定 URL。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要打开的网页 URL"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "install_pip",
            "description": "使用 pip 安装 Python 包。用于缺少依赖时自动安装。",
            "parameters": {
                "type": "object",
                "properties": {
                    "package": {"type": "string", "description": "要安装的包名"}
                },
                "required": ["package"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compress_image",
            "description": "压缩或调整图片大小。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "图片文件路径"},
                    "width": {"type": "integer", "description": "目标宽度（像素）"},
                    "quality": {"type": "integer", "description": "压缩质量 1-100，默认 85"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard",
            "description": "读取或写入系统剪贴板。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "read 读取 / write 写入"},
                    "text": {"type": "string", "description": "写入时的文本内容"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "zip_archive",
            "description": "创建或解压 ZIP 压缩包。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "create 创建 / extract 解压"},
                    "path": {"type": "string", "description": "源路径"},
                    "dest": {"type": "string", "description": "目标路径"}
                },
                "required": ["action", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "notify",
            "description": "发送桌面通知。用于长任务完成时提醒。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "通知标题，默认 Maona"},
                    "message": {"type": "string", "description": "通知内容"}
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "encode_decode",
            "description": "编解码工具：base64/url/hex/md5/sha256。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "base64_encode/decode, url_encode/decode, md5, sha256, hex"},
                    "text": {"type": "string", "description": "要处理的文本"}
                },
                "required": ["action", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "重命名或移动文件/目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "原路径"},
                    "new_name": {"type": "string", "description": "新名称或新路径"}
                },
                "required": ["path", "new_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "安全删除文件（移至回收站）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的文件路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "text_to_speech",
            "description": "将文字转换为语音朗读。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要朗读的文字"},
                    "lang": {"type": "string", "description": "语言代码，默认 zh"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "count_tokens",
            "description": "估算文本的 token 消耗数量。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要估算的文本"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "html_preview",
            "description": "【预览 HTML】将 HTML 代码保存并在应用内打开预览。当用户说「打开这个 HTML」「看看网页效果」「预览页面」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {"type": "string", "description": "HTML 代码"},
                    "path": {"type": "string", "description": "保存路径"}
                },
                "required": ["html"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cost_summary",
            "description": "查看当前会话的 token 消耗和费用统计。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_docx",
            "description": "读取 Word (.docx) 文件文本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "docx 文件路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_pptx",
            "description": "读取 PowerPoint (.pptx) 幻灯片。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "pptx 文件路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_xlsx",
            "description": "读取 Excel (.xlsx/.xls) 表格。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "xlsx 文件路径"},
                    "sheet": {"type": "string", "description": "工作表名称"},
                    "n": {"type": "integer", "description": "显示行数，默认 20"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "加载已启用技能的完整操作指令。当某个已启用技能的操作指南未在上下文中时，调用此工具获取其详细说明。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "要加载的技能ID（从系统提示中的可用技能列表选取）"
                    }
                },
                "required": ["skill_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_mode",
            "description": "切换当前工作模式。craft=直接执行, plan=先出方案等确认, ask=只读分析。复杂修改类任务先切plan出方案；简单查询切ask。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["craft", "plan", "ask"],
                        "description": "目标模式"
                    },
                    "reason": {
                        "type": "string",
                        "description": "切换原因（简短说明）"
                    }
                },
                "required": ["mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_create",
            "description": "创建任务跟踪项。当面对复杂任务（3步以上）时，先创建任务列表跟踪进度，防止遗漏。返回任务ID。",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "任务标题"},
                    "description": {"type": "string", "description": "详细描述"},
                    "steps": {"type": "array", "items": {"type": "string"}, "description": "步骤列表"}
                },
                "required": ["subject"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_update",
            "description": "更新任务状态。完成一步就标记一步。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "failed"], "description": "新状态"},
                    "step": {"type": "integer", "description": "当前完成的步骤编号（从1开始）"},
                    "note": {"type": "string", "description": "备注"}
                },
                "required": ["task_id", "status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "列出当前会话的所有任务及进度。查看哪些已完成、哪些待做。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restore_backup",
            "description": "【恢复文件备份】恢复到修改前的上一个备份。当用户说「回滚」「还原」「撤销修改」「恢复到之前版本」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要恢复的文件路径"},
                    "list_only": {"type": "boolean", "description": "仅列出可用备份，不执行恢复"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_snapshot",
            "description": "【保存 Git 快照】自动 add+commit 所有变更。当用户说「保存快照」「提交一下」「存个档」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "提交信息"},
                    "path": {"type": "string", "description": "工作目录，默认当前工作空间"}
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "project_index",
            "description": "【扫描项目结构】生成函数签名/文件树/依赖关系概览。当用户说「看看这个项目」「项目结构是怎样的」「有哪些模块」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "项目根目录"},
                    "refresh": {"type": "boolean", "description": "强制刷新索引"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "live_preview",
            "description": "【实时预览】标记文件为实时预览模式。改这个文件时浏览器自动刷新。当用户说「实时预览」「边改边看」「热更新」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要实时预览的文件路径（HTML/JS/CSS）"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sub_task",
            "description": "【并行子任务】启动独立子 Agent 并行执行多个任务。当用户说「同时做」「并行处理」「分几个任务一起跑」时调用。支持 explore/plan/research/implement 四种模式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "子任务描述"},
                    "context": {"type": "string", "description": "参考上下文（项目信息/文件路径/关键代码片段）"},
                    "mode": {"type": "string", "description": "子 Agent 模式：explore/plan/research/implement。默认根据 prompt 自动推断"}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "code_search",
            "description": "【全文搜索代码】智能搜索项目代码，支持多关键词模糊匹配。当用户说「搜索 XX 代码」「项目里哪里用了 XX」时调用。返回文件和行号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索内容，支持多词空格分隔"},
                    "path": {"type": "string", "description": "搜索目录，默认当前工作空间"},
                    "max_results": {"type": "integer", "description": "最大结果数，默认15"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_create",
            "description": "创建新技能文件。当发现反复使用的操作模式时，把它封装成技能。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能ID（英文，用-分隔），例如 fix-react-hooks"},
                    "display": {"type": "string", "description": "显示名称（中文）"},
                    "description": {"type": "string", "description": "一句话描述"},
                    "body": {"type": "string", "description": "技能内容（Markdown）"}
                },
                "required": ["name", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_update",
            "description": "修改已有技能的内容。发现技能有缺陷时改进它。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能ID"},
                    "body": {"type": "string", "description": "新的完整技能内容"}
                },
                "required": ["name", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_delete",
            "description": "删除不再需要的技能。仅当技能确实无用且用户默许时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "要删除的技能ID"}
                },
                "required": ["name"]
            }
        }
    },
    # ===== 技能发现 =====
    {
        "type": "function",
        "function": {
            "name": "find_skills",
            "description": "搜索可用技能（已安装 + 可安装市场）。当遇到不熟悉的任务、需要特定领域能力、或现有工具无法满足需求时，必须先调用此工具搜索是否有匹配的技能。返回匹配的已安装技能（含启用状态）和可安装的市场技能列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，例如 'pdf' 'excel' 'browser' 'godot'"},
                    "install": {"type": "boolean", "description": "是否自动安装搜索到的市场技能，默认 false"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rag_build",
            "description": "【构建代码语义索引】扫描整个项目分块+向量化，存到 .maona/rag_index/。当用户说「建索引」「索引项目」「分析代码库」时调用。之后用 rag_search 语义搜索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "项目根目录"},
                    "force": {"type": "boolean", "description": "强制重建索引"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "【语义搜索代码】用自然语言搜索代码库。当用户说「找到处理 XX 的代码」「搜索 XX 逻辑」「有没有 XX 相关代码」时调用。即使没说准确关键词也能找到对应的 try/catch 块。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "自然语言或代码关键词"},
                    "path": {"type": "string", "description": "项目根目录"},
                    "top_k": {"type": "integer", "description": "返回结果数，默认8"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_test",
            "description": "【运行项目测试】执行测试套件并返回通过/失败数。当用户说「跑一下测试」「测试看看」「测试通过了吗」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "项目目录"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_check",
            "description": "【代码质量检查】检查代码语法/类型/风格问题。当用户说「检查代码」「lint 一下」「有没有语法错误」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "项目目录"},
                    "file": {"type": "string", "description": "只检查指定文件"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "profile",
            "description": "【性能分析】测试命令执行时间和资源消耗。当用户说「测一下性能」「哪里慢」「分析瓶颈」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要测量的命令，如 python script.py"},
                    "path": {"type": "string", "description": "工作目录"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kb_create",
            "description": "【创建知识库】把文档/网页内容存成可搜索知识库。当用户说「建一个知识库」「把资料存起来以后搜」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "知识库名称"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kb_add_url",
            "description": "【添加网页到知识库】抓取网页并加入知识库索引。当用户说「把这个网页存到知识库」「收藏这个页面」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kb": {"type": "string", "description": "知识库名称"},
                    "url": {"type": "string", "description": "网页 URL"}
                },
                "required": ["kb", "url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kb_add",
            "description": "【添加文本到知识库】把文章/文档/代码片段存入知识库。当用户说「记下这段内容」「保存到知识库」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kb": {"type": "string", "description": "知识库名称"},
                    "title": {"type": "string", "description": "文档标题"},
                    "content": {"type": "string", "description": "文档内容"}
                },
                "required": ["kb", "title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kb_search",
            "description": "【搜索知识库】语义搜索已存储的文档。当用户说「知识库里有没有关于 XX 的」「查一下之前存的资料」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kb": {"type": "string", "description": "知识库名称"},
                    "query": {"type": "string", "description": "搜索内容"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"}
                },
                "required": ["kb", "query"]
            }
        }
    },
    # ===== 浏览器自动化 =====
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "【浏览器自动化】用 Playwright 打开网页并提取文本。当用户说「打开 XX 网站」「帮我看看这个网页」「浏览 XX 页面」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "目标 URL"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "【浏览器截图】截取当前浏览器页面的完整截图。当用户说「截个图」「截屏」「看看页面长什么样」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "可选：先导航到此 URL 再截图"},
                    "selector": {"type": "string", "description": "可选：只截取特定元素"},
                    "full_page": {"type": "boolean", "description": "是否截取整页"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "【浏览器点击】点击页面上的元素（按钮/链接等）。当用户说「点 XX 按钮」「点击那个链接」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS 选择器"}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "【浏览器填表】填写输入框。当用户说「在搜索框输入 XX」「填写表单」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS 选择器"},
                    "value": {"type": "string", "description": "要填入的值"}
                },
                "required": ["selector", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract",
            "description": "【浏览器提取】提取页面指定元素的内容。当用户说「提取页面内容」「抓取 XX 信息」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS 选择器，默认 body"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait",
            "description": "【浏览器等待】等待指定毫秒数。用于页面加载完毕后等一会儿再操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ms": {"type": "integer", "description": "等待毫秒数，默认 1000"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "【关闭浏览器】关闭浏览器实例。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    # ===== LSP 代码智能 =====
    {
        "type": "function",
        "function": {
            "name": "lsp_diagnose",
            "description": "检查 Python 文件语法和类型错误",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Python 文件路径"}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_references",
            "description": "搜索代码中的符号引用",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "基准文件路径（决定搜索范围）"},
                    "symbol": {"type": "string", "description": "要搜索的符号名称"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_outline",
            "description": "提取 Python 文件的结构大纲（函数/类定义）",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Python 文件路径"}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_hover",
            "description": "查看文件指定行的上下文（前后各 3 行）",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "文件路径"},
                    "line": {"type": "integer", "description": "行号（从 1 开始）"}
                },
                "required": ["filepath", "line"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_format",
            "description": "检查代码格式（使用 black）",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Python 文件路径"}
                },
                "required": ["filepath"]
            }
        }
    },
    # ===== 部署 =====
    {
        "type": "function",
        "function": {
            "name": "deploy_preview",
            "description": "【本地预览网站】启动 HTTP 服务器预览静态网站。当用户说「预览一下」「看看效果」「本地预览」「打开这个页面」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "站点目录路径"},
                    "port": {"type": "integer", "description": "端口，默认 8080"}
                },
                "required": ["directory"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_package",
            "description": "【打包项目】将目录打包为 ZIP 文件。当用户说「打包」「压缩成 zip」「导出项目」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "要打包的目录"},
                    "output": {"type": "string", "description": "输出 ZIP 路径，默认同级目录"}
                },
                "required": ["directory"]
            }
        }
    },
    # ===== 创意 + 运维工具 =====
    {
        "type": "function",
        "function": {
            "name": "image_generate",
            "description": "【AI 生图】用 AI 生成图片。当用户说「生成一张图」「画个 XX」「AI 画图」时调用。需先配置图片 API。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图片描述提示词"},
                    "size": {"type": "string", "description": "尺寸，如 1024x1024"}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preview_html",
            "description": "在应用内预览 HTML 内容或文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "HTML 代码内容"},
                    "filepath": {"type": "string", "description": "或提供 HTML 文件路径"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_auto_save",
            "description": "【保存为技能】完成任务后将当前工作流保存为可复用的技能。当用户说「记住这个流程」「保存为技能」「下次还要这样」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                    "prompt_template": {"type": "string", "description": "技能执行指令模板"},
                    "trigger": {"type": "string", "description": "触发条件说明"}
                },
                "required": ["name", "prompt_template"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_task",
            "description": "【创建定时任务】设定在指定时间执行的操作。当用户说「定时」「每天/每周 XX 点」「设置提醒」「自动执行」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "interval_minutes": {"type": "integer", "description": "间隔分钟数"},
                    "description": {"type": "string", "description": "任务描述"}
                },
                "required": ["command", "interval_minutes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled_tasks",
            "description": "列出所有定时任务",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled_task",
            "description": "取消定时任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID"}
                },
                "required": ["task_id"]
            }
        }
    },
    # ===== Godot 项目操作 =====
    {
        "type": "function",
        "function": {
            "name": "godot_setup",
            "description": "【已弃用】请在涉及 Godot 项目时一律优先使用 load_skill(\"godot-dev\") 再按 Skill 流程操作。本工具仅用于极简测试（创建单一 Node2D 项目），不具备编辑器下载、多模板、active-game.json 等完整功能，直接使用会导致项目结构与后续 Skill 流程不兼容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_dir": {"type": "string", "description": "游戏项目目录路径"}
                },
                "required": ["game_dir"]
            }
        }
    },
    # ===== Godot 项目完整性检查 =====
    {
        "type": "function",
        "function": {
            "name": "check_godot_project",
            "description": "【检查 Godot 项目】检查 Godot 项目完整性（project.godot/TSCN/脚本引用/Autoload/目录结构）。当用户说「检查 Godot 项目」「验证项目结构」「项目有没有问题」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "游戏项目目录路径（含 project.godot 的那个目录）"}
                },
                "required": ["project_dir"]
            }
        }
    },
    # ===== GDScript 验证 =====
    {
        "type": "function",
        "function": {
            "name": "validate_gdscript",
            "description": "【检查 GDScript 代码】验证 GDScript 语法/类型/跨文件一致性/TSCN 格式。不用打开 Godot 编辑器也能检查。当用户说「检查 GDScript」「验证脚本」「语法有没有错」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Godot 项目根目录路径（含 project.godot）"},
                    "skip_addons": {"type": "boolean", "description": "是否跳过 addons/ 目录，默认 true"}
                },
                "required": ["project_dir"]
            }
        }
    },
    # ===== 环境缓存 =====
    {
        "type": "function",
        "function": {
            "name": "cache_env",
            "description": "保存环境探测结果到会话缓存，避免后续轮次重复探测。探测到环境状态后调用此工具，后续轮次会自动注入缓存结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "has_project": {"type": "boolean", "description": "工作空间是否有 Godot 项目（project.godot）"},
                    "has_editor": {"type": "boolean", "description": "工作空间是否有 Godot 编辑器"},
                    "editor_listening": {"type": "boolean", "description": "GodotMCP 端口 9080 是否在监听"},
                    "game_dir": {"type": "string", "description": "当前游戏项目目录路径"},
                    "active_game": {"type": "string", "description": "active-game.json 中记录的项目名"}
                },
                "required": []
            }
        }
    },
    # ===== 对话历史搜索 =====
    {
        "type": "function",
        "function": {
            "name": "search_conversations",
            "description": "搜索所有历史对话消息（FTS5 全文搜索 + 自动 LIKE 回退）。当需要回忆之前聊过什么、用户提到过什么偏好、做过什么决策时调用此工具。返回匹配的对话片段及所属对话标题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，支持中文和英文"},
                    "limit": {"type": "integer", "description": "返回结果数量，默认 10"}
                },
                "required": ["query"]
            }
        }
    },
    # ===== ComfyUI 节点开发 =====
    {
        "type": "function",
        "function": {
            "name": "comfy_cli",
            "description": "【ComfyUI 节点开发全套工具】当用户要「创建/搭建/做 ComfyUI 节点」「新建自定义节点项目」「安装/更新 ComfyUI 插件」「发布节点到 Registry」「启动 ComfyUI」「下载 ComfyUI 模型」「管理 ComfyUI 环境」时使用。底层调用 comfy-cli 命令行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "主命令: scaffold(创建节点项目), init(初始化已有目录), install(安装节点/插件), update(更新), publish(发布到Registry), validate(验证包规范), pack(打包zip), launch(启动ComfyUI), run(运行工作流), model(管理模型), install-ui(安装ComfyUI本体)",
                        "enum": ["scaffold", "init", "install", "update", "publish", "validate", "pack", "launch", "run", "model", "install-ui"]
                    },
                    "subcommand": {
                        "type": "string",
                        "description": "子命令（如 node、model 等），默认: node"
                    },
                    "args": {
                        "type": "string",
                        "description": "额外参数，空格分隔（如节点名、项目名等）"
                    },
                    "workspace": {
                        "type": "string",
                        "description": "ComfyUI 目录路径（可选，默认自动检测）"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfy_node_scaffold",
            "description": "【创建 ComfyUI 自定义节点项目】当用户说「帮我做一个 ComfyUI 节点」「创建节点项目」「写个 ComfyUI 插件」「搭节点骨架」时调用。自动生成完整项目目录、__init__.py（含 NODE_CLASS_MAPPINGS 注册）、nodes.py（示例节点）、web/js/（前端扩展）、pyproject.toml（发布配置）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "节点项目名称（英文，如 MyImageProcessor）"
                    },
                    "author": {
                        "type": "string",
                        "description": "作者名"
                    },
                    "description": {
                        "type": "string",
                        "description": "项目简短描述（中文）"
                    },
                    "workspace": {
                        "type": "string",
                        "description": "ComfyUI 目录的 custom_nodes 路径"
                    }
                },
                "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfy_node_install",
            "description": "【安装 ComfyUI 插件/节点】当用户说「安装 XX 节点」「给我装个 ComfyUI 插件」「下载 XX 节点的包」时调用。支持从 ComfyUI Registry 或 GitHub 安装。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {
                        "type": "string",
                        "description": "节点名称（如 ComfyUI-Impact-Pack）或 GitHub 地址"
                    },
                    "workspace": {
                        "type": "string",
                        "description": "ComfyUI 目录路径"
                    }
                },
                "required": ["node_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfy_node_publish",
            "description": "【发布 ComfyUI 节点到 Registry】当用户说「发布这个节点」「上传到 ComfyUI 插件市场」「推送到 Registry」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "ComfyUI 目录路径"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfy_launch",
            "description": "【启动 ComfyUI】当用户说「打开/启动/运行 ComfyUI」时调用。支持后台运行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "background": {
                        "type": "boolean",
                        "description": "是否后台运行，默认 true"
                    },
                    "workspace": {
                        "type": "string",
                        "description": "ComfyUI 目录路径"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "comfy_model_download",
            "description": "【下载 ComfyUI AI 模型】当用户说「下载 XX 模型」「下个 SDXL/Flux 的 checkpoint」「帮我拉个模型到 ComfyUI」时调用。支持 CivitAI、HuggingFace、直链 URL。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_url": {
                        "type": "string",
                        "description": "模型下载 URL（CivitAI / HuggingFace / 直链）"
                    },
                    "workspace": {
                        "type": "string",
                        "description": "ComfyUI 目录路径"
                    }
                },
                "required": ["model_url"]
            }
        }
    },
    # ===== 智能记忆 =====
    {
        "type": "function",
        "function": {
            "name": "remember_workflow",
            "description": "【保存工作流】完成任务后，记住当前成功的工具调用序列。当用户说「记住这个流程」「下次还这样做」「保存工作流」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "场景关键词，逗号分隔（如「数据分析,csv」）"},
                    "steps": {"type": "string", "description": "工具调用步骤JSON，如 [{\"tool\":\"read_csv\",\"params\":{...}}, ...]"}
                },
                "required": ["keywords", "steps"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_workflow",
            "description": "【搜索工作流】根据当前意图查找之前成功的操作模式。当开始复杂任务时自动调用此工具参考经验。",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "description": "用户意图描述（如「数据分析」「网页开发」）"}
                },
                "required": ["intent"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_graph",
            "description": "【知识图谱搜索】在图谱中搜索关联实体。当需要查找「和XX相关的YY」「XX依赖哪些文件」时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "relation": {"type": "string", "description": "关系类型过滤（可选）"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "decompose_task",
            "description": "【任务拆解】将复杂请求拆解为有序子任务列表。当用户说「帮我完整做XX」「分析并实现YY」等复杂任务时，先用此工具规划。",
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {"type": "string", "description": "用户原始请求"}
                },
                "required": ["request"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_checkpoint",
            "description": "【保存检查点】长任务中保存当前进度，中断后可从此恢复。当用户说「保存进度」「备份状态」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "当前进度简述"}
                },
                "required": ["summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_checkpoints",
            "description": "【列出检查点】查看已保存的检查点列表。当用户说「有哪些备份」「恢复之前的进度」时先调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]
