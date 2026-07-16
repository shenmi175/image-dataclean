# 自动化工具箱

本项目是一个本地优先、前后端分离的桌面自动化工具箱。首个可用工具为“视频转图片”，支持多文件或递归目录输入、任务级并行、暂停/恢复/取消/重试、实时活动中心、执行历史和持久化设置。

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
sudo apt install ./dist/automation-toolbox_0.2.0_amd64.deb
```

目标系统需提供 GTK/WebKit 系统运行库：

```bash
sudo apt install python3-gi gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0
```

任务状态保存在 `data/toolbox.sqlite3`。应用异常退出后，未完成任务会标记为“已中断”，已生成的图片不会被删除。

## 平台依赖说明

Python 和 Node 包均保存在项目目录。pywebview 使用操作系统 WebView，因此仍需要平台提供系统运行库：Windows 使用 WebView2；Linux 需要 GTK/WebKit2 或 Qt；macOS 使用系统 WebKit。这些系统组件不能放入 Python 虚拟环境。
