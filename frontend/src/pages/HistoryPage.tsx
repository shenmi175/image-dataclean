import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  MoreOutlined,
  ReloadOutlined,
  SettingOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Dropdown,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { TableProps } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { HistoryResponse, Task, TaskStatus } from "../api/types";
import { statusColor, statusLabel } from "../components/TaskCenter";
import { TaskDetailsDrawer } from "../components/TaskDetailsDrawer";

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const emptyHistory: HistoryResponse = {
  items: [],
  total: 0,
  counts: { completed: 0, failed: 0, cancelled: 0, interrupted: 0 },
};

type Props = {
  revision: number;
  onReuse: (task: Task) => void;
  onTaskCreated: (task: Task) => void;
};

export default function HistoryPage({ revision, onReuse, onTaskCreated }: Props) {
  const [data, setData] = useState<HistoryResponse>(emptyHistory);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [statuses, setStatuses] = useState<TaskStatus[]>([]);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(
        await api.history({
          statuses,
          query,
          dateFrom: dateRange?.[0] ? new Date(`${dateRange[0]}T00:00:00`).toISOString() : undefined,
          dateTo: dateRange?.[1] ? new Date(`${dateRange[1]}T23:59:59.999`).toISOString() : undefined,
          limit: 20,
          offset: (page - 1) * 20,
        }),
      );
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [dateRange, page, query, statuses]);

  useEffect(() => {
    load();
  }, [load, revision]);

  const retry = async (task: Task) => {
    try {
      const created = await api.action(task.id, "retry");
      onTaskCreated(created);
      message.success("已创建重试任务");
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const openOutput = async (task: Task) => {
    try {
      await api.openPath(task.output_path!);
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const confirmDelete = (task: Task, deleteOutput: boolean) => {
    Modal.confirm({
      title: deleteOutput ? "删除记录并清理输出文件？" : "删除这条执行记录？",
      icon: <ExclamationCircleOutlined />,
      content: deleteOutput
        ? "该操作会永久删除本任务生成的输出目录，无法撤销。"
        : "仅删除历史记录、日志和失败明细，输出文件保持不变。",
      okText: deleteOutput ? "永久删除" : "删除记录",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteTask(task.id, deleteOutput);
          message.success(deleteOutput ? "记录和输出已删除" : "记录已删除，输出文件已保留");
          await load();
        } catch (error) {
          message.error((error as Error).message);
          throw error;
        }
      },
    });
  };

  const columns: TableProps<Task>["columns"] = [
    {
      title: "任务",
      key: "task",
      render: (_, task) => (
        <div>
          <Text strong>视频转图片</Text>
          <Text type="secondary" className="table-subline">{task.id.slice(0, 12)}</Text>
        </div>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: TaskStatus) => <Tag color={statusColor[status]}>{statusLabel[status]}</Tag>,
    },
    {
      title: "结果",
      key: "result",
      render: (_, task) => (
        <Space size={12}>
          <Text type="success">成功 {task.success_count}</Text>
          <Text type={task.failure_count ? "danger" : "secondary"}>失败 {task.failure_count}</Text>
        </Space>
      ),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 170,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: "输出目录",
      dataIndex: "output_path",
      ellipsis: true,
      render: (value: string | null) => value || "—",
    },
    {
      title: "操作",
      key: "actions",
      width: 235,
      render: (_, task) => (
        <Space size={4}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => setDetailTaskId(task.id)}>
            详情
          </Button>
          <Button size="small" icon={<SettingOutlined />} onClick={() => onReuse(task)}>
            使用参数
          </Button>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => retry(task)} />
          {task.output_path ? (
            <Button size="small" icon={<FolderOpenOutlined />} onClick={() => openOutput(task)} />
          ) : null}
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                { key: "record", label: "删除记录", icon: <DeleteOutlined />, danger: true },
                ...(task.output_path
                  ? [{ key: "all", label: "删除记录和输出", icon: <StopOutlined />, danger: true }]
                  : []),
              ],
              onClick: ({ key }) => confirmDelete(task, key === "all"),
            }}
          >
            <Button size="small" icon={<MoreOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-container history-page">
      <div className="page-heading">
        <div>
          <Title level={2}>执行历史</Title>
          <Text type="secondary">查询已结束任务，查看结果、复用参数或清理记录。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </div>
      <Row gutter={[16, 16]} className="summary-grid">
        <Col xs={12} lg={6}><Card><Statistic title="已完成" value={data.counts.completed} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="失败" value={data.counts.failed} prefix={<ExclamationCircleOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="已取消" value={data.counts.cancelled} prefix={<StopOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="已中断" value={data.counts.interrupted} prefix={<ClockCircleOutlined />} /></Card></Col>
      </Row>
      <Card className="page-card" bordered={false}>
        <div className="history-filters">
          <Select
            mode="multiple"
            allowClear
            placeholder="全部状态"
            value={statuses}
            onChange={(value) => { setStatuses(value); setPage(1); }}
            options={(["completed", "failed", "cancelled", "interrupted"] as TaskStatus[]).map((status) => ({
              value: status,
              label: statusLabel[status],
            }))}
          />
          <RangePicker
            onChange={(_, values) => {
              setDateRange(values[0] && values[1] ? [values[0], values[1]] : null);
              setPage(1);
            }}
          />
          <Input.Search
            allowClear
            value={queryInput}
            placeholder="搜索任务 ID、路径或消息"
            onChange={(event) => setQueryInput(event.target.value)}
            onSearch={(value) => { setQuery(value.trim()); setPage(1); }}
          />
        </div>
        <Table<Task>
          rowKey="id"
          columns={columns}
          dataSource={data.items}
          loading={loading}
          scroll={{ x: 1080 }}
          pagination={{
            current: page,
            pageSize: 20,
            total: data.total,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 条`,
            onChange: setPage,
          }}
        />
      </Card>
      <TaskDetailsDrawer taskId={detailTaskId} onClose={() => setDetailTaskId(null)} />
    </div>
  );
}
