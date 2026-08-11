# 自动化工具箱

本项目是一个本地优先、前后端分离的桌面自动化工具箱。内置数据清理、媒体处理、图像分类、标注转换、数据集划分、合并和可视化工具，支持任务级并行、暂停/恢复/取消/重试、实时活动中心、执行历史和持久化设置。

- React + TypeScript：响应式操作台
- FastAPI：本地 API 和 SSE 实时事件流
- pywebview：桌面窗口
- Python multiprocessing：隔离执行后台任务
- SQLite：任务与历史状态持久化

完整设计见 [架构文档](docs/architecture.md)。

## 支持范围与初始化

官方二进制目前只支持 **Ubuntu 24.04 amd64**。源码开发固定使用 Python
3.12、uv 锁文件和 pnpm 锁文件；主应用与模型 Provider 各有独立依赖环境，
PyTorch/Transformers 不会安装进主应用。

项目依赖安装在仓库内部：Python 使用 `.venv`，前端使用 `frontend/node_modules`。

```bash
./scripts/bootstrap.sh
```

主应用依赖由根目录 `uv.lock` 管理；模型组件依赖由
`components/dinov3-provider/uv.lock` 独立管理。不要用一个环境覆盖另一个锁文件。

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
sudo apt install ./dist/automation-toolbox_0.4.0_amd64.deb
```

建议使用 `.deb`，APT 会自动安装 GTK/WebKit 运行库。便携 tar 包仍要求 Ubuntu
24.04 amd64，并需要系统已有 `python3-gi`、`libgtk-3-0t64`、
`gir1.2-webkit2-4.1` 和 `libwebkit2gtk-4.1-0`。

开发环境的任务状态保存在 `data/toolbox.sqlite3`；安装包默认使用
`~/.local/share/automation-toolbox/data/toolbox.sqlite3`。应用异常退出后，未完成任务会标记为“已中断”，已生成的图片不会被删除。

## 并行处理

工具箱同时支持“多个任务并发”和“单个任务内部并行”。设置页中的单任务并行线程数默认为 `0`，表示根据可用 CPU 核数和最大并发任务数自动平衡；每个任务表单也可以单独覆盖为 `1-32`，其中 `1` 可用于强制串行排查问题。

图像分类、标注转换、数据集处理和可视化按文件并行。视频抽帧保持顺序解码，并使用有界流水线并行缩放和 JPEG 编码，避免一次缓存过多高分辨率帧。输出文件命名、manifest 和报告顺序不受线程完成顺序影响。

## RGB / 红外候选分类

分类工具按像素的 RGB 通道差异识别彩色图和灰度/红外候选图。默认递归扫描，复制源文件，并为输出目录和文件添加 `_rgb` 或 `_ir` 后缀。普通灰度图也会归入红外候选；该工具不等同于红外成像模型。

## DINOv3 视频帧清理

数据清理专区使用 `facebook/dinov3-vits16-pretrain-lvd1689m` 提取图像特征，按自然文件名顺序动态选择代表帧。默认在每个目录内比较、阈值为 `0.95`，并把保留帧复制到任务目录的 `cleaned/` 下；也可切换为全目录比较。

主程序不再导入 PyTorch、Transformers 或直接加载模型。首次提交 DINOv3
任务时，界面会要求阅读并明确接受独立的 DINOv3 License；随后主程序从同版本
GitHub Release 匿名下载 CPU Provider，校验 GitHub 资产 SHA-256 后解包。Provider
再从固定 ModelScope 地址匿名下载固定 revision 的四个模型文件，并逐文件校验大小
和 SHA-256。默认安装位置为：

```text
~/.local/share/automation-toolbox/components/dinov3-cpu/0.1.0/
~/.local/share/automation-toolbox/models/dinov3-vits16-pretrain-lvd1689m/<revision>/
```

主程序与 Provider 通过版本化 NDJSON/stdin-stdout 协议交换特征，不共享 Python
环境。后续模型只需实现同一 Provider 协议并增加组件描述，不需要把模型运行时重新
打进主应用。当前 Provider 仅支持 CPU；CUDA 组件应作为另一份独立 Release Asset。

模型权重和 DINOv3 License 不属于本项目 MIT 许可范围。许可证文本会随下载的模型
保存；许可证摘要变化后，应用会要求重新确认。

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

## GitHub Release 与签名标签

推送 `v*` 标签会触发 `.github/workflows/release.yml`，在 Ubuntu 24.04 amd64
重新测试并构建以下 Release Assets：

- `.deb` 安装包和主程序便携 tar 包
- 独立 DINOv3 CPU Provider tar 包
- `components-v1.json` 组件目录
- 主程序/Provider CycloneDX 1.5 SBOM
- `SHA256SUMS`，以及 GitHub artifact provenance attestation

上传使用工作流自动提供、仅授予当前仓库 `contents: write` 的 `GITHUB_TOKEN`，不需要
PAT 或私钥。发布工作流只接受已经存在且通过 SSH 验证的标签：将签名公钥（例如
`ssh-ed25519 AAAA...`）保存为仓库 Actions variable
`RELEASE_SIGNING_PUBLIC_KEY`，私钥始终只保存在发布者机器或硬件密钥中。

本地配置和发布：

```bash
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
./scripts/create-signed-tag.sh
git push origin v0.4.0
```

验证下载内容：

```bash
sha256sum -c SHA256SUMS
gh attestation verify automation-toolbox_0.4.0_amd64.deb --repo shenmi175/image-dataclean
```

历史 `.deb` 不应继续提交到 Git/LFS；发布物统一保存在对应 GitHub Release。项目源码
采用 [MIT License](LICENSE)，第三方与模型许可边界见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
