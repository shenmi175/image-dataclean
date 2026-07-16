# 自动化工具箱架构方案

> 文档状态：已采纳方案  
> 更新日期：2026-07-14  
> 适用范围：本地视频、图片及后续常用自动化任务的可视化执行平台

## 1. 目标

构建一个本地优先、前后端分离的桌面工具箱，满足以下要求：

- 用户通过响应式可视化界面配置和执行任务，不需要反复输入命令行参数。
- 多个任务互相隔离，一个任务失败、暂停或取消不会影响其他任务。
- 支持任务排队、限制并发、暂停、恢复、取消和失败重试。
- 实时显示总体进度、当前处理对象、成功/失败数量、速度和日志。
- 前端刷新或重新连接后能够恢复任务列表和进度。
- 新增工具时不修改主框架，通过统一工具协议接入。
- 开发环境一条命令启动，发布后用户双击快捷方式启动。

## 2. 架构决策

采用以下组合：

- 前端：React + TypeScript + Vite + Ant Design
- 本地后端：FastAPI + Uvicorn
- 桌面外壳：pywebview
- 参数模型与校验：Pydantic
- 任务执行：Python `multiprocessing` 独立 Worker 进程
- 状态持久化：SQLite（WAL 模式）
- 实时通信：SSE（保留 WebSocket 兼容接口）
- 构建发布：前端静态构建 + PyInstaller `onedir` + 平台安装程序

整体采用“本地优先的模块化单体”架构。前端、API、任务调度和工具执行在代码层面边界清晰；发布时仍可组合成一个桌面应用，避免过早引入 Redis、Celery、消息中间件或微服务。

## 3. 系统结构

```text
┌──────────────── 桌面启动器 / pywebview ────────────────┐
│ 管理窗口、原生文件对话框、后端生命周期和单实例         │
└───────────────────────┬───────────────────────────────┘
                        │ 加载本地页面
┌───────────────────────▼───────────────────────────────┐
│ React 操作台                                           │
│ 工具导航 │ 参数表单 │ 活动中心 │ 日志 │ 历史/设置      │
└───────────────────────┬───────────────────────────────┘
                        │ REST + SSE
┌───────────────────────▼───────────────────────────────┐
│ FastAPI 后端进程                                       │
│ API │ 工具注册表 │ 参数校验 │ 任务调度 │ 状态持久化     │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
┌─────────────▼──────────────┐   ┌─────────▼────────────┐
│ 独立 Worker 进程池          │   │ SQLite / 日志文件    │
│ Worker 1：任务 A            │   │ 状态、历史、参数快照 │
│ Worker 2：任务 B            │   │ 结果、错误、预设     │
│ Worker N：任务 N            │   └──────────────────────┘
└─────────────┬──────────────┘
              │
┌─────────────▼────────────────────────────────────────┐
│ 工具插件                                               │
│ video_frames │ image_resize │ rename │ format_convert │
└───────────────────────────────────────────────────────┘
```

### 3.1 进程职责

桌面启动器进程：

- 启动本地 FastAPI 后端并等待健康检查通过。
- 创建 pywebview 窗口并加载 React 页面。
- 提供原生目录/文件选择能力。
- 管理退出策略：立即退出、任务结束后退出或后台继续运行。

FastAPI 后端进程：

- 接收前端请求，不直接执行耗时工具逻辑。
- 校验工具参数并创建任务记录。
- 调度任务、限制并发、汇总进度和持久化状态。
- 通过 SSE 推送增量事件。

Worker 进程：

- 每个运行中任务使用独立进程上下文。
- 执行 OpenCV 或其他耗时逻辑。
- 响应暂停、恢复和取消信号。
- 报告进度、日志和结构化结果。
- 单个 Worker 崩溃不能导致 API 或其他任务退出。

## 4. 前后端通信

### 4.1 REST API

REST 用于命令操作和可恢复的状态快照：

```text
GET    /api/health
GET    /api/tools
GET    /api/tools/{tool_id}
POST   /api/tasks
GET    /api/tasks
GET    /api/tasks/{task_id}
POST   /api/tasks/{task_id}/pause
POST   /api/tasks/{task_id}/resume
POST   /api/tasks/{task_id}/cancel
POST   /api/tasks/{task_id}/retry
GET    /api/tasks/{task_id}/logs
POST   /api/dialogs/select-directory
POST   /api/dialogs/select-files
POST   /api/system/open-path
```

