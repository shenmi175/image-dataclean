import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  FolderOpenOutlined,
  PauseOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Button, Empty, List, Progress, Space, Tag, Tooltip, Typography, message } from "antd";
import { memo, useState } from "react";

import { api } from "../api/client";
import type { Task, TaskStatus } from "../api/types";
import { TaskDetailsDrawer } from "./TaskDetailsDrawer";

const { Text, Paragraph } = Typography;

export const statusLabel: Record<TaskStatus, string> = {
  pending: "等待中",
  running: "运行中",
  paused: "已暂停",
  cancelling: "取消中",
  cancelled: "已取消",
  completed: "已完成",
  failed: "失败",
  interrupted: "已中断",
};

export const statusColor: Record<TaskStatus, string> = {
  pending: "default",
  running: "processing",
  paused: "warning",
  cancelling: "warning",
  cancelled: "default",
  completed: "success",
  failed: "error",
  interrupted: "error",
};

type Props = {
  tasks: Task[];
  onChanged: (task: Task) => void;
  compact?: boolean;
};

type TaskCardProps = {
  task: Task;
  busy: string | null;
  onAction: (task: Task, name: "pause" | "resume" | "cancel" | "retry") => void;
  onDetails: (task: Task) => void;
};

const TaskCard = memo(function TaskCard({ task, busy, onAction, onDetails }: TaskCardProps) {
  const openOutput = async () => {
    try {
      await api.openPath(task.output_path!);
    } catch (error) {
      message.error((error as Error).message);
    }
  };
  return (
    <List.Item className="task-item" onClick={() => onDetails(task)}>
      <div className="task-head">
        <Space size={8}>
          {task.status === "completed" ? (
            <CheckCircleOutlined className="success-icon" />
          ) : task.status === "failed" || task.status === "interrupted" ? (
            <CloseCircleOutlined className="failure-icon" />
          ) : (
            <PlayCircleOutlined className="running-icon" />
          )}
          <Text strong>视频转图片</Text>
        </Space>
        <Tag color={statusColor[task.status]}>{statusLabel[task.status]}</Tag>
      </div>
      <Progress
        percent={task.progress === null ? undefined : Math.round(task.progress)}
        status={task.status === "failed" ? "exception" : task.status === "completed" ? "success" : "active"}
        showInfo={task.progress !== null}
      />
      <Paragraph ellipsis={{ rows: 1 }} type="secondary" className="task-message">
        {task.error_summary || task.message || "等待调度"}
      </Paragraph>
      <div className="task-metrics">
        <Text type="secondary">成功 {task.success_count}</Text>
        <Text type={task.failure_count ? "danger" : "secondary"}>失败 {task.failure_count}</Text>
        {task.speed ? <Text type="secondary">{task.speed.toFixed(1)} 帧/秒</Text> : null}
      </div>
      <Space className="task-actions" onClick={(event) => event.stopPropagation()}>
        {task.status === "running" && (
          <Tooltip title="暂停">
            <Button
              size="small"
              icon={<PauseOutlined />}
              loading={busy === `${task.id}:pause`}
              onClick={() => onAction(task, "pause")}
            />
          </Tooltip>
        )}
        {task.status === "paused" && (
          <Tooltip title="恢复">
            <Button
              size="small"
              icon={<PlayCircleOutlined />}
              loading={busy === `${task.id}:resume`}
              onClick={() => onAction(task, "resume")}
            />
          </Tooltip>
        )}
        {(["pending", "running", "paused", "cancelling"] as TaskStatus[]).includes(task.status) && (
          <Tooltip title="取消">
            <Button
              size="small"
              danger
              icon={<StopOutlined />}
              disabled={task.status === "cancelling"}
              loading={busy === `${task.id}:cancel`}
              onClick={() => onAction(task, "cancel")}
            />
          </Tooltip>
        )}
        {(["completed", "failed", "cancelled", "interrupted"] as TaskStatus[]).includes(task.status) && (
          <Tooltip title="重新执行">
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={busy === `${task.id}:retry`}
              onClick={() => onAction(task, "retry")}
            />
          </Tooltip>
        )}
        {task.output_path && (
          <Tooltip title="打开输出目录">
            <Button size="small" icon={<FolderOpenOutlined />} onClick={openOutput} />
          </Tooltip>
        )}
      </Space>
    </List.Item>
  );
});

export function TaskCenter({ tasks, onChanged, compact = false }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);

  const action = async (task: Task, name: "pause" | "resume" | "cancel" | "retry") => {
    setBusy(`${task.id}:${name}`);
    try {
      const updated = await api.action(task.id, name);
      onChanged(updated);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (!tasks.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务" />;
  }

  return (
    <>
      <List
        dataSource={compact ? tasks.slice(0, 6) : tasks}
        className="task-list"
        renderItem={(task) => (
          <TaskCard
            task={task}
            busy={busy}
            onAction={action}
            onDetails={(selected) => setDetailTaskId(selected.id)}
          />
        )}
      />
      <TaskDetailsDrawer taskId={detailTaskId} onClose={() => setDetailTaskId(null)} />
    </>
  );
}
