import { AppstoreOutlined, ArrowLeftOutlined, ArrowRightOutlined, PictureOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Button, Card, Result, Spin, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { AppSettings, Task, ToolMetadata } from "../api/types";
import { TaskCenter } from "../components/TaskCenter";
import { ToolForm } from "../components/ToolForm";

const { Title, Paragraph, Text } = Typography;

type Props = {
  tool?: ToolMetadata;
  tools: ToolMetadata[];
  activeTasks: Task[];
  settings: AppSettings | null;
  reuseTaskId: string | null;
  loadingTools: boolean;
  onTaskChanged: (task: Task) => void;
  onRefresh: () => void;
  onOpenActivity: () => void;
  onBack: () => void;
};

export default function ToolPage({
  tool,
  tools,
  activeTasks,
  settings,
  reuseTaskId,
  loadingTools,
  onTaskChanged,
  onRefresh,
  onOpenActivity,
  onBack,
}: Props) {
  const [reuseParams, setReuseParams] = useState<Record<string, unknown> | null>(null);
  const [loadingReuse, setLoadingReuse] = useState(false);

  useEffect(() => {
    if (!reuseTaskId || !tool) {
      setReuseParams(null);
      return;
    }
    let cancelled = false;
    setLoadingReuse(true);
    api.task(reuseTaskId)
      .then((task) => {
        if (cancelled) return;
        if (task.tool_id !== tool.id) throw new Error("历史任务与当前工具不匹配");
        setReuseParams(task.params);
      })
      .catch((error) => {
        if (!cancelled) message.error(`无法复用历史参数：${(error as Error).message}`);
      })
      .finally(() => {
        if (!cancelled) setLoadingReuse(false);
      });
    return () => { cancelled = true; };
  }, [reuseTaskId, tool]);

  const initialValues = useMemo(
    () => ({
      ...(tool?.id === "video-frames" ? settings?.video_frames ?? {} : {}),
      ...(settings?.default_output_dir ? { output_dir: settings.default_output_dir } : {}),
      ...(reuseParams ?? {}),
    }),
    [reuseParams, settings, tool?.id],
  );
  const heroIcon =
    tool?.id === "video-frames" ? <VideoCameraOutlined />
      : tool?.id === "image-rgb-ir-classifier" ? <PictureOutlined />
        : <AppstoreOutlined />;

  if (!tool && loadingTools) return <div className="page-loading"><Spin size="large" /></div>;
  if (!tool) {
    return <Result status="404" title="工具不存在" subTitle="该工具可能已被移除或链接有误。" extra={<Button type="primary" onClick={onBack}>返回工具中心</Button>} />;
  }

  return (
    <div className="workspace tool-workspace">
      <main className="tool-column">
        <section className="hero">
          <div className="hero-icon">
            {heroIcon}
          </div>
          <div>
            <Button type="link" className="tool-back" icon={<ArrowLeftOutlined />} onClick={onBack}>
              返回工具中心
            </Button>
            <Title level={2}>{tool?.name ?? "自动化工具"}</Title>
            <Paragraph>
              {tool?.description ?? "配置参数并在后台执行任务。"}
            </Paragraph>
          </div>
        </section>
        <Card className="form-card" title="任务参数" bordered={false}>
          {tool && settings && !loadingReuse ? (
            <ToolForm
              key={`${tool.id}:${reuseTaskId ?? "default"}:${JSON.stringify(initialValues)}`}
              tool={tool}
              initialOverrides={initialValues}
              onCreated={onTaskChanged}
            />
          ) : (
            <Text type="secondary">正在加载工具定义或历史参数…</Text>
          )}
        </Card>
      </main>
      <aside className="task-column">
        <div className="panel-heading">
          <div>
            <Title level={4}>当前活动</Title>
            <Text type="secondary">{activeTasks.length} 个活动任务</Text>
          </div>
          <Button size="small" onClick={onRefresh}>
            刷新
          </Button>
        </div>
        <TaskCenter tasks={activeTasks} tools={tools} onChanged={onTaskChanged} compact />
        {activeTasks.length > 6 ? (
          <Button type="link" icon={<ArrowRightOutlined />} onClick={onOpenActivity} block>
            查看全部活动
          </Button>
        ) : null}
      </aside>
    </div>
  );
}
