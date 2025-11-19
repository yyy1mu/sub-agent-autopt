"""状态管理模块"""
import re
from typing import Dict, Any


def truncate(text: str, max_len: int = 400) -> str:
    """截断文本"""
    if len(text) <= max_len:
        return text
    return text[:max_len].replace("\n", " ") + "..."


def update_state(executor_output: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    从执行器输出中提取状态更新
    """
    new_state = current_state.copy()
    
    # 多种模式匹配（增强鲁棒性）
    patterns = [
        r"\[STATE_UPDATE\]\s*([a-zA-Z0-9_]+)\s*:\s*(.+?)(?=\n\[STATE_UPDATE\]|\n\*\*|$)",  # 标准格式，改进匹配
        r"!\[报告State变更\]!.*?'([a-zA-Z0-9_]+)':\s*'([^']+)'",   # 字典格式
        r"Set-Cookie:\s*(session=[^\s;]+)",                         # 直接从HTTP响应提取
        r"set-cookie:\s*([^;]+)",                                   # 小写set-cookie
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, executor_output, re.MULTILINE | re.DOTALL | re.IGNORECASE):
            if pattern in [patterns[2], patterns[3]]:  # Set-Cookie特殊处理
                cookie_value = match.group(1).strip()
                if cookie_value and cookie_value != current_state.get("cookie"):
                    print(f"[STATE] ★ 从HTTP响应提取Cookie: '{truncate(cookie_value, 50)}'")
                    new_state["cookie"] = cookie_value
            else:
                key = match.group(1).strip()
                value = match.group(2).strip().strip("',\"")
                
                # 特殊处理cookie值，保留完整格式
                if key == "cookie" and value.startswith("access_token"):
                    # 保留完整的cookie值，包括引号
                    full_match = re.search(r"\[STATE_UPDATE\]\s*cookie\s*:\s*(.+?)(?=\n\[STATE_UPDATE\]|\n\*\*|$)", 
                                         executor_output, re.MULTILINE | re.DOTALL)
                    if full_match:
                        value = full_match.group(1).strip().strip("',\"")
                
                # 过滤无效值
                if value and value.lower() not in ["none", "null", ""]:
                    if new_state.get(key) != value:
                        print(f"[STATE] ★ 状态更新: '{key}' = '{truncate(value, 50)}'")
                        new_state[key] = value
    
    return new_state


def check_cookie_expired(output: str, old_cookie: str | None, new_cookie: str | None, is_login_task: bool) -> bool:
    """
    检查Cookie是否失效
    
    Args:
        output: 执行器输出
        old_cookie: 旧的cookie值
        new_cookie: 新的cookie值
        is_login_task: 是否是登录任务
    
    Returns:
        如果cookie失效返回True
    """
    if not old_cookie:
        return False
    
    # Cookie失效检测（更精确的逻辑）
    is_auth_required_redirect = (
        'Redirecting' in output and 
        'href="/"' in output and 
        not is_login_task
    )
    
    # 只有在以下情况才认为cookie失效：
    # 1. 有cookie
    # 2. 不是登录任务
    # 3. 被重定向到首页
    # 4. 新cookie没有被更新（说明登录未成功）
    if old_cookie and is_auth_required_redirect and old_cookie == new_cookie:
        return True
    
    return False


def format_state_summary(state: Dict[str, Any], findings: list) -> str:
    """
    格式化状态摘要，用于传递给执行agent
    
    Args:
        state: 当前状态字典
        findings: 发现列表
    
    Returns:
        格式化的状态摘要字符串
    """
    return (
        f"cookie: {state.get('cookie', 'None')}\n"
        f"user_id: {state.get('user_id', 'None')}\n"
        f"base_url: {state.get('base_url', '')}\n"
        f"findings: {findings[-3:] if findings else []}"  # 只传递最近的发现
    )

