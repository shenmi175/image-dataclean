import {
  ClockCircleOutlined,
  HourglassOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Button, Card, Col, Row, Space, Statistic, Typography } from "antd";

import type { Task, ToolMetadata } from "../api/types";
import { TaskCenter } from "../components/TaskCenter";

const { Title, Text } = Typography;

type Props = {
  tasks: Task[];
  tools: ToolMetadata[];
  maxWorkers: number;
  onTaskChanged: (task: Task) => void;
  onRefresh: () => void;
};

export default function ActivityPage({ tasks, tools, maxWorkers, onTaskChanged, onRefresh }: Props) {
  const running = tasks.filter((task) => task.status === "running").length;
  const pending = tasks.filter((task) => task.status === "pending").length;
  const paused = tasks.filter((task) => task.status === "paused").length;

  return (
    <div className="page-container">
      <div className="page-heading">
        <div>
          <Title level={2}>活动中心</Title>
          <Text type="secondary">集中查看排队和执行中的任务，状态将实时更新。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          刷新
        </Button>
      </div>
      <Row gutter={[16, 16]} className="summary-grid">
        <Col xs={12} lg={6}>
          <Card><Statistic title="运行中" value={running} prefix={<PlayCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="等待中" value={pending} prefix={<HourglassOutlined />} /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="已暂停" value={paused} prefix={<PauseCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card>
            <Statistic
              title="并发槽位"
              value={running}
              suffix={`/ ${maxWorkers}`}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>
      <Card
        className="page-card"
        title={<Space><ClockCircleOutlined />活动任务</Space>}
        bordered={false}
      >
        <TaskCenter tasks={tasks} tools={tools} onChanged={onTaskChanged} />
      </Card>
    </div>
  );
}
