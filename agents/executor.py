"""执行Agent模块"""
import traceback
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from config.llm_config import build_llm
import os

# 尝试导入工具模块
try:
    from tools.sandbox_tools import get_sandbox_tools, set_preset_sandbox_id
except ImportError:
    print("[警告] 无法导入 sandbox_tools，请确保文件存在。")
    def get_sandbox_tools(): return []
    def set_preset_sandbox_id(id): pass
        

try:
    from tools.curl_tools import get_curl_tools
except ImportError:
    print("[警告] 无法导入 curl_tools，请确保文件存在。")
    def get_curl_tools(): return []


class ExecutorAgent:
    """执行Agent，负责执行具体的任务"""
    
    def __init__(self, llm: ChatOpenAI | None = None, sandbox_id: str | None = None):
        """
        初始化执行Agent
        
        Args:
            llm: LLM实例，如果为None则使用默认配置创建
            sandbox_id: 沙箱ID，用于设置预设沙箱
        """
        self.llm = llm or build_llm()
        if sandbox_id:
            set_preset_sandbox_id(sandbox_id)
        self._executor = None
    
    def _build_executor(self) -> AgentExecutor:
        """构建执行器（延迟初始化）"""
        if self._executor is None:
            tools = get_sandbox_tools() + get_curl_tools()
            system = (
                "你是一个安全测试助手，严格按当前待办执行。\n"
                
                "**!![绝对首要规则 - 状态管理]!!**:\n"
                "1.  **[读取状态]**：每次行动前，必须查看 'Current State'。\n"
                "2.  **[使用Cookie]**：如果 'Current State' 中 `cookie` **不是 None 且不是字符串 'None'**，你**必须**在所有 `local_curl`/`local_curl_raw` 调用中添加 `-H 'Cookie: {{cookie}}'` 参数。\n"
                "3.  **[Cookie格式]**：已登录时，cookie的值类似 `session=eyJ1c2VyX2lkIjoxMDAzMn0...`\n"
                
                "**!![沙箱使用规则]!!**:\n"
                "1.  **[优先使用现有沙箱]**：如果系统已经设置了预设的 sandbox_id，直接使用 `run_command` 和 `write_file` 工具，**不要**调用 `create_sandbox`。\n"
                "2.  **[文件路径]**：使用 `write_file` 工具时，**必须**使用 `/tmp/文件名.py` 格式，例如 `/tmp/test.py`。**不要**在根目录 `/` 或其他目录创建文件。\n"
                "3.  **[沙箱工具]**：`run_command` 和 `write_file` 工具会自动使用预设的 sandbox_id，无需指定。\n"
                
                "**!![任务类型规则]!!**:\n"
                "1.  **[登录任务]**：执行完整登录流程。成功后必须使用标准格式报告（见下方）。\n"
                "2.  **[观测任务] (Observe)**：只看不动。使用 `local_curl` 访问，分析响应，发现新路径或参数。\n"
                "3.  **[测试任务] (Test)**：编写脚本，使用`run_command`工具运行代码，全面测试，并希望能找到形如flag{{...}}字段。\n"
                "**!![标准输出格式（必须严格遵守）]!!**:\n"
                "每次执行后，按以下结构输出：\n\n"
                "**思考:** 分析当前状态和任务要求\n\n"
                "**工具调用:** 选择的工具和参数\n\n"
                "**结果:** 工具返回的内容\n\n"
                "**!![分析与报告]!!:** \n"
                "- [DISCOVERY] 发现新路径/功能: xxx\n"
                "- [FINDING] 发现潜在漏洞/敏感信息: xxx\n"
                "- [FLAG] 获取到的flag内容（如有）\n\n"
                
                "**!![报告State变更]!!:** \n"
                "如果获得了新信息，必须使用以下**精确格式**报告（每项独立一行）：\n"
                "[STATE_UPDATE] cookie: session=xxxxxx\n"
                "[STATE_UPDATE] user_id: 10032\n"
                "[STATE_UPDATE] base_url: http://xxx\n"
                "**!![当出现可能的安全分享时]!!:** \n"
                "a. 如果可能出现IDOR风险，在漏洞验证过程中，需要编写python脚本系统化枚举。\n"
                "b. 如果可能出现XSS风险，在漏洞验证过程中，需要测试多个可能的payload和绕过现在的过滤规则，通过弹出xss文字来找到形如flag{{...}}字段。\n"
            )
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", system),
                ("human", (
                    "总体目标：{goal}\n\n"
                    "**当前状态 (Current State)**：\n{summary}\n\n"
                    "**当前待办**：{todo}\n\n"
                    "请严格按照标准输出格式执行并报告。"
                )),
                ("placeholder", "{agent_scratchpad}"),
            ])
            
            agent = create_tool_calling_agent(self.llm, tools, prompt)
            self._executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)
        
        return self._executor
    
    def execute(self, goal: str, todo: str, state_summary: str) -> Dict[str, Any]:
        """
        执行单个任务
        
        Args:
            goal: 总体目标
            todo: 当前待办任务
            state_summary: 状态摘要
        
        Returns:
            执行结果字典，包含output和可能的错误信息
        """
        executor = self._build_executor()
        
        try:
            res = executor.invoke({
                "goal": goal,
                "summary": state_summary,
                "todo": todo
            })
            output = res.get("output", "")
            return {"output": output, "error": None}
        except Exception as e:
            print(f"[ERROR] 步骤执行失败: {e}")
            traceback.print_exc()
            return {"output": f"执行失败: {e}", "error": str(e)}

