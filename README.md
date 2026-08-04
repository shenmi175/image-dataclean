# 自动化工具箱

本项目是一个本地优先、前后端分离的桌面自动化工具箱。内置数据清理、媒体处理、图像分类、标注转换、数据集划分、合并和可视化工具，支持任务级并行、暂停/恢复/取消/重试、实时活动中心、执行历史和持久化设置。

- React + TypeScript：响应式操作台
- FastAPI：本地 API 和 SSE 实时事件流
- pywebview：桌面窗口
- Python multiprocessing：隔离执行后台任务
- SQLite：任务与历史状态持久化

完整设计见 [架构文档](docs/architecture.md)。

## 初始化

项目依赖安装在仓库内部：Python 使用 `.venv`，前端使用 `frontend/node_modules`。

```bash
./scripts/bootstrap.sh
```

## 启动开发环境

```bash
./start.sh dev
```

访问 `http://127.0.0.1:5173`。Vite 会把 `/api` 请求代理到本地 FastAPI。

视频任务会在所选输出根目录下创建独立的 `{时间戳}_{任务ID}` 目录。开发模式默认关闭本地 API 会话认证；桌面模式会自动生成临时令牌并启用认证。

## 启动桌面应用

```bash
./start.sh desktop
```

该命令会先构建前端，再启动 FastAPI 和 pywebview 桌面窗口。

## 测试与构建

```bash
./start.sh test
./start.sh build
```

## Ubuntu 可执行程序

在 Ubuntu 24.04 x86_64 上构建独立的 `onedir` 程序：

```bash
./start.sh package
./dist/AutomationToolbox/automation-toolbox
```

构建可从 Ubuntu 应用菜单启动的 `.deb` 安装包：

```bash
./start.sh deb
sudo apt install ./dist/automation-toolbox_0.3.1_amd64.deb
```

目标系统需提供 GTK/WebKit 系统运行库：

```bash
sudo apt install python3-gi gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0
```

任务状态保存在 `data/toolbox.sqlite3`。应用异常退出后，未完成任务会标记为“已中断”，已生成的图片不会被删除。

## 并行处理

工具箱同时支持“多个任务并发”和“单个任务内部并行”。设置页中的单任务并行线程数默认为 `0`，表示根据可用 CPU 核数和最大并发任务数自动平衡；每个任务表单也可以单独覆盖为 `1-32`，其中 `1` 可用于强制串行排查问题。

图像分类、标注转换、数据集处理和可视化按文件并行。视频抽帧保持顺序解码，并使用有界流水线并行缩放和 JPEG 编码，避免一次缓存过多高分辨率帧。输出文件命名、manifest 和报告顺序不受线程完成顺序影响。

## RGB / 红外候选分类

分类工具按像素的 RGB 通道差异识别彩色图和灰度/红外候选图。默认递归扫描，复制源文件，并为输出目录和文件添加 `_rgb` 或 `_ir` 后缀。普通灰度图也会归入红外候选；该工具不等同于红外成像模型。

## DINOv3 视频帧清理

数据清理专区使用 `facebook/dinov3-vits16-pretrain-lvd1689m` 提取图像特征，按自然文件名顺序动态选择代表帧。默认在每个目录内比较、阈值为 `0.95`，并把保留帧复制到任务目录的 `cleaned/` 下；也可切换为全目录比较。

模型首次使用时下载到项目目录 `models/dinov3-vits16-pretrain-lvd1689m/`，下载器会校验 SHA-256，Transformers 仅从该本地目录加载，不使用 ModelScope 或 Hugging Face 全局缓存。模型目录包含 DINOv3 License，使用模型即表示接受该许可证。

“原地永久删除”模式会删除源目录中的重复或高度相似帧，必须在表单中显式确认。任务会在删除前生成 `deletion_plan.csv`，完成后生成 `summary.json` 和 `decisions.csv`；建议先使用默认复制模式检查阈值和结果。

## 标注与数据集工具

- Labelme 多边形转 YOLO segmentation
- web-auto 标注导出为 Labelme 或 COCO
- COCO polygon 转 Labelme
- YOLO train/val 安全划分（不修改源数据）
- Labelme、YOLO、COCO 标注抽样可视化
- 多个 YOLO segmentation 数据集合并与类别映射

这些任务都写入独立输出目录，并生成 `summary.json`；转换、划分和合并任务还会生成逐文件 CSV 或来源 manifest。

## 新增工具

每个工具使用独立包维护，通常包含 `spec.py`（Pydantic 参数）、`executor.py`（执行逻辑）和 `__init__.py`（公开工具类）。公共能力位于 `backend/tools/common/`：

- `schemas`、`paths`：输出参数、输入存在性和嵌套输出保护
- `discovery`：按后缀递归发现文件，默认忽略符号链接
- `transfer`：原子复制/移动及统一冲突处理
- `batch`、`parallel`：暂停、取消、进度、速率、失败计数和有界线程池
- `reports`、`yolo`：JSON/CSV 报告和 YOLO 通用读写

新工具继承 `Tool`，通过 `ui_schema` 声明目录、文件、多文件、目录列表和嵌套对象控件；前端会自动生成表单。工具类在 `backend/tools/builtins.py` 增加一条引用后，会自动出现在工具中心，不需要修改菜单或页面代码。只有明确声明 `ToolCapabilities(transfer_modes=("copy", "move"))` 的归档工具才会开放移动源文件能力。

## 平台依赖说明

Python 和 Node 包均保存在项目目录。pywebview 使用操作系统 WebView，因此仍需要平台提供系统运行库：Windows 使用 WebView2；Linux 需要 GTK/WebKit2 或 Qt；macOS 使用系统 WebKit。这些系统组件不能放入 Python 虚拟环境。
