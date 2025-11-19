"""沙箱工具模块 - 提供Docker沙箱管理工具"""
import uuid
import tempfile
import os
import shutil
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.callbacks import CallbackManagerForToolRun
import docker



# =====================
# Docker 客户端管理
# =====================

_client = None

def get_docker_client():
    """获取 Docker 客户端（延迟初始化，简化错误处理）。"""
    global _client
    if _client is not None:
        return _client
    
    if docker is None:
        raise RuntimeError("docker 模块未安装，请运行: pip install docker")
    
    try:
        _client = docker.from_env()
        _client.ping()
        return _client
    except Exception as e:
        raise RuntimeError(
            f"无法连接到 Docker daemon: {e}\n"
            "请确认 Docker Desktop 已启动，并确保当前用户有权限访问 /var/run/docker.sock"
        )


# =====================
# Docker 沙箱核心类
# =====================

class FilesAPI:
    def __init__(self, container):
        self.container = container

    def write(self, path, content):
        # path is absolute inside container
        assert path.startswith("/tmp") or path.startswith("/")
        
        # 确保目录存在
        dir_path = os.path.dirname(path)
        if dir_path != "/" and dir_path:
            result = self.container.exec_run(
                f"mkdir -p {dir_path}",
                workdir="/"
            )
            if result[0] != 0:
                raise RuntimeError(f"无法创建目录 {dir_path}: {result[1]}")
        
        # 使用 Python 在容器内创建文件（最可靠的方法）
        # 将内容进行 base64 编码以避免特殊字符问题
        import base64
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
        
        # 使用 base64 解码并写入文件
        python_cmd = f"""python3 -c "
import base64
import os
content = base64.b64decode('{encoded_content}').decode('utf-8')
with open('{path}', 'w', encoding='utf-8') as f:
    f.write(content)
"
"""
        
        result = self.container.exec_run(
            python_cmd,
            workdir="/"
        )
        
        if result[0] != 0:
            # 如果 Python 方法失败，尝试使用 echo + here-doc（适用于简单内容）
            # 但这种方法对特殊字符不友好
            try:
                # 转义单引号和特殊字符
                escaped_content = content.replace("'", "'\"'\"'")
                echo_cmd = f"sh -c \"cat > {path} << 'EOF'\n{content}\nEOF\""
                result = self.container.exec_run(echo_cmd, workdir="/")
                
                if result[0] != 0:
                    raise RuntimeError(f"无法在容器内创建文件 {path}: {result[1].decode('utf-8', errors='ignore')}")
            except Exception as e:
                raise RuntimeError(f"无法在容器内创建文件 {path}: {e}")
        
        # 验证文件是否创建成功
        verify_result = self.container.exec_run(f"test -f {path}", workdir="/")
        if verify_result[0] != 0:
            raise RuntimeError(f"文件创建后验证失败: {path}")
        
        print(f"[SANDBOX] 文件在容器内创建成功: {path}")


class CommandsAPI:
    def __init__(self, container):
        self.container = container

    def run(self, cmd, timeout=120, user="root"):
        # Use container.exec_run, returns exit_code and output bytes
        try:
            exec_id = self.container.exec_run(
                cmd, 
                user=user, 
                demux=True, 
                stdout=True, 
                stderr=True, 
                tty=False, 
                stream=False, 
                workdir="/tmp", 
                stdin=False, 
                environment=None, 
                privileged=False, 
                socket=False
            )
            # docker-py exec_run returns a tuple (exit_code, output) when demux=False.
            # When demux=True it returns tuple (exit_code, (stdout, stderr))
            exit_code, output = exec_id

            if isinstance(output, tuple):
                stdout = (output[0] or b"").decode("utf-8", errors="ignore")
                stderr = (output[1] or b"").decode("utf-8", errors="ignore")
            else:
                stdout = (output or b"").decode("utf-8", errors="ignore")
                stderr = ""

            class R:
                pass
            r = R()
            r.stdout = stdout
            r.stderr = stderr
            r.exit_code = exit_code
            return r
        except Exception as e:
            class R:
                pass
            r = R()
            r.stdout = ""
            r.stderr = str(e)
            r.exit_code = -1
            return r


