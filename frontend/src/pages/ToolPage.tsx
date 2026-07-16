import { ArrowRightOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Button, Card, Typography } from "antd";
import { useMemo } from "react";

import type { AppSettings, Task, ToolMetadata } from "../api/types";
import { TaskCenter } from "../components/TaskCenter";
import { ToolForm } from "../components/ToolForm";

const { Title, Paragraph, Text } = Typography;

type Props = {
  tool?: ToolMetadata;
  activeTasks: Task[];
  settings: AppSettings | null;
  reuseDraft: { key: string; params: Record<string, unknown> } | null;
  onTaskChanged: (task: Task) => void;
  onRefresh: () => void;
  onOpenActivity: () => void;
};

export default function ToolPage({
  tool,
  activeTasks,
  settings,
  reuseDraft,
  onTaskChanged,
  onRefresh,
  onOpenActivity,
}: Props) {
  const initialValues = useMemo(
    () => ({
      ...(settings?.video_frames ?? {}),
      ...(settings?.default_output_dir ? { output_dir: settings.default_output_dir } : {}),
      ...(reuseDraft?.params ?? {}),
    }),
    [reuseDraft, settings],
  );

  return (
    <div className="workspace tool-workspace">
      <main className="tool-column">
        <section className="hero">
          <div className="hero-icon">
            <VideoCameraOutlined />
          </div>
          <div>
            <Title level={2}>{tool?.name ?? "视频转图片"}</Title>
            <Paragraph>
              {tool?.description ?? "按固定帧间隔批量提取视频画面，并在后台并行执行多个任务。"}
            </Paragraph>
          </div>
        </section>
        <Card className="form-card" title="任务参数" bordered={false}>
          {tool && settings ? (
            <ToolForm
              key={`${reuseDraft?.key ?? "default"}:${JSON.stringify(settings.video_frames)}`}
              tool={tool}
              initialOverrides={initialValues}
              onCreated={onTaskChanged}
            />
          ) : (
            <Text type="secondary">正在加载工具定义…</Text>
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
        <TaskCenter tasks={activeTasks} onChanged={onTaskChanged} compact />
        {activeTasks.length > 6 ? (
          <Button type="link" icon={<ArrowRightOutlined />} onClick={onOpenActivity} block>
            查看全部活动
          </Button>
        ) : null}
      </aside>
    </div>
  );
}