创建任务示例：

```json
{
  "tool_id": "video-frames",
  "params": {
    "input_dir": "/data/videos",
    "output_dir": "/data/frames",
    "frame_interval": 10,
    "resize": true,
    "width": 640,
    "height": 640,
    "resize_mode": "letterbox"
  }
}
```

后端立即返回任务 ID，不等待任务执行结束：

```json
{
  "task_id": "01J00000000000000000000000",
  "status": "pending"
}
```

### 4.2 WebSocket

WebSocket 只推送变化事件，不作为任务状态的唯一来源：

```text
WS /api/events
```

进度事件示例：

```json
{
  "type": "task.progress",
  "task_id": "01J00000000000000000000000",
  "status": "running",
  "current": 320,
  "total": 1200,
  "percent": 26.67,
  "message": "正在处理 video_03.mp4",
  "speed": 18.4,
  "success_count": 318,
  "failure_count": 2,
  "updated_at": "2026-07-14T15:30:00+08:00"
}
```

React 首次加载或 SSE 重连时，先通过 REST 拉取任务快照，再接收增量事件。这能避免页面刷新、短暂断线或窗口重开造成状态丢失。

## 5. 任务模型

### 5.1 状态机

```text
pending ──► running ──► completed
   │           │  ▲
   │           ▼  │
   │         paused
   │           │
   └───────────┴──────► cancelling ──► cancelled
               │
               └──────► failed
```

规则：

- `pending` 任务可以取消，不能暂停。
- `running` 任务可以暂停或取消。
- `paused` 任务仍占用 Worker；可恢复或取消。
- `completed`、`cancelled`、`failed` 为终态。
- 重试会创建新任务，并记录来源任务 ID，保留原任务历史。
- 应用异常退出时，原 `running`、`paused` 和 `cancelling` 任务标记为 `interrupted`；是否允许恢复由具体工具声明。

### 5.2 并发调度

- 默认并发数建议为 `min(4, max(1, CPU 核心数 / 2))`，并允许用户配置。
- OpenCV、编码转换等 CPU/磁盘密集任务应限制并发，避免并发越高反而越慢。
- 调度器只从 `pending` 队列中选择任务。
- 首版使用 FIFO；后续可增加优先级和资源标签，例如 `cpu`、`gpu`、`disk-heavy`。
- 每个任务拥有独立的暂停事件、取消事件、进度通道和日志上下文。

## 6. 暂停、恢复和取消

暂停采用协作式安全检查点，不直接冻结整个后端进程。

工具执行上下文统一提供：

```python
class TaskContext:
    def wait_if_paused(self) -> None: ...
    def raise_if_cancelled(self) -> None: ...
    def report_progress(
        self,
        current: int,
        total: int | None,
        message: str = "",
    ) -> None: ...
    def log(self, level: str, message: str) -> None: ...
```

工具应在安全位置调用检查点：

- 视频抽帧：每读取一帧或写出一帧后检查。
- 图片批处理：每处理完一张图片后检查。
- 文件复制/转换：每个文件或数据块后检查。
- 外部命令：使用独立的子进程适配器处理暂停和终止，不能假设所有平台都支持相同信号。

取消分两级：

1. 正常取消：设置取消事件，让工具释放视频句柄、文件和临时资源后退出。
2. 强制终止：超过配置的超时时间仍无响应时，只终止对应 Worker，并记录为异常取消。

“暂停”只保证停止继续处理，不保证释放 Worker 和已经打开的资源。若未来需要暂停任务不占用并发槽，应增加可序列化检查点协议，由支持该能力的工具主动保存并退出。

## 7. 工具插件协议

每个工具包含元数据、参数模型和执行器：

```python
class VideoFramesParams(BaseModel):
    input_dir: Path
    output_dir: Path
    frame_interval: int = Field(default=10, ge=1)
    resize: bool = True
    width: int = Field(default=640, gt=0)
    height: int = Field(default=640, gt=0)
    resize_mode: Literal["letterbox", "direct"] = "letterbox"


class VideoFramesTool:
    id = "video-frames"
    name = "视频抽帧"
    category = "媒体处理"
    version = "1.0.0"
    params_model = VideoFramesParams
    supports_pause = True
    supports_resume_after_restart = False

    def run(self, params: VideoFramesParams, context: TaskContext):
        ...
```