class DockerSandbox:
    def __init__(self, container, host_workdir=None):
        self.container = container
        self._files = FilesAPI(container)  # 直接传入 container
        self._commands = CommandsAPI(container)
        self.host_workdir = host_workdir  # 保留用于其他用途（如果需要）

    @property
    def files(self):
        return self._files

    @property
    def commands(self):
        return self._commands

    def set_timeout(self, ms):
        # optional; no-op or store for use on commands
        self.timeout_ms = ms

    def kill(self):
        try:
            self.container.remove(force=True)
        except Exception:
            pass
        # 不再需要删除 host_workdir，因为不再使用挂载
        if self.host_workdir and os.path.exists(self.host_workdir):
            try:
                shutil.rmtree(self.host_workdir)
            except Exception:
                pass


def make_sandbox(network: str | None = None):
    # 不再需要创建主机临时目录用于挂载
    client = get_docker_client()

    try:
        run_kwargs = dict(
            image="python:3.11-slim",
            command="sleep infinity",
            detach=True,
            stdin_open=False,
            tty=False,
            # 不再挂载 volumes
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            mem_limit="512m",
            pids_limit=128,
            user="root",
            remove=False,
        )

        # 网络策略：若指定 network 则加入该网络并启用网络；否则默认禁网
        if network:
            run_kwargs["network"] = network
            run_kwargs["network_disabled"] = False
        else:
            run_kwargs["network_disabled"] = True

        container = client.containers.run(**run_kwargs)
    except docker.errors.ImageNotFound:
        raise RuntimeError("Docker 镜像 'python:3.11-slim' 未找到。请先运行: docker pull python:3.11-slim")
    except docker.errors.APIError as e:
        raise RuntimeError(f"Docker API 错误: {e}")
    except Exception as e:
        raise RuntimeError(f"创建 Docker 容器失败: {e}")

    # 不再需要 host_workdir，传入 None
    return DockerSandbox(container, host_workdir=None)


# =====================
# 全局沙箱注册表
# =====================

# 全局沙箱注册表，供跨工具调用共享状态
_SANDBOXES: Dict[str, DockerSandbox] = {}
_LAST_SANDBOX_ID: Optional[str] = None
_PRESET_SANDBOX_ID: Optional[str] = None  # 预设的 sandbox_id，优先使用


def _require_sandbox(sandbox_id: str) -> DockerSandbox:
    if sandbox_id not in _SANDBOXES:
        raise ValueError(f"sandbox_id 不存在: {sandbox_id}")
    return _SANDBOXES[sandbox_id]


def _resolve_sandbox(optional_id: Optional[str]) -> DockerSandbox:
    """解析沙箱：优先使用传入 ID；其次使用预设 ID。"""
    if optional_id:
        return _require_sandbox(optional_id)
    
    # 检查是否有预设的 sandbox_id
    global _PRESET_SANDBOX_ID
    if not _PRESET_SANDBOX_ID:
        raise ValueError("未设置预设的 sandbox_id。请确保已通过 set_preset_sandbox_id() 设置。")
    
    if _PRESET_SANDBOX_ID in _SANDBOXES:
        return _SANDBOXES[_PRESET_SANDBOX_ID]
    
    # 预设的 sandbox_id 不在注册表中，尝试从 Docker 容器连接
    try:
        client = get_docker_client()
        if client is None:
            raise ValueError("Docker client 不可用")
        
        # 尝试通过完整 ID 或短 ID 查找容器
        try:
            container = client.containers.get(_PRESET_SANDBOX_ID)
        except Exception:
            # 如果完整 ID 找不到，尝试使用前 12 位（Docker 短 ID）
            short_id = _PRESET_SANDBOX_ID[:12]
            container = client.containers.get(short_id)
        
        # 从已存在的容器创建 DockerSandbox
        # 不再需要获取挂载路径，直接在容器内操作
        container.reload()
        print(f"[SANDBOX] 连接到容器: {container.id[:12]} (状态: {container.status})")

        # 直接创建 DockerSandbox，不需要 workdir
        sbx = DockerSandbox(container, host_workdir=None)

        # 注册到 _SANDBOXES
        _SANDBOXES[_PRESET_SANDBOX_ID] = sbx
        global _LAST_SANDBOX_ID
        _LAST_SANDBOX_ID = _PRESET_SANDBOX_ID
        print(f"[SANDBOX] 从已存在的 Docker 容器连接并注册 sandbox: {_PRESET_SANDBOX_ID}")
        return sbx
    except Exception as e:
        # 如果无法从 Docker 连接，提供清晰的错误信息
        available = list_sandboxes()
        raise ValueError(
            f"预设的 sandbox_id '{_PRESET_SANDBOX_ID}' 不在当前进程的注册表中，且无法从 Docker 容器连接。\n"
            f"错误: {e}\n"
            f"当前已注册的 sandbox_id: {available if available else '(无)'}\n"
            f"提示：请确保 Docker 容器存在且可访问，或检查 sandbox_id 是否正确。"
        )


