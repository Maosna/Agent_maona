"""统一技能系统 - 行为技能 + 工具组合 + 远程市场"""
import json
import shutil
from pathlib import Path
import httpx

BASE_DIR = Path(__file__).resolve().parent.parent / "data"
SKILLS_DIR = BASE_DIR / "skills"
MARKET_FILE = BASE_DIR / "market" / "index.json"  # 本地市场索引文件

# 远程市场渠道配置
MARKET_SOURCES = [
    MARKET_FILE,  # 本地内置市场
    # 可添加远程 URL:
    # "https://raw.githubusercontent.com/xxx/maona-skills/main/index.json",
]


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---"):
        return {}, content
    parts = content[3:].split("---", 1)
    if len(parts) < 2:
        return {}, content
    try:
        import yaml
        meta = yaml.safe_load(parts[0]) or {}
    except:
        meta = {}
    return meta, parts[1].strip()


def scan_skills() -> list[dict]:
    """扫描已安装技能"""
    if not SKILLS_DIR.exists():
        return []
    state = {}
    state_file = SKILLS_DIR / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except:
            pass
    skills = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        # 优先读 info.json，否则读 SKILL.md
        info = d / "info.json"
        if info.exists():
            try:
                meta = json.loads(info.read_text(encoding="utf-8"))
            except:
                continue
            sid = d.name
            skills.append({
                "id": sid,
                "name": meta.get("name", sid),
                "description": meta.get("description", ""),
                "description_en": meta.get("description_en", ""),
                "icon": meta.get("icon", "🎯"),
                "category": meta.get("category", "通用"),
                "author": meta.get("author", ""),
                "type": meta.get("type", "behavior"),
                "tools": meta.get("tools", []),
                "tags": meta.get("tags", []),
                "suite": meta.get("suite", ""),
                "body": meta.get("body", ""),
                "enabled": state.get(sid, {}).get("enabled", False),
            })
            continue
        # Fallback to SKILL.md format
        md = d / "SKILL.md"
        if md.exists():
            content = md.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(content)
            sid = d.name
            skills.append({
                "id": sid,
                "name": meta.get("name", sid),
                "description": meta.get("description", ""),
                "description_en": meta.get("description_en", meta.get("description", "")),
                "icon": meta.get("icon", "🎯"),
                "category": meta.get("category", "通用"),
                "author": "",
                "type": "behavior",
                "tools": [],
                "tags": meta.get("tags", []),
                "suite": meta.get("suite", ""),
                "body": body,
                "enabled": state.get(sid, {}).get("enabled", False),
            })
    return skills


def get_market_skills() -> list[dict]:
    """获取技能市场（本地 + 远程）"""
    all_skills = []
    seen = set()
    for source in MARKET_SOURCES:
        try:
            if isinstance(source, Path) and source.exists():
                data = json.loads(source.read_text(encoding="utf-8"))
            elif isinstance(source, str) and source.startswith("http"):
                import asyncio, concurrent.futures
                async def _fetch():
                    async with httpx.AsyncClient(timeout=10) as c:
                        r = await c.get(source)
                        return r.json()
                try:
                    # 在独立线程中运行 asyncio.run()，避免 nest_asyncio 全局破坏事件循环
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        data = pool.submit(lambda: asyncio.run(_fetch())).result(timeout=15)
                except Exception:
                    continue
            else:
                continue
            for s in data:
                sid = s.get("id")
                if sid and sid not in seen:
                    seen.add(sid)
                    all_skills.append(s)
        except Exception:
            continue
    # 标记已安装
    installed = {s["id"] for s in scan_skills()}
    for s in all_skills:
        s["installed"] = s["id"] in installed
    return all_skills


