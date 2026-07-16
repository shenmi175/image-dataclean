import {
  AppstoreOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  SettingOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import { Button, ConfigProvider, Drawer, Layout, Menu, Space, Spin, Tag, Typography } from "antd";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";

import { api, connectEvents } from "./api/client";
import type { AppSettings, Task, ToolMetadata } from "./api/types";
import { TaskCenter } from "./components/TaskCenter";
import ToolPage from "./pages/ToolPage";

const loadActivityPage = () => import("./pages/ActivityPage");
const loadHistoryPage = () => import("./pages/HistoryPage");
const loadSettingsPage = () => import("./pages/SettingsPage");
const ActivityPage = lazy(loadActivityPage);
const HistoryPage = lazy(loadHistoryPage);
const SettingsPage = lazy(loadSettingsPage);

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

type PageKey = "video-frames" | "activity" | "history" | "settings";

const activeStatuses = new Set(["pending", "running", "paused", "cancelling"]);

function sortActive(tasks: Task[]): Task[] {
  const priority: Record<string, number> = { running: 0, paused: 1, cancelling: 2, pending: 3 };
  return tasks.sort(
    (a, b) =>
      (priority[a.status] ?? 9) - (priority[b.status] ?? 9) ||
      a.created_at.localeCompare(b.created_at),
  );
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

const pageMeta: Record<PageKey, { section: string; title: string }> = {
  "video-frames": { section: "媒体处理", title: "视频转图片" },
  activity: { section: "任务管理", title: "活动中心" },
  history: { section: "任务管理", title: "执行历史" },
  settings: { section: "应用", title: "设置" },
};

export default function App() {
  const [page, setPage] = useState<PageKey>("video-frames");
  const [tools, setTools] = useState<ToolMetadata[]>([]);
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [connected, setConnected] = useState(false);
  const [mobileTasks, setMobileTasks] = useState(false);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [reuseDraft, setReuseDraft] = useState<{
    key: string;
    params: Record<string, unknown>;
  } | null>(null);
  const pendingEvents = useRef<Map<string, Task>>(new Map());
  const animationFrame = useRef<number | null>(null);

  const refreshActive = useCallback(async () => {
    try {
      setActiveTasks(await api.activeTasks());
    } catch {
      setConnected(false);
    }
  }, []);

  const handleTaskChanged = useCallback((task: Task) => {
    setActiveTasks((current) => mergeActive(current, [task]));
    if (!activeStatuses.has(task.status)) setHistoryRevision((value) => value + 1);
  }, []);

  useEffect(() => {
    api.tools().then(setTools).catch(() => setTools([]));
    api.settings().then(setSettings).catch(() => setSettings(null));
    refreshActive();
    const preload = window.setTimeout(() => {
      void loadActivityPage();
      void loadHistoryPage();
      void loadSettingsPage();
    }, 800);
    const disconnect = connectEvents(
      (event) => {
        if (!event.task) return;
        pendingEvents.current.set(event.task.id, event.task);
        if (!activeStatuses.has(event.task.status)) {
          setHistoryRevision((value) => value + 1);
        }
        if (animationFrame.current === null) {
          animationFrame.current = window.requestAnimationFrame(() => {
            const updates = Array.from(pendingEvents.current.values());
            pendingEvents.current.clear();
            animationFrame.current = null;
            setActiveTasks((current) => mergeActive(current, updates));
          });
        }
      },
      (isConnected) => {
        setConnected(isConnected);
        if (isConnected) refreshActive();
      },
    );
    return () => {
      window.clearTimeout(preload);
      disconnect();
      if (animationFrame.current !== null) window.cancelAnimationFrame(animationFrame.current);
    };
  }, [refreshActive]);

  const openWithHistoryParams = (task: Task) => {
    setReuseDraft({ key: `${task.id}:${Date.now()}`, params: task.params });
    setPage("video-frames");
  };

  const currentMeta = pageMeta[page];
  const currentTool = tools.find((tool) => tool.id === "video-frames");

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#2563eb",
          borderRadius: 12,
          colorBgLayout: "#f4f7fb",
          fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif',
          motion: false,
        },
      }}
    >
      <Layout className="app-shell">
        <Sider breakpoint="lg" collapsedWidth="0" className="sidebar" width={232}>
          <div className="brand">
            <div className="brand-mark">T</div>
            <div>
              <strong>自动化工具箱</strong>
              <small>LOCAL AUTOMATION</small>
            </div>
          </div>
          <Menu
            mode="inline"
            selectedKeys={[page]}
            defaultOpenKeys={["tools"]}
            onClick={({ key }) => setPage(key as PageKey)}
            items={[
              {
                key: "tools",
                icon: <AppstoreOutlined />,
                label: "工具",
                children: [{ key: "video-frames", icon: <VideoCameraOutlined />, label: "视频转图片" }],
              },
              { key: "activity", icon: <ClockCircleOutlined />, label: "活动中心" },
              { key: "history", icon: <HistoryOutlined />, label: "执行历史" },
              { key: "settings", icon: <SettingOutlined />, label: "设置" },
            ]}
          />
          <div className="sidebar-foot">
            <Tag icon={<CheckCircleFilled />} color={connected ? "success" : "error"}>
              {connected ? "实时通道已连接" : "正在重新连接"}
            </Tag>
          </div>
        </Sider>
        <Layout>
          <Header className="topbar">
            <div>
              <Text type="secondary">{currentMeta.section} / </Text>
              <Text strong>{currentMeta.title}</Text>
            </div>
            <Space>
              <Tag icon={<CheckCircleFilled />} color={connected ? "success" : "error"}>
                {connected ? "后端已连接" : "连接中断"}
              </Tag>
              <Button
                className="mobile-task-button"
                icon={<MenuFoldOutlined />}
                onClick={() => setMobileTasks(true)}
              >
                活动 {activeTasks.length}
              </Button>
            </Space>
          </Header>
          <Content className="main-content">
            <Suspense fallback={<div className="page-loading"><Spin size="large" /></div>}>
              {page === "video-frames" ? (
                <ToolPage
                  tool={currentTool}
                  activeTasks={activeTasks}
                  settings={settings}
                  reuseDraft={reuseDraft}
                  onTaskChanged={handleTaskChanged}
                  onRefresh={refreshActive}
                  onOpenActivity={() => setPage("activity")}
                />
              ) : null}
              {page === "activity" ? (
                <ActivityPage
                  tasks={activeTasks}
                  maxWorkers={settings?.max_workers ?? 1}
                  onTaskChanged={handleTaskChanged}
                  onRefresh={refreshActive}
                />
              ) : null}
              {page === "history" ? (
                <HistoryPage
                  revision={historyRevision}
                  onReuse={openWithHistoryParams}
                  onTaskCreated={handleTaskChanged}
                />
              ) : null}
              {page === "settings" ? (
                <SettingsPage settings={settings} onChanged={setSettings} />
              ) : null}
            </Suspense>
          </Content>
        </Layout>
        <Drawer
          title="活动中心"
          open={mobileTasks}
          onClose={() => setMobileTasks(false)}
          width="92%"
          destroyOnHidden
        >
          {mobileTasks ? <TaskCenter tasks={activeTasks} onChanged={handleTaskChanged} /> : null}
        </Drawer>
      </Layout>
    </ConfigProvider>
  );
}