# =====================
# 工具入参与返回模型
# =====================

class CreateSandboxInput(BaseModel):
    pass


class CreateSandboxOutput(BaseModel):
    sandbox_id: str = Field(..., description="新建沙箱的唯一 ID")
    mount_path: str = Field(..., description="容器内挂载路径 /tmp")


class WriteFileInput(BaseModel):
    sandbox_id: str = Field(..., description="目标沙箱 ID")
    path: str = Field(..., description="容器内绝对路径，如 /tmp/app/main.py")
    content: str = Field(..., description="写入文件的文本内容")


class RunCommandInput(BaseModel):
    sandbox_id: str = Field(..., description="目标沙箱 ID")
    cmd: str = Field(..., description="在容器内执行的命令")
    timeout_sec: int = Field(120, description="超时时间（秒）")
    user: str = Field("root", description="执行用户，默认 root")


class RunCommandOutput(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class KillSandboxInput(BaseModel):
    sandbox_id: str = Field(..., description="目标沙箱 ID")


class KillSandboxOutput(BaseModel):
    success: bool


# =====================
# 具体工具实现
# =====================

@tool("create_sandbox")
def create_sandbox() -> CreateSandboxOutput:
    """创建一个隔离的 Python 3.11 Docker 沙箱，返回 sandbox_id 与挂载路径。"""
    sbx = make_sandbox(network="xben-001-24_default")
    sandbox_id = uuid.uuid4().hex
    _SANDBOXES[sandbox_id] = sbx
    
    global _LAST_SANDBOX_ID
    _LAST_SANDBOX_ID = sandbox_id
    
    return CreateSandboxOutput(sandbox_id=sandbox_id, mount_path="/tmp")


@tool("write_file")
def write_file(path: str, content: str, sandbox_id: Optional[str] = None) -> str:
    """向沙箱写文件；路径需位于 /tmp 下。未提供 sandbox_id 时使用最近创建的沙箱或唯一沙箱。

    参数:
    - path: 容器内绝对路径（如 /tmp/app.py 或 app.py）
    - content: 写入内容
    - sandbox_id: 可选，目标沙箱 ID
    
    注意：如果路径不是以 /tmp 开头，会自动修正为 /tmp/文件名
    """
    # 路径验证和自动修正
    path = path.strip()
    
    # 如果路径不是以 /tmp 开头，进行修正
    if not path.startswith("/tmp"):
        # 如果是绝对路径（以 / 开头），提取文件名并放到 /tmp 下
        if path.startswith("/"):
            filename = os.path.basename(path)
            path = f"/tmp/{filename}"
            print(f"[SANDBOX] 路径已自动修正: {path}")
        # 如果是相对路径，直接放到 /tmp 下
        else:
            path = f"/tmp/{path}"
            print(f"[SANDBOX] 路径已自动修正: {path}")
    
    # 确保路径以 /tmp 开头
    if not path.startswith("/tmp/"):
        path = f"/tmp/{os.path.basename(path)}"
    
    sbx = _resolve_sandbox(sandbox_id)
    sbx.files.write(path, content)
    return f"ok: 文件已写入 {path}"


@tool("run_command")
def run_command(
    cmd: str, 
    timeout_sec: int = 120, 
    user: str = "root", 
    sandbox_id: Optional[str] = None
) -> RunCommandOutput:
    """在沙箱内执行命令，返回 exit_code、stdout、stderr。未提供 sandbox_id 时使用最近创建的沙箱或唯一沙箱。

    参数:
    - cmd: 在容器内执行的命令
    - timeout_sec: 超时（秒）
    - user: 执行用户
    - sandbox_id: 可选，目标沙箱 ID
    """
    sbx = _resolve_sandbox(sandbox_id)
    r = sbx.commands.run(cmd, timeout=timeout_sec, user=user)
    return RunCommandOutput(exit_code=r.exit_code, stdout=r.stdout, stderr=r.stderr)


@tool("kill_sandbox")
def kill_sandbox(sandbox_id: Optional[str] = None) -> KillSandboxOutput:
    """销毁并清理沙箱。未提供 sandbox_id 时销毁最近创建的沙箱或唯一沙箱。"""
    sbx = _resolve_sandbox(sandbox_id)
    try:
        sbx.kill()
        # 从注册表移除
        global _LAST_SANDBOX_ID
        to_remove = None
        for k, v in list(_SANDBOXES.items()):
            if v is sbx:
                to_remove = k
                break
        if to_remove:
            _SANDBOXES.pop(to_remove, None)
            if _LAST_SANDBOX_ID == to_remove:
                _LAST_SANDBOX_ID = None
        return KillSandboxOutput(success=True)
    except Exception:
        return KillSandboxOutput(success=False)


def get_sandbox_tools():
    """返回一组可供 LLM 调用的沙箱工具。"""
    # 移除 create_sandbox 和 kill_sandbox，只保留使用沙箱的工具
    return [write_file, run_command]


# =====================
# 便捷检查函数
# =====================

def has_sandbox(sandbox_id: str) -> bool:
    """检查 sandbox_id 是否存在。"""
    return sandbox_id in _SANDBOXES


def get_preset_sandbox_id() -> Optional[str]:
    """获取当前预设的 sandbox_id。"""
    return _PRESET_SANDBOX_ID


def list_sandboxes() -> List[str]:
    """列出所有已注册的 sandbox_id。"""
    return list(_SANDBOXES.keys())


def set_preset_sandbox_id(sandbox_id: Optional[str], allow_missing: bool = True) -> None:
    """设置预设的 sandbox_id，所有工具调用将优先使用此 ID。
    
    设置后会自动尝试连接 Docker 容器。

    参数:
    - sandbox_id: 要预设的 sandbox_id，如果为 None 则清除预设
    - allow_missing: 如果为 True，允许设置一个尚未注册的 sandbox_id（可能是外部创建的）
    """
    global _PRESET_SANDBOX_ID
    if sandbox_id:
        if not allow_missing and sandbox_id not in _SANDBOXES:
            available = list_sandboxes()
            raise ValueError(
                f"预设的 sandbox_id 不存在: {sandbox_id}\n"
                f"当前已注册的 sandbox_id: {available if available else '(无)'}"
            )
        _PRESET_SANDBOX_ID = sandbox_id
        
        # 如果不在注册表中，尝试立即连接
        if sandbox_id not in _SANDBOXES:
            try:
                client = get_docker_client()
                if client:
                    try:
                        # 尝试通过完整 ID 或短 ID 查找容器
                        try:
                            container = client.containers.get(sandbox_id)
                        except Exception:
                            short_id = sandbox_id[:12]
                            container = client.containers.get(short_id)
                        
                        # 从已存在的容器创建 DockerSandbox
                        # 不再需要获取挂载路径，直接在容器内操作
                        container.reload()
                        print(f"[SANDBOX] 连接到容器: {container.id[:12]} (状态: {container.status})")

                        # 直接创建 DockerSandbox，不需要 workdir
                        sbx = DockerSandbox(container, host_workdir=None)

                        # 注册到 _SANDBOXES
                        _SANDBOXES[sandbox_id] = sbx
                        global _LAST_SANDBOX_ID
                        _LAST_SANDBOX_ID = sandbox_id
                        print(f"[SANDBOX] 从已存在的 Docker 容器连接并注册 sandbox: {sandbox_id}")
                    except Exception as e:
                        print(f"[SANDBOX] 已设置预设 sandbox_id: {sandbox_id} (注意：此 ID 尚未在当前进程中注册，将在首次使用时尝试连接)")
                        print(f"[SANDBOX] 连接尝试失败: {e}")
            except Exception as e:
                print(f"[SANDBOX] 已设置预设 sandbox_id: {sandbox_id} (注意：无法获取 Docker 客户端，将在首次使用时尝试连接)")
        else:
            print(f"[SANDBOX] 已设置预设 sandbox_id: {sandbox_id}")
    else:
        _PRESET_SANDBOX_ID = None
        print("[SANDBOX] 已清除预设 sandbox_id")