def install_skill(skill_id: str) -> bool:
    """从市场安装技能"""
    market = get_market_skills() if MARKET_FILE.exists() else []
    meta = next((m for m in market if m["id"] == skill_id), None)
    if not meta:
        return False
    skill_dir = SKILLS_DIR / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    install_data = {k: v for k, v in meta.items() if k != "installed"}
    (skill_dir / "info.json").write_text(
        json.dumps(install_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def uninstall_skill(skill_id: str) -> bool:
    """卸载技能（同时清理 state.json）"""
    skill_dir = SKILLS_DIR / skill_id
    if not skill_dir.exists():
        return False
    shutil.rmtree(str(skill_dir))
    # 清理 state.json 中的残留
    state_file = SKILLS_DIR / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            if skill_id in state:
                del state[skill_id]
                state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except:
            pass
    return True


def toggle_skill(skill_id: str, enabled: bool) -> bool:
    # 验证技能目录存在
    skill_dir = SKILLS_DIR / skill_id
    if not skill_dir.exists() or not (skill_dir / "info.json").exists():
        return False  # 不允许为非存在技能设置状态
    state_file = SKILLS_DIR / "state.json"
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except:
            pass
    state[skill_id] = {"enabled": enabled}
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def toggle_suite(suite_name: str, enabled: bool) -> int:
    """批量切换套件下所有技能的启用状态，返回切换数量"""
    skills = scan_skills()
    suite_skills = [s for s in skills if s.get("suite") == suite_name]
    for s in suite_skills:
        toggle_skill(s["id"], enabled)
    return len(suite_skills)


def get_enabled_prompts() -> str:
    """返回已启用技能的摘要列表（仅名称+一句话描述，用于 system prompt）"""
    skills = scan_skills()
    enabled = [s for s in skills if s.get("enabled")]
    if not enabled:
        return ""
    lines = [f"已启用 {len(enabled)} 个技能。使用 load_skill(\"技能ID\") 加载具体指令："]
    for s in enabled:
        lines.append(f"- {s['id']}: {s['description'][:80]}")
    return "\n".join(lines)


def list_skills() -> list[dict]:
    """列出所有已安装技能（供 API 使用）"""
    return scan_skills()


def get_active_skills() -> list[str]:
    """返回当前激活的技能 ID 列表"""
    state_file = SKILLS_DIR / "state.json"
    if not state_file.exists():
        return []
    try:
        state = json.loads(state_file.read_text(encoding='utf-8'))
        return [k for k, v in state.items() if v.get("enabled")]
    except:
        return []


def set_active_skills(skill_ids: list[str]) -> None:
    """批量设置激活的技能 ID"""
    skills = scan_skills()
    state = {}
    for s in skills:
        state[s["id"]] = {"enabled": s["id"] in skill_ids}
    state_file = SKILLS_DIR / "state.json"
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def get_skill_body(skill_id: str) -> str | None:
    """按需加载指定技能的完整 body（渐近式披露）"""
    skills = scan_skills()
    for s in skills:
        if s["id"] == skill_id:
            if not s.get("enabled"):
                return f"技能 {skill_id} 未启用。请先在技能中心启用后再加载。"
            body = s.get("body", "")
            if not body:
                return f"技能 {skill_id} 没有操作指令。"
            name = s["name"]
            desc = s.get("description", "")
            return _format_skill_overview(skill_id, name, desc, body)
    avail = [s["id"] for s in skills if s.get("enabled")]
    return f"技能 {skill_id} 不存在。当前可用的技能：{', '.join(avail) if avail else '(无)'}"


def _format_skill_overview(skill_id: str, name: str, description: str, body: str) -> str:
    """渐近式披露：只返回概览（步骤标题列表），Agent 需要具体步骤时用 read_skill_step"""
    import re
    # 提取步骤标题（## 开头的行）
    steps = re.findall(r'^###?\s+(.+)$', body, re.MULTILINE)
    # 提取关键信息（参数约定、工作区结构等）—— 取前 800 字符
    preview = body[:800]
    if len(body) > 800:
        # 截断到完整段落
        last_break = max(preview.rfind("\n\n"), preview.rfind("\n"))
        if last_break > 400:
            preview = preview[:last_break]

    lines = [
        f"## 技能：{name}",
        f"描述：{description}" if description else "",
        f"",
        f"核心约定：",
        f"{preview}",
        f"",
        f"## 执行步骤（{len(steps)} 步）",
    ]
    if steps:
        for i, st in enumerate(steps):
            lines.append(f"  {i + 1}. {st.strip()}")
    else:
        # 无标题结构时，手动分段
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        for i, p in enumerate(paragraphs[:10]):
            title = p.split("\n")[0][:80]
            lines.append(f"  {i + 1}. {title}")

    lines.append("")
    lines.append(f"---")
    lines.append(f"⚠️ 以上是技能概览。执行时用 read_skill_step(\"{skill_id}\", 步骤号或标题) 获取具体指令。")
    lines.append(f"   例如：read_skill_step(\"{skill_id}\", 1) 或 read_skill_step(\"{skill_id}\", \"步骤 4 的标题\")")
    lines.append(f"   技能全文 {len(body)} 字符，不要一次性加载——按需逐步读取，读完执行完就进入下一步。")

    return "\n".join(lines)


def read_skill_step(skill_id: str, step_ref: str | int) -> str:
    """按需读取技能的特定步骤/章节"""
    skills = scan_skills()
    for s in skills:
        if s["id"] == skill_id:
            body = s.get("body", "")
            if not body:
                return f"技能 {skill_id} 没有内容"

            import re
            sections = re.split(r'(?=^###?\s)', body, flags=re.MULTILINE)

            # 按序号匹配（跳过开头的 H1 标题段，从第一个 ## 段开始编号为步骤 1）
            if isinstance(step_ref, int) or (isinstance(step_ref, str) and step_ref.isdigit()):
                idx = int(step_ref) - 1
                # 判断第一个 section 是否是 H1 概览（不以 ## 开头）→ 跳过
                effective_sections = sections
                if sections and not sections[0].strip().startswith("##"):
                    effective_sections = sections[1:]
                if 0 <= idx < len(effective_sections):
                    return f"## 技能：{s['name']} > 步骤 {idx + 1}\n{effective_sections[idx].strip()}"
                return f"步骤 {step_ref} 不存在。技能 {skill_id} 共 {len(effective_sections)} 个步骤。"

            # 按标题关键词匹配
            ref_lower = str(step_ref).lower()
            for i, sec in enumerate(sections):
                if ref_lower in sec.lower()[:120]:
                    return f"## 技能：{s['name']} > {step_ref}\n{sec.strip()}"

            # 模糊匹配
            best_match = None
            best_score = 0
            for i, sec in enumerate(sections):
                title = sec.split("\n")[0].lower()
                score = sum(1 for w in ref_lower.split() if w in title)
                if score > best_score:
                    best_score = score
                    best_match = (i, sec)
            if best_match and best_score > 0:
                return f"## 技能：{s['name']} > {step_ref}\n{best_match[1].strip()}"

            return f"未找到与 «{step_ref}» 匹配的步骤。可用步骤：\n" + "\n".join(
                f"  {i + 1}. {sec.split(chr(10))[0][:80]}" for i, sec in enumerate(sections)
            )
    return f"技能 {skill_id} 未找到"
    # 未匹配，返回可用列表
    avail = [s["id"] for s in skills if s.get("enabled")]
    return f"技能 {skill_id} 不存在。当前可用的技能：{', '.join(avail) if avail else '(无)'}"
