# 多Agent安全测试系统

Authors: 杨旭YANGXU、HackingHUI 中国科学技术大学网络信息中心
杨旭YANGXU 2026.06 毕业，正在寻找工作。如果您有工作机会，非常感谢您能和我联系yyy1mu@qq.com

这是一个基于多Agent架构的自动化安全测试系统. 该项目是参加腾讯智能挑战赛的代码, 测试集为xbow-benchmark, 在比赛中拿到flag的通过率为60%左右, 现在代码中还有诸多bug,不过代码能正常直接运行.

## 项目结构

```
sub-agent-autopt/
├── main.py                 # 主入口文件
├── agents/                 # Agent模块
│   ├── __init__.py
│   ├── coordinator.py     # 协调Agent（主协调者）
│   ├── planner.py         # 规划Agent（负责生成待办清单）
│   └── executor.py        # 执行Agent（负责执行具体任务）
├── config/                # 配置模块
│   ├── __init__.py
│   └── llm_config.py      # LLM配置管理
├── utils/                 # 工具模块
│   ├── __init__.py
│   ├── state_manager.py   # 状态管理
│   └── finding_extractor.py  # 发现提取
├── tools/                 # 工具模块（Agent使用的工具）
│   ├── __init__.py
│   ├── curl_tools.py      # HTTP请求工具（curl封装）
│   └── sandbox_tools.py  # 沙箱工具（需要单独创建）
├── pyproject.toml         # Poetry配置文件
└── README.md
```

## Agent架构说明

### 1. CoordinatorAgent (协调Agent)
- **职责**: 主协调者，负责整体流程控制
- **功能**:
  - 管理执行循环
  - 协调规划Agent和执行Agent
  - 状态管理和更新
  - 发现提取和汇总
  - 动态重新规划

### 2. PlannerAgent (规划Agent)
- **职责**: 生成和更新待办清单
- **功能**:
  - 初始规划：根据目标生成初始待办清单
  - 动态规划：根据当前状态、发现和历史重新规划
  - 上下文格式化：为规划准备上下文信息

### 3. ExecutorAgent (执行Agent)
- **职责**: 执行具体的测试任务
- **功能**:
  - 执行单个待办任务
  - 调用工具（sandbox_tools, curl_tools）
  - 返回执行结果

## 工具模块 (tools/)

工具模块位于 `tools/` 目录，包含Agent在执行任务时使用的各种工具。

### tools/curl_tools.py
提供HTTP请求工具，包含两个主要工具：

1. **local_curl**: 标准化的HTTP请求工具

2. **local_curl_raw**: 原始curl命令工具
   - 更灵活的curl参数传递
   - 适合复杂场景

**使用方式**:
```python
from tools.curl_tools import get_curl_tools
tools = get_curl_tools()  # 返回 [local_curl, local_curl_raw]
```

### tools/sandbox_tools.py
提供Docker沙箱管理工具，包含四个主要工具：

1. **create_sandbox**: 创建一个隔离的 Python 3.11 Docker 沙箱
   - 返回 sandbox_id 和挂载路径
   - 自动注册到全局沙箱注册表

2. **write_file**: 向沙箱写入文件
   - 支持指定 sandbox_id 或使用默认沙箱
   - 路径需位于 /tmp 下

3. **run_command**: 在沙箱内执行命令
   - 支持超时设置
   - 支持指定执行用户
   - 返回 exit_code、stdout、stderr

4. **kill_sandbox**: 销毁并清理沙箱
   - 自动从注册表移除

**辅助函数**:
- `set_preset_sandbox_id()`: 设置预设的 sandbox_id
- `get_preset_sandbox_id()`: 获取当前预设的 sandbox_id
- `list_sandboxes()`: 列出所有已注册的 sandbox_id
- `has_sandbox()`: 检查 sandbox_id 是否存在

**使用方式**:
```python
from tools.sandbox_tools import get_sandbox_tools, set_preset_sandbox_id
tools = get_sandbox_tools()  # 返回 [create_sandbox, write_file, run_command, kill_sandbox]
```

**注意**: 此模块依赖 `docker_sandbox` 模块，需要确保该模块可用。

## 安装和设置

### 使用 Poetry（推荐）

1. **安装 Poetry**（如果尚未安装）:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. **安装项目依赖**:
```bash
# 安装所有依赖（包括开发依赖）
poetry install

# 或只安装生产依赖
poetry install --without dev
```

3. **激活虚拟环境**:
```bash
# 方式1: 进入Poetry shell（推荐）
poetry shell

# 方式2: 使用poetry run运行命令（无需激活）
poetry run python main.py
```

4. **运行项目**:
```bash
# 在Poetry shell中
python main.py

# 或直接使用poetry run
poetry run python main.py
```

5. **查看虚拟环境信息**:
```bash
poetry env info
```

6. **添加新依赖**:
```bash
poetry add package-name
poetry add --group dev package-name  # 添加开发依赖
```

7. **更新依赖**:
```bash
poetry update
```

### 使用 pip（备选）

```bash
pip install langchain langchain-openai langchain-core requests
```

## 环境变量

```bash
export OPENAI_MODEL="deepseek-chat"
export OPENAI_BASE_URL="https://api.deepseek.com"
export OPENAI_API_KEY="your-api-key"
export SANDBOX_ID="your-sandbox-id"
```

## 使用方法

```bash
python main.py
```



