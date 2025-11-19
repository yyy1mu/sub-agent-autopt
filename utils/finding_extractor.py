"""发现提取模块"""
import re
from typing import List


def extract_findings(executor_output: str, existing_findings: List[str]) -> List[str]:
    """
    提取新发现和FLAG
    
    Args:
        executor_output: 执行器的输出文本
        existing_findings: 已存在的发现列表（用于去重）
    
    Returns:
        新发现的列表
    """
    new_findings = []
    
    # 匹配各种格式的发现
    patterns = [
        (r"\[FINDING\]\s*([^:\n]+?):\s*(.+?)(?=\n\[|$)", "FINDING"),
        (r"\[DISCOVERY\]\s*(.+?)(?=\n\[|$)", "DISCOVERY"),
        (r"\[FLAG\]\s*(.+?)(?=\n|$)", "FLAG"),
        (r"flag\{[^}]+\}", "FLAG"),  # 直接匹配flag格式
    ]
    
    for pattern, ftype in patterns:
        for match in re.finditer(pattern, executor_output, re.IGNORECASE | re.DOTALL):
            if ftype == "FLAG":
                # 检查是否有捕获组，如果没有则使用 group(0)
                if match.lastindex is None or match.lastindex == 0:
                    content = match.group(0)
                else:
                    content = match.group(1)
                finding = f"FLAG: {content.strip().replace('`', '')}"
            elif ftype == "FINDING":
                finding = f"{match.group(1).strip()}: {match.group(2).strip()}"
            else:  # DISCOVERY
                finding = f"发现: {match.group(1).strip()}"
            
            # 去重
            if finding not in existing_findings and not any(f.startswith(finding[:20]) for f in existing_findings):
                new_findings.append(finding)
                
    return new_findings


def has_flag(findings: List[str]) -> bool:
    """
    检查发现列表中是否包含FLAG
    
    Args:
        findings: 发现列表
    
    Returns:
        如果包含FLAG返回True
    """
    return any("flag{" in f.lower() for f in findings)

