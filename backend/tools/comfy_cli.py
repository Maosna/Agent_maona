"""ComfyUI CLI 工具封装 —— 让 Maona 可以直接调用 comfy-cli 管理 ComfyUI 节点和项目"""

import asyncio
import os
import shutil
from pathlib import Path

# comfy-cli 的可执行文件路径（安装在 Python venv 的 Scripts 目录下）
_COMFY_EXE = None


def _find_comfy_exe() -> str | None:
    """查找 comfy 可执行文件路径"""
    global _COMFY_EXE
    if _COMFY_EXE:
        return _COMFY_EXE

    # 1. 先检查 PATH 中是否有 comfy 命令
    comfy_path = shutil.which("comfy")
    if comfy_path:
        _COMFY_EXE = comfy_path
        return _COMFY_EXE

    # 2. 在工作区 venv 的 Scripts 目录查找
    candidates = [
        Path(os.environ.get("VIRTUAL_ENV", "")) / "Scripts" / "comfy.exe",
        # Managed Python env
        Path("C:/ProgramData/WorkBuddy/chromium-env/1368sba/.workbuddy/binaries/python/envs/default/Scripts/comfy.exe"),
        # 用户级 pip 安装
        Path.home() / "AppData" / "Roaming" / "Python" / "Python313" / "Scripts" / "comfy.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python313" / "Scripts" / "comfy.exe",
    ]
    for p in candidates:
        if p.exists():
            _COMFY_EXE = str(p)
            return _COMFY_EXE

    return None


async def comfy_cli(command: str, subcommand: str = "", args: str = "", workspace: str = "") -> str:
    """调用 comfy-cli 执行命令

    参数:
        command: 主命令 (scaffold, init, install, publish, validate, pack, launch, run, model 等)
        subcommand: 子命令 (如 node 的 install/update/publish)
        args: 额外参数，空格分隔的字符串
        workspace: ComfyUI 工作空间路径，可选
    
    返回:
        comfy-cli 的输出结果
    """
    exe = _find_comfy_exe()
    if not exe:
        return "❌ 未找到 comfy-cli。请先运行: pip install comfy-cli"

    # 构建命令
    cmd_parts = [exe]
    if workspace:
        cmd_parts.extend(["--workspace", workspace])
    
    # --skip-prompt 必须在子命令之前
    cmd_parts.append("--skip-prompt")
    
    if subcommand:
        cmd_parts.append(subcommand)
    
    cmd_parts.append(command)
    
    if args:
        # 分割 args 字符串为参数列表
        cmd_parts.extend(args.split())
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=120
        )
        
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        
        result_parts = []
        if stdout_text:
            result_parts.append(stdout_text)
        if stderr_text:
            result_parts.append(f"[stderr]\n{stderr_text}")
        
        rc = proc.returncode
        status = "✅" if rc == 0 else f"❌ (exit code: {rc})"
        
        output = "\n".join(result_parts) if result_parts else "(无输出)"
        return f"{status}\n命令: comfy {' '.join(cmd_parts[1:])}\n\n{output}"
    
    except asyncio.TimeoutError:
        return "❌ 命令执行超时（超过 120 秒）"
    except FileNotFoundError:
        return f"❌ 找不到 comfy 可执行文件: {exe}"
    except Exception as e:
        return f"❌ 执行出错: {str(e)}"


# ===== 常用操作的便捷封装 =====

async def comfy_node_scaffold(project_name: str, workspace: str = "", author: str = "", description: str = "") -> str:
    """创建新的 ComfyUI 自定义节点项目骨架"""
    extra = ""
    if author:
        extra += f" --full-name '{author}'"
    if description:
        extra += f" --project-short-description '{description}'"
    
    # scaffold 会交互式提问，用 --skip-prompt 和额外参数代替
    return await comfy_cli("scaffold", subcommand="node", args=f"--project-name {project_name} {extra}", workspace=workspace)


async def comfy_node_install(node_name: str, workspace: str = "") -> str:
    """安装自定义节点"""
    return await comfy_cli("install", subcommand="node", args=node_name, workspace=workspace)


async def comfy_node_update(node_name: str = "all", workspace: str = "") -> str:
    """更新自定义节点"""
    return await comfy_cli("update", subcommand="node", args=node_name, workspace=workspace)


async def comfy_node_publish(workspace: str = "") -> str:
    """发布节点到 Registry"""
    return await comfy_cli("publish", subcommand="node", workspace=workspace)


async def comfy_node_validate(workspace: str = "") -> str:
    """验证节点包是否符合发布规范"""
    return await comfy_cli("validate", subcommand="node", workspace=workspace)


async def comfy_node_pack(workspace: str = "") -> str:
    """打包节点为 zip 文件"""
    return await comfy_cli("pack", subcommand="node", workspace=workspace)


async def comfy_launch(workspace: str = "", background: bool = True) -> str:
    """启动 ComfyUI"""
    bg_arg = "--background" if background else ""
    return await comfy_cli("launch", args=bg_arg, workspace=workspace)


async def comfy_model_download(model_url: str, workspace: str = "") -> str:
    """下载模型"""
    return await comfy_cli("model", subcommand="download", args=model_url, workspace=workspace)


async def comfy_install_ui(workspace: str = "") -> str:
    """安装 ComfyUI 本体"""
    return await comfy_cli("install", workspace=workspace)
