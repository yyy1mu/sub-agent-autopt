"""协调Agent模块 - 主协调者，负责整体流程控制"""
from typing import List, Tuple, Dict, Any
from langchain_openai import ChatOpenAI
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from utils.state_manager import update_state, check_cookie_expired, format_state_summary, truncate
from utils.finding_extractor import extract_findings, has_flag
from config.llm_config import build_llm


class CoordinatorAgent:
    """主协调Agent，负责协调规划Agent和执行Agent，管理整体流程"""
    
    def __init__(self, sandbox_id: str | None = None):
        """
        初始化协调Agent
        
        Args:
            sandbox_id: 沙箱ID
        """
        self.llm = build_llm()
        self.planner = PlannerAgent(self.llm)
        self.executor = ExecutorAgent(self.llm, sandbox_id)
        
        # 初始状态
        self.state = {
            "cookie": None,
            "user_id": None,
            "base_url": None,
        }
        
        # 执行历史
        self.findings: List[str] = []
        self.step_history: List[Dict[str, Any]] = []
        self.completed_todos: List[str] = []
        self.todos: List[str] = []
        
        # 控制变量
        self.session_established = False  # 是否曾成功建立过会话
        self.consecutive_login_attempts = 0
        self.max_iter = 100
        self.has_new_findings = False  # 标记本轮是否有新发现
    
    def run(self, goal: str) -> Tuple[List[str], str]:
        """
        运行主循环
        
        Args:
            goal: 总体目标
        
        Returns:
            完成的待办列表和最终总结
        """
        # 初始化待办清单
        self.todos = self.planner.generate_todos(goal)
        print(f"[PLAN] 初始待办清单 ({len(self.todos)}项):")
        for idx, t in enumerate(self.todos, 1):
            print(f"  {idx}. {t}")
        
        # 主循环
        for i in range(1, self.max_iter + 1):
            if not self.todos:
                print("\n[完成] 所有待办已执行完毕。")
                break
            
            todo = self.todos.pop(0)
            self.completed_todos.append(todo)
            
            print(f"\n{'='*60}")
            print(f"[步骤 {i}] 执行: {todo}")
            print(f"[当前状态] Cookie: {truncate(str(self.state.get('cookie', 'None')), 30)}, "
                  f"UserID: {self.state.get('user_id', 'None')}")
            print('='*60)
            
            # 执行任务
            state_summary = format_state_summary(self.state, self.findings)
            result = self.executor.execute(goal, todo, state_summary)
            output = result["output"]
            
            # 记录执行前的发现数量
            findings_before = len(self.findings)
            
            # 更新状态
            self._update_state_from_output(output, todo)
            
            # 提取发现
            self._extract_and_update_findings(output)
            
            # 检查是否有新发现
            self.has_new_findings = len(self.findings) > findings_before
            
            # 记录历史
            self.step_history.append({
                "step": i,
                "todo": todo,
                "output": truncate(output),
                "state_before": self.state.copy(),
                "findings_before": findings_before
            })
            
            # 检查是否获取FLAG
            if has_flag(self.findings):
                print("\n" + "="*60)
                print("[SUCCESS] 🎉 恭喜！已获取 Flag，任务完成！")
                print("="*60)
                break
            
            # 动态规划
            self._replan_if_needed(goal)
            
            # 防止无限登录循环
            if self.consecutive_login_attempts > 3:
                print("[ERROR] 连续3次登录失败，可能凭据错误，终止执行。")
                break
        
        # 生成最终报告
        return self._generate_final_report()
    
    def _update_state_from_output(self, output: str, todo: str):
        """从输出中更新状态"""
        old_cookie = self.state.get("cookie")
        self.state = update_state(output, self.state)
        new_cookie = self.state.get("cookie")
        
        # 判断是否是登录任务
        is_login_task = "登录" in todo.lower() or "login" in todo.lower()
        
        # 检查Cookie是否失效
        if check_cookie_expired(output, old_cookie, new_cookie, is_login_task):
            print("[STATE] ⚠️ 检测到会话失效（认证失败重定向），清除 Cookie。")
            self.state["cookie"] = None
            self.consecutive_login_attempts += 1
        elif new_cookie and new_cookie != old_cookie:
            # 成功获取新cookie，重置计数器
            self.consecutive_login_attempts = 0
            self.session_established = True
            print(f"[STATE] ✓ 新会话已建立")
    
    def _extract_and_update_findings(self, output: str):
        """提取并更新发现"""
        new_finds = extract_findings(output, self.findings)
        if new_finds:
            print(f"\n[FINDING] 新发现 ({len(new_finds)}条):")
            for nf in new_finds:
                print(f"  - {nf}")
            self.findings.extend(new_finds)
    
    def _replan_if_needed(self, goal: str):
        """如果需要，触发重新规划"""
        need_replan = False
        replan_reason = []
        
        # 检查是否需要登录
        cookie_missing = self.state.get("cookie") is None or self.state.get("cookie") == "None"
        if cookie_missing and self.session_established:
            if not any("登录" in t.lower() or "login" in t.lower() for t in self.todos):
                replan_reason.append("会话丢失，需要登录")
                need_replan = True
        
        # 检查是否有新发现
        if self.has_new_findings:
            replan_reason.append("发现新线索")
            need_replan = True
            self.has_new_findings = False  # 重置标志
        
        # 检查待办队列是否为空
        if not self.todos:
            replan_reason.append("待办队列为空")
            need_replan = True
        
        if need_replan:
            print(f"\n[PLAN] 触发重新规划: {', '.join(replan_reason)}")
            
            planner_context = self.planner.format_planning_context(
                self.state,
                self.findings,
                self.step_history
            )
            
            new_todos = self.planner.generate_todos(goal, context=planner_context)
            
            # 去重：移除已完成的任务
            unique_todos = []
            for nt in new_todos:
                # 简单的重复检测
                if not any(nt.lower() in ct.lower() for ct in self.completed_todos[-5:]):
                    unique_todos.append(nt)
            
            self.todos = unique_todos
            print(f"[PLAN] 更新后的待办 ({len(self.todos)}项):")
            for idx, t in enumerate(self.todos, 1):
                print(f"  {idx}. {t}")
    
    def _generate_final_report(self) -> Tuple[List[str], str]:
        """生成最终报告"""
        print("\n" + "="*60)
        print("执行总结")
        print("="*60)
        print(f"完成步骤数: {len(self.completed_todos)}")
        print(f"最终状态: {self.state}")
        print(f"发现总数: {len(self.findings)}")
        
        if self.findings:
            print("\n所有发现:")
            for idx, f in enumerate(self.findings, 1):
                print(f"  {idx}. {f}")
        
        summary = f"Final State: {self.state}\nFindings: {self.findings}"
        return self.completed_todos, summary

