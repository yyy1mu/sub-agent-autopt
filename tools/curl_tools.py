"""Curl工具模块 - 提供HTTP请求工具"""
import json
import shlex
import subprocess
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool


def _parse_headers(headers: Optional[str]) -> Dict[str, str]:
    """
    解析 headers 字符串：
    - 若为 JSON 字符串（如 {"Authorization":"Bearer ..."}），解析为 dict
    - 为空或解析失败则返回空 dict
    """
    if not headers:
        return {}
    
    try:
        obj = json.loads(headers)
        if isinstance(obj, dict):
            return {str(k): str(v) for k, v in obj.items()}
        return {}
    except Exception:
        return {}


@tool("local_curl")
def local_curl(
    url: str,
    method: str = "GET",
    headers: Optional[str] = None,
    data: Optional[str] = None,
    timeout_sec: int = 20,
    insecure: bool = False,
) -> Dict[str, Any]:
    """
    使用本地 curl 发起 HTTP 请求，返回 exit_code/stdout/stderr。
    
    参数：
    - url: 请求地址
    - method: HTTP 方法，默认 GET
    - headers: 可选，JSON 字符串格式的请求头，例如 {"Authorization":"Bearer xxx"}
    - data: 可选，请求体（自动使用 --data-binary）
    - timeout_sec: 超时时间（秒），默认 20
    - insecure: 是否忽略 TLS 证书校验（-k），默认 False
    """
    cmd: List[str] = ["curl", "-sS", "-X", method, "--max-time", str(timeout_sec)]
    
    if insecure:
        cmd.append("-k")
    
    # 添加 headers
    hdrs = _parse_headers(headers)
    for k, v in hdrs.items():
        cmd += ["-H", f"{k}: {v}"]
    
    # 添加 data
    if data is not None:
        cmd += ["--data-binary", data]
    
    # URL 最后
    cmd.append(url)
    
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "cmd": cmd,
        }
    except Exception as e:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "cmd": cmd,
        }


@tool("local_curl_raw")
def local_curl_raw(args: str = None, **kwargs) -> Dict[str, Any]:
    """
    使用本地 curl 的原始参数字符串（不包含 'curl' 本身），更灵活（注意安全）。
    
    例如："-k -sS -X POST https://example.com -H 'Content-Type: application/json' --data '{\"a\":1}'"
    
    返回 exit_code/stdout/stderr。
    """
    # 处理 LangChain 可能添加的 v__args 前缀
    if args is None:
        args = kwargs.get('v__args', kwargs.get('args', ''))
    
    # 如果 args 是列表，转换为字符串
    if isinstance(args, list):
        args = ' '.join(str(a) for a in args)
    
    base = ["curl"]
    try:
        parts = shlex.split(args)
    except Exception:
        # 容错：若分词失败，直接裸传给 shell
        parts = [args]
    
    cmd = base + parts
    
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "cmd": cmd,
        }
    except Exception as e:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "cmd": cmd,
        }


def get_curl_tools() -> List:
    """
    返回 curl 工具列表。
    
    Returns:
        包含 local_curl 和 local_curl_raw 工具的列表
    """
    return [local_curl, local_curl_raw]

