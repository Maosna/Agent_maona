"""任务拆解与自动回溯 — 让 Agent 能自己规划、纠正、重试"""

import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SubTask:
    id: int
    goal: str
    tools: list[str]  # 预期使用的工具
    status: str = "pending"  # pending|running|done|failed
    result: str = ""
    retries: int = 0
    max_retries: int = 2


@dataclass
class TaskPlan:
    original_request: str
    subtasks: list[SubTask] = field(default_factory=list)
    current_index: int = 0
    total_retries: int = 0
    max_total_retries: int = 5

    def current(self) -> Optional[SubTask]:
        if 0 <= self.current_index < len(self.subtasks):
            return self.subtasks[self.current_index]
        return None

    def next(self) -> Optional[SubTask]:
        self.current_index += 1
        return self.current()

    def add_alternative(self, task: SubTask, after_index: int):
        """在指定位置后插入备选方案"""
        self.subtasks.insert(after_index + 1, task)

    def all_done(self) -> bool:
        return all(t.status == "done" for t in self.subtasks)

    def progress(self) -> str:
        done = sum(1 for t in self.subtasks if t.status == "done")
        return f"{done}/{len(self.subtasks)}"


async def decompose_task(user_request: str, provider, tools: list[str]) -> TaskPlan:
    """使用 LLM 拆解用户请求为子任务列表"""
    prompt = f"""你是一个任务规划专家。请将以下用户请求拆解为有序的子任务列表。

用户请求: {user_request}

可用工具: {', '.join(tools[:30])}

请严格按照 JSON 格式返回，不要加其他文字:
{{"subtasks": [
  {{"goal": "子任务描述（中文）", "tools": ["预期使用的工具1", "工具2"]}},
  ...
]}}

规则:
1. 子任务按执行顺序排列
2. 每个子任务的目标要具体、可验证
3. 子任务数量控制在 3-7 个
4. 复杂任务可以包含"验证"子任务
5. 工具名必须从可用工具列表中选择"""
    
    try:
        resp = await provider.chat_non_stream(
            [{"role": "user", "content": prompt}],
            tools=None
        )
        content = resp.get("content", "")
        # 提取 JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            data = json.loads(json_match.group())
            plan = TaskPlan(original_request=user_request)
            for i, st_data in enumerate(data.get("subtasks", [])):
                plan.subtasks.append(SubTask(
                    id=i + 1,
                    goal=st_data.get("goal", ""),
                    tools=st_data.get("tools", []),
                ))
            if plan.subtasks:
                return plan
    except Exception as e:
        print(f"[Maona] 任务拆解失败: {e}")

    # 回退：单步任务
    plan = TaskPlan(original_request=user_request)
    plan.subtasks.append(SubTask(id=1, goal=user_request, tools=tools[:5]))
    return plan


def should_backtrack(plan: TaskPlan, current_task: SubTask) -> bool:
    """判断是否需要回溯"""
    if current_task.status != "failed":
        return False
    return current_task.retries < current_task.max_retries


def backtrack_prompt(plan: TaskPlan, failed_task: SubTask) -> str:
    """生成回溯提示词，指导 LLM 尝试替代策略"""
    alt_strategies = [
        "换一种工具或参数重试",
        "先检查前置条件是否满足",
        "拆分为更小的步骤",
        "跳过当前步骤尝试后面的，再回来补",
    ]
    alt = alt_strategies[failed_task.retries % len(alt_strategies)]
    
    return f"""[系统] 子任务 "{failed_task.goal}" 失败。
建议：{alt}。
当前进度：{plan.progress()}，总重试：{plan.total_retries}/{plan.max_total_retries}。
请采取替代策略继续执行。"""


def get_plan_context(plan: TaskPlan) -> str:
    """生成计划上下文，注入到 system prompt"""
    if not plan or not plan.subtasks:
        return ""

    lines = ["\n## 任务执行计划"]
    lines.append(f"总目标: {plan.original_request[:100]}")
    lines.append(f"进度: {plan.progress()}")
    lines.append("")
    for t in plan.subtasks:
        icon = {"pending": "⬜", "running": "🔄", "done": "✅", "failed": "❌"}.get(t.status, "⬜")
        lines.append(f"{icon} 步骤{t.id}: {t.goal} [{', '.join(t.tools[:3])}]")
    return "\n".join(lines)
