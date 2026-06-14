"""RAG 语义搜索 — TF-IDF + 余弦相似度，零外部依赖"""
import json
import math
import re
from pathlib import Path
from collections import Counter

SKIP_DIRS = {'node_modules', '__pycache__', '.git', '.maona', 'godot-editor', 'tesseract', '.vscode', 'dist', 'build', '.next', 'data', 'templates'}
CODE_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.html', '.css', '.json', '.gd', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.yaml', '.yml', '.toml', '.cfg', '.ini', '.sh', '.bat', '.ps1', '.sql', '.md', '.txt', '.rb', '.php', '.swift', '.kt'}

def _tokenize(text: str) -> list[str]:
    """分词：英文 CamelCase/snake_case 拆分 + 中文单字/二元组 + 去停用词"""
    text = text.lower()
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'[_\-/.]', ' ', text)
    en_tokens = re.findall(r'[a-z0-9]+', text)
    cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
    stops = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
             'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
             'should', 'may', 'might', 'can', 'shall', 'to', 'of', 'in', 'for',
             'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
             'and', 'but', 'or', 'not', 'no', 'if', 'then', 'else', 'this', 'that',
             'it', 'its', 'we', 'you', 'they', 'he', 'she', 'his', 'her', 'their'}
    # 中文停用字（高频无意义）
    cn_stops = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
                '个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
                '看', '好', '自己', '这', '他', '她', '它', '们', '那', '些', '所', '为',
                '所以', '因为', '但是', '然而', '而且', '可以', '这个', '那个', '什么',
                '怎么', '如何', '如果', '虽然', '已经', '还是', '或者', '以及'}
    result = [t for t in en_tokens if t not in stops and len(t) > 1 and not t.isdigit()]
    # 中文：单字 + 二元组（跳过停用字）
    for i in range(len(cn_chars)):
        if cn_chars[i] not in cn_stops:
            result.append(cn_chars[i])
        if i < len(cn_chars) - 1:
            bigram = cn_chars[i] + cn_chars[i+1]
            if bigram not in cn_stops:
                result.append(bigram)
    return result


class RagIndex:
    def __init__(self, root: Path):
        self.root = root
        self.chunks = []  # [{file, start, end, text, vector}]
        self.idf = {}  # {term: idf_score}
        self._vocab = set()
        self._df = Counter()  # document frequency

    def build(self):
        """扫描项目，分块，计算 TF-IDF"""
        self.chunks = []
        self._df.clear()

        # 1. 分块
        for fpath in sorted(self.root.rglob("*")):
            if any(d in fpath.parts for d in SKIP_DIRS):
                continue
            if fpath.suffix.lower() not in CODE_EXTS:
                continue
            try:
                text = fpath.read_text(encoding='utf-8', errors='replace')
            except:
                continue
            lines = text.split('\n')
            chunk_size = 80
            for i in range(0, len(lines), chunk_size):
                chunk_text = '\n'.join(lines[i:i+chunk_size])
                tokens = _tokenize(chunk_text)
                if len(tokens) < 5:
                    continue
                rel = str(fpath.relative_to(self.root))
                self.chunks.append({
                    'file': rel,
                    'start': i + 1,
                    'end': min(i + chunk_size, len(lines)),
                    'text': chunk_text[:2000],
                    'tokens': tokens,
                    'tf': None  # 后面填
                })
                # 更新 DF
                for t in set(tokens):
                    self._df[t] += 1

        if not self.chunks:
            return 0

        # 2. 计算 IDF
        N = len(self.chunks)
        for term, df in self._df.items():
            self.idf[term] = math.log((N + 1) / (df + 1)) + 1

        # 3. 计算 TF-IDF 向量（稀疏存储）
        for c in self.chunks:
            tf = Counter()
            for t in c['tokens']:
                tf[t] += 1
            vec = {}
            for term, count in tf.items():
                if term in self.idf:
                    vec[term] = count * self.idf[term]
            # L2 归一化
            norm = math.sqrt(sum(v*v for v in vec.values())) or 1
            c['vector'] = {k: v/norm for k, v in vec.items()}
            del c['tokens']  # 不再需要原始 tokens

        return len(self.chunks)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """余弦相似度搜索"""
        if not self.chunks:
            return []
        q_tokens = _tokenize(query)
        # 查询向量
        q_vec = {}
        for t in q_tokens:
            if t in self.idf:
                q_vec[t] = self.idf[t]
        norm = math.sqrt(sum(v*v for v in q_vec.values())) or 1
        q_vec = {k: v/norm for k, v in q_vec.items()}

        # 余弦相似度
        scores = []
        for c in self.chunks:
            dot = sum(q_vec.get(k, 0) * v for k, v in c['vector'].items())
            scores.append((dot, c))

        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        seen = set()
        for score, c in scores[:top_k*3]:  # 去重后取 top_k
            key = c['file']
            if key in seen:
                continue
            seen.add(key)
            # 找高亮片段
            snippet = self._highlight(c['text'], q_tokens)
            results.append({
                'file': c['file'],
                'lines': f"L{c['start']}-L{c['end']}",
                'score': round(score, 3),
                'snippet': snippet[:300]
            })
            if len(results) >= top_k:
                break
        return results

    def _highlight(self, text: str, query_tokens: list[str]) -> str:
        """提取包含查询词的行作为摘要"""
        lines = text.split('\n')
        best = []
        for line in lines:
            score = sum(1 for t in query_tokens if t in line.lower())
            if score > 0:
                best.append((score, line.strip()[:120]))
        if not best:
            return lines[0][:120] if lines else ''
        best.sort(key=lambda x: x[0], reverse=True)
        return ' | '.join(l for _, l in best[:3])

    def save(self):
        """持久化到 .maona/rag_index/"""
        idx_dir = self.root / '.maona' / 'rag_index'
        idx_dir.mkdir(parents=True, exist_ok=True)
        # 分文件存，避免单文件过大
        for i in range(0, len(self.chunks), 500):
            batch = self.chunks[i:i+500]
            (idx_dir / f'chunks_{i//500}.json').write_text(
                json.dumps(batch, ensure_ascii=False)
            )
        # 存 IDF
        (idx_dir / 'idf.json').write_text(
            json.dumps(self.idf, ensure_ascii=False)
        )
        (idx_dir / 'meta.json').write_text(
            json.dumps({'root': str(self.root), 'total_chunks': len(self.chunks), 'df': dict(self._df.most_common(100))}, ensure_ascii=False)
        )

    def load(self):
        """从 .maona/rag_index/ 加载"""
        idx_dir = self.root / '.maona' / 'rag_index'
        if not idx_dir.exists():
            return False
        try:
            self.idf = json.loads((idx_dir / 'idf.json').read_text(encoding='utf-8'))
        except:
            return False
        self.chunks = []
        for f in sorted(idx_dir.glob('chunks_*.json')):
            self.chunks.extend(json.loads(f.read_text(encoding='utf-8')))
        return len(self.chunks) > 0

    def stats(self) -> str:
        if not self.chunks:
            return "索引为空"
        files = len(set(c['file'] for c in self.chunks))
        terms = len(self.idf)
        return f"{len(self.chunks)} 个代码块, {files} 个文件, {terms} 个词条"
