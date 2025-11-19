"""规划Agent模块"""
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from config.llm_config import build_llm


class PlannerAgent:
    """规划Agent，负责生成和更新待办清单"""
    
    def __init__(self, llm: ChatOpenAI | None = None):
        """
        初始化规划Agent
        
        Args:
            llm: LLM实例，如果为None则使用默认配置创建
        """
        self.llm = llm or build_llm()
    
    def generate_todos(self, goal: str, context: str = "") -> List[str]:
        """
        生成或更新待办清单
        
        Args:
            goal: 总体目标
            context: 上下文信息（当前状态、发现、历史等）
        
        Returns:
            待办事项列表
        """
        if context:
            prompt_text = """目标:

{goal}

---

**关键上下文与最新发现**:

{context}

---

**你的任务**：

基于【新测试方法论】和【当前状态】生成*精准的*后续待办清单。

**!![新测试方法论]!!**：

1.  **观测 (Observe)**：信息收集。使用`local_curl`访问新发现的路径。

2.  **探测 (Probe)**：枚举。发现可疑点后，根据漏洞的类型，使用不同的*漏洞探测方法*。

**!![规划规则]!!**

1.  **!![格式]!!**：**只输出待办事项列表，每行一个。** 不要包含任何其他文字。

2.  **!![优先登录]!!**：如果 'Current State' 中 `cookie` 为 None 或 "None"，**第一个任务必须是 '登录系统并获取Cookie'**。

3.  **!![IDOR测试优先级]!!**

4.  **!![避免重复]!!**：不要生成已完成的任务（检查 Recent History）。

请生成后续待办清单：

"""
        else:
            prompt_text = """目标:

{goal}

**你的任务**:

1.  **!![格式死命令]!!**：**只输出待办事项列表，每行一个。** 不要包含任何其他文字。

2.  **!![规划]!!**: 生成不超过5个步骤的初始`观测(Observe)`清单，以`观测(Observe) 目标主页并寻找登录入口`开始。

请生成初始待办清单：

"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是资深安全测试教练。将用户目标拆解为简短可执行的步骤。"),
            ("human", prompt_text),
        ])
        
        chain = prompt | self.llm
        text = chain.invoke({"goal": goal, "context": context or "无"}).content.strip()
        
        lines = [ln.strip("- •* \t0123456789.").strip() for ln in text.splitlines() if ln.strip()]
        seen = set()
        todos = []
        
        for ln in lines:
            if ln and ln not in seen:
                seen.add(ln)
                todos.append(ln)
        
        if not context and not todos:
            return ["观测(Observe) 目标主页并寻找登录入口"]
        
        return todos[:8]
    
    def format_planning_context(
        self, 
        state: dict, 
        findings: List[str], 
        step_history: List[dict]
    ) -> str:
        """
        格式化规划上下文
        
        Args:
            state: 当前状态字典
            findings: 发现列表
            step_history: 步骤历史列表
        
        Returns:
            格式化的上下文字符串
        """
        return (
            f"**Current State**:\n"
            f"- cookie: {state.get('cookie', 'None')}\n"
            f"- user_id: {state.get('user_id', 'None')}\n"
            f"- base_url: {state.get('base_url', '')}\n\n"
            f"**Findings** ({len(findings)}条):\n" + 
            "\n".join(f"  - {f}" for f in findings[-5:]) + "\n\n"  # 只传递最近5条
            f"**Recent History** (最近3步):\n" +
            "\n".join(f"  [{h['step']}] {h['todo']}" for h in step_history[-3:])
        )

