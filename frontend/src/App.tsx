import {
  AppstoreOutlined,
  ClockCircleOutlined,
  HistoryOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Checkbox, ConfigProvider, Layout, Menu, Modal, Radio, Space, Spin, Typography, message } from "antd";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, matchPath, useLocation, useNavigate } from "react-router-dom";

import { api, connectEvents } from "./api/client";
import type { ConnectionState } from "./api/client";
import type { AppSettings, Task, ToolMetadata } from "./api/types";
import { ConnectionStatus } from "./components/ConnectionStatus";
import ToolPage from "./pages/ToolPage";

const ActivityPage = lazy(() => import("./pages/ActivityPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const ToolCenterPage = lazy(() => import("./pages/ToolCenterPage"));

const { Header, Sider, Content } = Layout;
const { Text } = Typography;
const activeStatuses = new Set(["pending", "running", "paused", "cancelling"]);

function sortActive(tasks: Task[]): Task[] {
  const priority: Record<string, number> = { running: 0, paused: 1, cancelling: 2, pending: 3 };
  return tasks.sort((a, b) =>
    (priority[a.status] ?? 9) - (priority[b.status] ?? 9) || a.created_at.localeCompare(b.created_at));
}

function mergeActive(current: Task[], updates: Task[]): Task[] {
  const byId = new Map(current.map((task) => [task.id, task]));
  for (const task of updates) {
    const previous = byId.get(task.id);
    if (previous && previous.revision >= task.revision) continue;
    if (activeStatuses.has(task.status)) byId.set(task.id, task);
    else byId.delete(task.id);
  }
  return sortActive(Array.from(byId.values()));
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [tools, setTools] = useState<ToolMetadata[]>([]);
  const [loadingTools, setLoadingTools] = useState(true);
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [historyRevision, setHistoryRevision] = useState(0);
  const [conflictAction, setConflictAction] = useState<"skip" | "overwrite" | "rename">("skip");
  const [applyRemaining, setApplyRemaining] = useState(false);
  const [resolvingConflict, setResolvingConflict] = useState(false);
  const pendingEvents = useRef<Map<string, Task>>(new Map());
  const animationFrame = useRef<number | null>(null);

  const refreshActive = useCallback(async () => {
    try {
      setActiveTasks(await api.activeTasks());
    } catch {
      // The real-time channel owns connection state; a single REST failure must not flip it.
    }
  }, []);

  const handleTaskChanged = useCallback((task: Task) => {
    setActiveTasks((current) => mergeActive(current, [task]));
    if (!activeStatuses.has(task.status)) setHistoryRevision((value) => value + 1);
  }, []);

  useEffect(() => {
    api.tools().then(setTools).catch(() => setTools([])).finally(() => setLoadingTools(false));
    api.settings().then(setSettings).catch(() => setSettings(null));
    refreshActive();
    const disconnect = connectEvents(
      (event) => {
        if (!event.task) return;
        pendingEvents.current.set(event.task.id, event.task);
        if (!activeStatuses.has(event.task.status)) setHistoryRevision((value) => value + 1);
        if (animationFrame.current === null) {
          animationFrame.current = window.requestAnimationFrame(() => {
            const updates = Array.from(pendingEvents.current.values());
            pendingEvents.current.clear();
            animationFrame.current = null;
            setActiveTasks((current) => mergeActive(current, updates));
          });
        }
      },
      (state) => {
        setConnection(state);
        if (state === "connected") refreshActive();
      },
    );
    return () => {
      disconnect();
      if (animationFrame.current !== null) window.cancelAnimationFrame(animationFrame.current);
    };
  }, [refreshActive]);

  const toolMatch = matchPath("/tools/:toolId", location.pathname);
  const toolId = toolMatch?.params.toolId;
  const currentTool = tools.find((tool) => tool.id === toolId);
  const reuseTaskId = new URLSearchParams(location.search).get("reuse");
  const selectedMenu = location.pathname.startsWith("/tools") ? "tools"
    : location.pathname.startsWith("/activity") ? "activity"
      : location.pathname.startsWith("/history") ? "history" : "settings";
  const currentMeta = currentTool
    ? { section: currentTool.category, title: currentTool.name }
    : location.pathname === "/tools" ? { section: "工具", title: "工具中心" }
      : selectedMenu === "activity" ? { section: "任务管理", title: "活动中心" }
        : selectedMenu === "history" ? { section: "任务管理", title: "执行历史" }
          : { section: "应用", title: "设置" };
  const conflictTask = activeTasks.find((task) => task.pending_conflict);
  const conflict = conflictTask?.pending_conflict ?? null;

  useEffect(() => {
    setConflictAction("skip");
    setApplyRemaining(false);
  }, [conflict?.id]);

  const resolveConflict = async () => {
    if (!conflictTask || !conflict) return;
    setResolvingConflict(true);
    try {
      const updated = await api.resolveConflict(conflictTask.id, conflict.id, conflictAction, applyRemaining ? "remaining" : "current");
      handleTaskChanged(updated);
      message.success("冲突已处理，任务继续运行");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setResolvingConflict(false);
    }
  };

  return (
    <ConfigProvider theme={{ token: { colorPrimary: "#2563eb", borderRadius: 12, colorBgLayout: "#f4f7fb", fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif', motion: false } }}>
      <Layout className="app-shell">
        <Sider breakpoint="lg" collapsedWidth="0" className="sidebar" width={232}>
          <div className="brand"><div className="brand-mark">T</div><div><strong>自动化工具箱</strong><small>LOCAL AUTOMATION</small></div></div>
          <Menu
            mode="inline"
            selectedKeys={[selectedMenu]}
            onClick={({ key }) => navigate(key === "tools" ? "/tools" : `/${key}`)}
            items={[
              { key: "tools", icon: <AppstoreOutlined />, label: "工具中心" },
              { key: "activity", icon: <ClockCircleOutlined />, label: "活动中心" },
              { key: "history", icon: <HistoryOutlined />, label: "执行历史" },
              { key: "settings", icon: <SettingOutlined />, label: "设置" },
            ]}
          />
          <div className="sidebar-foot"><ConnectionStatus state={connection} compact /></div>
        </Sider>
        <Layout className="app-main-layout">
          <Header className="topbar">
            <div><Text type="secondary">{currentMeta.section} / </Text><Text strong>{currentMeta.title}</Text></div>
            <Space>
              <ConnectionStatus state={connection} />
              <Button className="mobile-task-button" icon={<ClockCircleOutlined />} onClick={() => navigate("/activity")}>活动 {activeTasks.length}</Button>
            </Space>
          </Header>
          <Content className="main-content">
            <Suspense fallback={<div className="page-loading"><Spin size="large" /></div>}>
              <Routes>
                <Route path="/" element={<Navigate to="/tools" replace />} />
                <Route path="/tools" element={<ToolCenterPage tools={tools} onOpen={(id) => navigate(`/tools/${id}`)} />} />
                <Route path="/tools/:toolId" element={
                  <ToolPage
                    tool={currentTool}
                    settings={settings}
                    reuseTaskId={reuseTaskId}
                    loadingTools={loadingTools}
                    onTaskChanged={handleTaskChanged}
                    onBack={() => navigate("/tools")}
                  />
                } />
                <Route path="/activity" element={<ActivityPage tasks={activeTasks} tools={tools} maxWorkers={settings?.max_workers ?? 1} onTaskChanged={handleTaskChanged} onRefresh={refreshActive} />} />
                <Route path="/history" element={<HistoryPage revision={historyRevision} tools={tools} onReuse={(task) => navigate(`/tools/${task.tool_id}?reuse=${task.id}`)} onTaskCreated={handleTaskChanged} />} />
                <Route path="/settings" element={<SettingsPage settings={settings} onChanged={setSettings} />} />
                <Route path="*" element={<Navigate to="/tools" replace />} />
              </Routes>
            </Suspense>
          </Content>
        </Layout>
        <Modal title="目标文件已存在" open={Boolean(conflict)} closable={false} maskClosable={false} keyboard={false} okText="确认并继续" cancelButtonProps={{ style: { display: "none" } }} confirmLoading={resolvingConflict} onOk={resolveConflict}>
          {conflict ? <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <div><Text type="secondary">源文件</Text><div className="conflict-path">{conflict.source_path}</div></div>
            <div><Text type="secondary">目标文件</Text><div className="conflict-path">{conflict.target_path}</div></div>
            <Radio.Group value={conflictAction} onChange={(event) => setConflictAction(event.target.value)}><Space direction="vertical">
              <Radio value="skip">跳过并记录（默认）</Radio><Radio value="overwrite">覆盖目标文件</Radio><Radio value="rename">自动添加递增编号</Radio>
            </Space></Radio.Group>
            <Checkbox checked={applyRemaining} onChange={(event) => setApplyRemaining(event.target.checked)}>应用到本任务后续全部冲突</Checkbox>
          </Space> : null}
        </Modal>
      </Layout>
    </ConfigProvider>
  );
}