Pydantic 模型生成 JSON Schema，React 根据 Schema 渲染基础参数表单。工具可以提供 UI Schema 控制字段顺序、分组、帮助文本和控件类型；复杂工具可以注册专属 React 页面。

禁止插件：

- 直接操作 React 或 pywebview 窗口。
- 自行创建未受管理的后台线程或进程。
- 绕过任务上下文更新数据库状态。
- 向前端暴露任意命令执行接口。

## 8. 前端操作台

### 8.1 页面结构

- 左侧：工具分类、收藏和搜索。
- 中间：当前工具说明、参数表单和执行按钮。
- 右侧或底部：全局任务中心。
- 任务详情：进度、当前文件、速度、日志、错误列表和输出路径。
- 历史记录：再次执行、复制参数、打开输出目录和清理记录。

### 8.2 响应式布局

- `>= 1200px`：工具导航、主表单、任务中心三栏。
- `768px ~ 1199px`：导航和内容两栏，任务中心放到底部或抽屉。
- `< 768px`：单栏布局，导航和任务中心使用抽屉。
- 使用 CSS Grid/Flex 和内容断点，不使用固定页面宽高。
- 表单宽屏可两列，窄屏自动变成单列。

### 8.3 前端状态原则

- 服务端任务状态以 FastAPI/SQLite 为准。
- WebSocket 事件通过 `task_id` 合并进客户端缓存。
- 暂停、恢复等按钮需要处理重复点击和接口幂等。
- 断线时明确显示连接状态，但不假定后台任务已停止。

## 9. 数据持久化

SQLite 至少包含以下表：

```text
tools_cache      工具元数据缓存（可选）
tasks            任务主记录和状态
task_events      重要状态事件
task_failures    单文件或子项失败记录
presets          用户参数预设
settings         应用设置
```

`tasks` 主要字段：

```text
id, tool_id, tool_version, status, params_json,
current, total, progress, message,
success_count, failure_count,
created_at, started_at, finished_at, updated_at,
output_path, log_path, source_task_id, error_summary
```

进度事件可以高频出现在内存和 WebSocket 中，但不应每帧写 SQLite。建议满足任一条件时持久化：

- 距上次写入超过 500 毫秒；
- 进度至少变化 1%；
- 状态发生变化；
- 出现失败或关键日志。

## 10. 一键启动

### 10.1 开发环境

提供统一开发命令，同时启动：

```text
Vite 开发服务器
FastAPI/Uvicorn
pywebview 桌面窗口
```

启动器等待前后端健康检查成功后再显示窗口。开发环境允许浏览器调试，生产环境关闭调试入口。

### 10.2 生产环境

用户只需要启动一个桌面入口：

```text
Toolbox.exe / Toolbox.app / toolbox
    ├── 检查是否已有实例
    ├── 选择随机空闲端口
    ├── 生成本次会话令牌
    ├── 启动绑定 127.0.0.1 的 FastAPI
    ├── 等待 /api/health
    └── 打开 pywebview 窗口
```

建议使用 PyInstaller `onedir`，再由 Windows 安装程序、macOS 应用包或 Linux 包创建快捷方式。`onedir` 一般比 `onefile` 启动更快，也便于包含 React 静态资源、OpenCV 动态库和平台 WebView 依赖。

使用 `multiprocessing` 打包时，应用入口必须尽早调用：

```python
if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
```

关闭窗口时不应直接杀死正在运行的任务。默认弹出选择：

- 最小化到后台，任务继续执行。
- 等待任务完成后退出。
- 取消所有任务并退出。

## 11. 本地安全边界

- FastAPI 只绑定 `127.0.0.1`，不监听局域网地址。
- 每次启动生成随机会话令牌，React 的 REST 和 WebSocket 请求必须携带令牌。
- 限制 CORS 和 WebSocket Origin，只允许当前应用来源。
- 原生文件操作只暴露明确的方法，例如选择目录、打开输出目录。
- 后端必须再次校验所有参数，不能信任前端表单校验。
- 禁止提供接受任意字符串的 Shell 执行接口。
- 日志默认隐藏令牌、环境变量和可能的敏感路径。

## 12. 建议目录结构

