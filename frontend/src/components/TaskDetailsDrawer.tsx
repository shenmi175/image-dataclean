import { Alert, Descriptions, Drawer, Empty, Skeleton, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { TaskDetail, TaskLog } from "../api/types";

const { Paragraph, Text } = Typography;

type Props = {
  taskId: string | null;
  onClose: () => void;
};

export function TaskDetailsDrawer({ taskId, onClose }: Props) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([api.task(taskId), api.logs(taskId)])
      .then(([detail, taskLogs]) => {
        if (cancelled) return;
        setTask(detail);
        setLogs(taskLogs);
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  return (
    <Drawer title="任务详情" width={620} open={Boolean(taskId)} onClose={onClose} destroyOnHidden>
      {loading ? <Skeleton active /> : null}
      {error ? <Alert type="error" showIcon message={error} /> : null}
      {!loading && task ? (
        <Space direction="vertical" size={18} style={{ width: "100%" }}>
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="任务 ID" span={2}>
              <Text copyable>{task.id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="状态">{task.status}</Descriptions.Item>
            <Descriptions.Item label="进度">
              {task.progress === null ? "未知" : `${Math.round(task.progress)}%`}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {new Date(task.created_at).toLocaleString()}
            </Descriptions.Item>
            <Descriptions.Item label="完成时间">
              {task.finished_at ? new Date(task.finished_at).toLocaleString() : "—"}
            </Descriptions.Item>
          </Descriptions>
          {task.output_path ? (
            <div>
              <Text strong>输出目录</Text>
              <Paragraph copyable className="detail-path">
                {task.output_path}
              </Paragraph>
            </div>
          ) : null}
          <div>
            <Text strong>任务参数</Text>
            <pre className="params-view">{JSON.stringify(task.params, null, 2)}</pre>
          </div>
          <div>
            <Text strong>失败项</Text>
            {task.failures.length ? (
              <div className="failure-list">
                {task.failures.map((failure) => (
                  <Alert
                    key={failure.id}
                    type="error"
                    showIcon
                    message={failure.item}
                    description={failure.error}
                  />
                ))}
              </div>
            ) : (
              <Tag color="success">无失败项</Tag>
            )}
          </div>
          <div>
            <Text strong>任务日志</Text>
            {logs.length ? (
              <div className="logs">
                {logs.map((log) => (
                  <div className={`log-line log-${log.level ?? "info"}`} key={log.id}>
                    <time>{new Date(log.created_at).toLocaleTimeString()}</time>
                    <span>{log.message}</span>
                  </div>
                ))}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无日志" />
            )}
          </div>
        </Space>
      ) : null}
    </Drawer>
  );
}
