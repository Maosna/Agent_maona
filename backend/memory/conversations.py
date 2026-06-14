"""对话历史持久化 - SQLite 存储，按项目隔离"""
import json
import math
import re
import aiosqlite
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Optional

DB_PATH = Path.home() / ".agent_maona" / "conversations.db"


async def _get_db() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """初始化数据库表"""
    db = await _get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT DEFAULT '新对话',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                reasoning_content TEXT,
                tool_calls TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_project
                ON conversations(project_id);
        """)
        await db.commit()
        
        # 迁移：为已有数据库添加 reasoning_content 和 tool_calls 字段
        cursor = await db.execute("PRAGMA table_info(messages)")
        columns = set(r[1] for r in await cursor.fetchall())
        if "reasoning_content" not in columns:
            await db.execute("ALTER TABLE messages ADD COLUMN reasoning_content TEXT")
        if "tool_calls" not in columns:
            await db.execute("ALTER TABLE messages ADD COLUMN tool_calls TEXT")
        # FTS5 全文搜索索引（普通模式，手动同步——不用触发器，避免崩溃）
        try:
            await db.execute("DROP TABLE IF EXISTS messages_fts")
            for t in ("messages_fts_insert", "messages_fts_delete", "messages_fts_update"):
                try: await db.execute(f"DROP TRIGGER IF EXISTS {t}")
                except: pass
            await db.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(content)")
            # 同步已有数据
            await db.execute("INSERT INTO messages_fts(rowid, content) SELECT id, content FROM messages WHERE content IS NOT NULL")
        except Exception:
            pass  # FTS5 可能不支持
        await db.commit()
    finally:
        await db.close()


# ========== 项目 ==========

async def ensure_project(project_id: str, name: str = None):
    """确保项目存在"""
    db = await _get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            (project_id, name or project_id)
        )
        await db.commit()
    finally:
        await db.close()


# ========== 对话 ==========

async def create_conversation(project_id: str, title: str = "新对话") -> str:
    """创建新对话，返回 conversation_id"""
    import uuid
    conv_id = uuid.uuid4().hex[:12]
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO conversations (id, project_id, title) VALUES (?, ?, ?)",
            (conv_id, project_id, title)
        )
        await db.commit()
    finally:
        await db.close()
    return conv_id


async def list_conversations(project_id: str, limit: int = 50) -> list:
    """列出项目的对话列表"""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT id, title, created_at, updated_at FROM conversations "
            "WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
            (project_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_conversation(conversation_id: str) -> Optional[dict]:
    """获取对话及其消息"""
    db = await _get_db()
    try:
        conv = await db.execute_fetchall(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        )
        if not conv:
            return None

        msgs = await db.execute_fetchall(
            "SELECT role, content, reasoning_content, tool_calls FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,)
        )
        messages = []
        import json
        for m in msgs:
            msg_dict = dict(m)
            if msg_dict.get("tool_calls"):
                try:
                    msg_dict["tool_calls"] = json.loads(msg_dict["tool_calls"])
                except: pass
            messages.append(msg_dict)
        return {
            **dict(conv[0]),
            "messages": messages,
        }
    finally:
        await db.close()


async def delete_conversation(conversation_id: str):
    """删除对话"""
    db = await _get_db()
    try:
        # 手动清理 FTS5（无触发器，需手动同步）
        try:
            await db.execute(
                "DELETE FROM messages_fts WHERE rowid IN (SELECT id FROM messages WHERE conversation_id = ?)",
                (conversation_id,))
        except Exception:
            pass
        await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        await db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        await db.commit()
    finally:
        await db.close()


async def update_title(conversation_id: str, title: str):
    """更新对话标题"""
    db = await _get_db()
    try:
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, conversation_id)
        )
        await db.commit()
    finally:
        await db.close()


# ========== 消息 ==========

async def save_message(conversation_id: str, role: str, content: str, reasoning_content: str = None, tool_calls: list = None):
    """保存一条消息"""
    db = await _get_db()
    try:
        import json
        tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
        await db.execute(
            "INSERT INTO messages (conversation_id, role, content, reasoning_content, tool_calls) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, reasoning_content, tool_calls_json)
        )
        # 更新对话的 updated_at
        await db.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,)
        )
        # 自动生成标题（取第一条用户消息的前 20 字）
        await db.execute("""
            UPDATE conversations SET title = (
                SELECT substr(content, 1, 30) || CASE WHEN length(content) > 30 THEN '...' ELSE '' END
                FROM messages
                WHERE conversation_id = conversations.id AND role = 'user'
                ORDER BY id LIMIT 1
            ) WHERE id = ? AND title = '新对话'
        """, (conversation_id,))
        await db.commit()
        # 手动同步 FTS5（不用触发器，避免崩溃影响删除操作）
        if content:
            try:
                cursor = await db.execute("SELECT last_insert_rowid()")
                row = await cursor.fetchone()
                if row and row[0]:
                    await db.execute(
                        "INSERT OR REPLACE INTO messages_fts(rowid, content) VALUES (?, ?)",
                        (row[0], content)
                    )
            except Exception:
                pass
    finally:
        await db.close()


async def search_conversation_messages(project_id: str, query: str, limit: int = 20) -> list:
    """搜索项目下的对话消息（FTS5 全文搜索 + TF-IDF 语义回退）"""
    if not query.strip():
        return []
    db = await _get_db()
    try:
        # 尝试 FTS5 全文搜索（更快更准）
        results = []
        try:
            cursor = await db.execute("""
                SELECT c.id as conv_id, c.title, m.role, substr(m.content, 1, 300) as preview,
                       m.created_at, snippet(messages_fts, 2, '<mark>', '</mark>', '...', 32) as snippet
                FROM messages_fts fts
                JOIN messages m ON fts.rowid = m.rowid
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.project_id = ? AND messages_fts MATCH ?
                ORDER BY rank LIMIT ?
            """, (project_id, _fts_escape(query), limit))
            rows = await cursor.fetchall()
            if rows:
                results = [dict(r) for r in rows]
        except Exception:
            pass  # FTS 表可能不存在

        # TF-IDF 语义增强：FTS5 结果少时补充语义搜索
        if len(results) < 3:
            sem = await search_conversations_semantic(project_id, query, limit)
            seen = {r.get("conv_id","")+r.get("preview","")[:40] for r in results}
            for s in sem:
                k = s.get("conv_id","")+s.get("preview","")[:40]
                if k not in seen:
                    results.append(s)
                    seen.add(k)
                if len(results) >= limit:
                    break
        if results:
            return results[:limit]

        # LIKE 最低回退
        import re
        safe_query = re.sub(r"[%_]", r"[\g<0>]", query)
        cursor = await db.execute("""
            SELECT c.id as conv_id, c.title, m.role, substr(m.content, 1, 200) as preview, m.created_at
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.project_id = ? AND m.content LIKE ?
            ORDER BY m.created_at DESC LIMIT ?
        """, (project_id, f"%{safe_query}%", limit))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()

def _fts_escape(query: str) -> str:
    """转义 FTS5 查询中的特殊字符"""
    cleaned = re.sub(r'[^\w\u4e00-\u9fff\s]', ' ', query)
    terms = cleaned.split()
    return ' OR '.join(terms) if terms else query


# ========== TF-IDF 语义搜索 ==========

def _tokenize(text: str) -> list[str]:
    """分词：CamelCase拆分 + 中文单字/二元组 + 去停用词"""
    text = text.lower()
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'[_\-/.]', ' ', text)
    en_tokens = re.findall(r'[a-z0-9]+', text)
    cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
    stops = {'the','a','an','is','are','was','were','be','been','being',
             'have','has','had','do','does','did','will','would','could',
             'should','may','might','can','shall','to','of','in','for',
             'on','with','at','by','from','as','into','through','during',
             'and','but','or','not','no','if','then','else','this','that',
             'it','its','we','you','they','he','she','his','her','their'}
    cn_stops = {'的','了','在','是','我','有','和','就','不','人','都','一',
                '个','上','也','很','到','说','要','去','你','会','着','没有'}
    result = [t for t in en_tokens if t not in stops and len(t) > 1 and not t.isdigit()]
    for i in range(len(cn_chars)):
        if cn_chars[i] not in cn_stops:
            result.append(cn_chars[i])
        if i < len(cn_chars) - 1:
            result.append(cn_chars[i] + cn_chars[i+1])
    return result


def _tfidf_score(q: list[str], d: list[str], all_docs: list[list[str]]) -> float:
    """计算 TF-IDF 余弦相似度"""
    if not q or not d:
        return 0.0
    N = len(all_docs) + 1
    qf, df = Counter(q), Counter(d)
    score = norm_q = norm_d = 0.0
    for term in set(qf) | set(df):
        idf = math.log((N + 1) / (sum(1 for x in all_docs if term in x) + 1))
        qw = qf.get(term, 0) * idf
        dw = df.get(term, 0) * idf
        score += qw * dw
        norm_q += qw ** 2
        norm_d += dw ** 2
    if norm_q == 0 or norm_d == 0:
        return 0.0
    return score / (math.sqrt(norm_q) * math.sqrt(norm_d))


async def search_conversations_semantic(project_id: str, query: str, limit: int = 10) -> list:
    """TF-IDF 语义搜索历史对话消息，不依赖 FTS5"""
    if not query.strip():
        return []
    db = await _get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT m.id as msg_id, c.id as conv_id, c.title, m.role, "
            "substr(m.content, 1, 500) as content, m.created_at "
            "FROM messages m JOIN conversations c ON m.conversation_id = c.id "
            "WHERE c.project_id = ? AND m.content IS NOT NULL "
            "ORDER BY m.created_at DESC LIMIT 200",
            (project_id,))
        if not rows:
            return []
        # 转成 dict list，提取文本
        docs = [dict(r) for r in rows]
        query_tokens = _tokenize(query)
        doc_tokens_list = [_tokenize(d["content"] or "") for d in docs]
        # 计算 TF-IDF 分数
        for i, d in enumerate(docs):
            d["_score"] = _tfidf_score(query_tokens, doc_tokens_list[i], doc_tokens_list)
        # 排序取 top
        docs.sort(key=lambda x: x["_score"], reverse=True)
        top = docs[:limit]
        return [{"conv_id": d["conv_id"], "title": d["title"],
                 "role": d["role"], "preview": (d.get("content","")[:200])} for d in top]
    finally:
        await db.close()


async def get_last_conversation_summary(project_id: str, exclude_conv_id: str = None) -> str:
    """获取最近 3 次对话的摘要，用于新对话的上下文注入。返回多条摘要避免只拿到无关对话。"""
    db = await _get_db()
    try:
        # 找最近 3 次对话（跳过琐碎对话：用户消息少于 1 条或总内容 < 20 字）
        if exclude_conv_id:
            rows = await db.execute_fetchall(
                "SELECT id, title, created_at FROM conversations "
                "WHERE project_id = ? AND id != ? ORDER BY updated_at DESC LIMIT 10",
                (project_id, exclude_conv_id))
        else:
            rows = await db.execute_fetchall(
                "SELECT id, title, created_at FROM conversations "
                "WHERE project_id = ? ORDER BY updated_at DESC LIMIT 10",
                (project_id,))
        if not rows:
            return ""

        summaries = []
        for row in rows[:5]:  # 取最近 5 个，过滤琐碎的
            conv = dict(row)
            msgs = await db.execute_fetchall(
                "SELECT role, substr(content, 1, 500) as content FROM messages "
                "WHERE conversation_id = ? AND role IN ('user', 'assistant') "
                "ORDER BY id ASC LIMIT 10",
                (conv["id"],))
            if not msgs:
                continue
            user_msgs = [dict(m)["content"] for m in msgs if dict(m)["role"] == "user"]
            if not user_msgs or sum(len(m) for m in user_msgs) < 20:
                continue  # 跳过琐碎对话
            user_requests = [m[:150] for m in user_msgs[:2]]
            summaries.append(f"「{conv['title']}」({conv['created_at'][:10]})：{'；'.join(user_requests)}")

        if not summaries:
            return ""

        if len(summaries) == 1:
            return f"## 上次对话摘要\n{summaries[0]}"
        return f"## 最近对话摘要（{len(summaries)} 条）\n" + "\n".join(f"- {s}" for s in summaries)
    finally:
        await db.close()