```text
toolbox/
├── backend/
│   ├── app.py
│   ├── api/
│   │   ├── tools.py
│   │   ├── tasks.py
│   │   ├── events.py
│   │   └── system.py
│   ├── scheduler/
│   │   ├── manager.py
│   │   ├── worker.py
│   │   ├── context.py
│   │   └── models.py
│   ├── tools/
│   │   ├── registry.py
│   │   ├── video_frames/
│   │   │   ├── spec.py
│   │   │   ├── executor.py
│   │   │   └── tests/
│   │   └── image_resize/
│   │       ├── spec.py
│   │       ├── executor.py
│   │       └── tests/
│   └── infrastructure/
│       ├── database.py
│       ├── dialogs.py
│       ├── logging.py
│       └── settings.py
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── features/tools/
│   │   ├── features/tasks/
│   │   ├── pages/
│   │   └── app/
│   └── package.json
├── desktop/
│   ├── launcher.py
│   └── lifecycle.py
├── data/
├── docs/
├── tests/
├── pyproject.toml
└── package.json
```

## 13. 从现有脚本迁移

当前 `video2image.py` 同时包含 Tkinter UI、参数校验、线程和 OpenCV 逻辑。迁移时按以下顺序进行：

1. 将视频抽帧和图片缩放提取为无 UI 的纯工具模块。
2. 修复尺寸变量、输出目录创建、中文路径写入和错误吞掉等问题。
3. 为核心处理补充单元测试和小型媒体夹具。
4. 实现工具协议、注册表和 `TaskContext`。
5. 实现单 Worker 的任务创建、进度、暂停、恢复和取消。
6. 接入 SQLite 和 WebSocket，验证页面刷新后状态恢复。
7. 增加受控的多 Worker 并发和异常隔离。
8. 建立 React 操作台，首先接入视频抽帧，再接入图片转换。
9. 完成 pywebview 启动器和 PyInstaller 打包。
10. 验证 Windows/Linux 上的安装、路径、DPI、退出和任务恢复行为。

迁移期间可暂时保留旧 Tkinter 入口作为回退，但核心算法只能保留一份，由旧入口和新 Worker 共同调用，避免两套实现产生差异。

## 14. 测试与验收重点

- 同时运行多个任务，其中一个失败，其他任务继续执行。
- 暂停某个任务后，其进度停止，其他任务继续推进。
- 恢复任务后从暂停位置继续，不重复写出已完成内容。
- 取消任务后资源被释放，部分输出有明确处理策略。
- React 刷新和 WebSocket 重连后，任务状态正确恢复。
- 强制结束某个 Worker 后，后端仍可创建和执行新任务。
- 应用关闭时不会悄悄丢失正在执行的任务。
- 输出目录包含中文、空格和较长路径时读写正确。
- 多任务运行时并发数不超过配置值。
- 打包应用能够正确创建 Worker，不发生递归启动。

## 15. 暂不采用的方案

- 继续扩展 Tkinter：难以满足现代响应式布局和长期组件化维护。
- 直接通过 pywebview JS Bridge 执行任务：任务生命周期会与窗口和桥接线程耦合，不适合多任务调度。
- Electron + Python：可实现，但运行体积和进程栈更重，当前没有明显收益。
- Tauri + Python sidecar：适合后期产品化，但首版增加 Rust、跨架构 sidecar 和打包复杂度。
- Celery + Redis：当前是单机本地工具箱，运维成本高于收益。
- 微服务：当前工具共享本地文件系统和运行环境，模块化单体更简单可靠。

## 16. 后续演进

当出现以下需求时再升级：

- 多台机器协同执行：抽象任务队列和远程 Worker 协议。
- GPU 任务：加入资源标签、设备锁和显存调度。
- 应用商店、自动更新和更严格权限：评估将桌面外壳替换为 Tauri。
- 第三方插件：增加插件签名、权限声明、隔离环境和兼容性协议。
- 可恢复的超长任务：为特定工具增加持久化检查点。

React 与 FastAPI 的通信协议、任务状态机和工具协议应保持与桌面外壳解耦，因此未来替换 pywebview 不需要重写核心系统。

## 17. 参考资料

- [pywebview Application architecture](https://pywebview.flowrl.com/guide/architecture)
- [pywebview Changelog](https://pywebview.flowrl.com/changelog)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [FastAPI - Run a Server Manually](https://fastapi.tiangolo.com/deployment/manually/)
- [PyInstaller - Multi-processing](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing)
