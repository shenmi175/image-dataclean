import { FolderOpenOutlined, ReloadOutlined, SaveOutlined, SettingOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Skeleton,
  Space,
  Switch,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { AppSettings, SettingsUpdate } from "../api/types";

const { Title, Text } = Typography;

type Props = {
  settings: AppSettings | null;
  onChanged: (settings: AppSettings) => void;
};

export default function SettingsPage({ settings, onChanged }: Props) {
  const [form] = Form.useForm<SettingsUpdate>();
  const [saving, setSaving] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const resize = Form.useWatch(["video_frames", "resize"], form);
  const maxWorkers = Form.useWatch("max_workers", form) ?? settings?.max_workers ?? 1;

  useEffect(() => {
    if (settings) {
      form.setFieldsValue({
        max_workers: settings.max_workers,
        parallel_workers: settings.parallel_workers,
        default_output_dir: settings.default_output_dir,
        video_frames: settings.video_frames,
      });
    }
  }, [form, settings]);

  const browse = async () => {
    setBrowsing(true);
    try {
      const result = await api.selectDirectory();
      if (result.path) form.setFieldValue("default_output_dir", result.path);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBrowsing(false);
    }
  };

  const save = async (values: SettingsUpdate) => {
    setSaving(true);
    try {
      const updated = await api.saveSettings({
        ...values,
        default_output_dir: values.default_output_dir?.trim() || null,
      });
      onChanged(updated);
      message.success("设置已保存，将应用于新启动的任务");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    Modal.confirm({
      title: "恢复系统默认设置？",
      content: "任务并发、单任务并行、默认输出目录和视频参数将被重置。",
      okText: "恢复默认",
      cancelText: "取消",
      onOk: async () => {
        const updated = await api.resetSettings();
        onChanged(updated);
        form.setFieldsValue(updated);
        message.success("已恢复系统默认设置");
      },
    });
  };

  if (!settings) {
    return <div className="page-container"><Skeleton active /></div>;
  }

  return (
    <div className="page-container settings-page">
      <div className="page-heading">
        <div>
          <Title level={2}>设置</Title>
          <Text type="secondary">调整任务并发、默认目录和视频转图片参数。</Text>
        </div>
      </div>
      <Form form={form} layout="vertical" onFinish={save} requiredMark={false}>
        <Card className="page-card settings-card" title={<Space><SettingOutlined />运行与存储</Space>} bordered={false}>
          <Form.Item
            name="max_workers"
            label="最大并发任务数"
            extra={`系统建议 ${settings.recommended_workers}；降低并发不会中断正在运行的任务。`}
            rules={[{ required: true, message: "请填写并发任务数" }]}
          >
            <InputNumber min={1} max={32} precision={0} style={{ width: 220 }} />
          </Form.Item>
          <Form.Item
            name="parallel_workers"
            label="单任务并行线程数"
            extra={
              `0 表示自动平衡；当前 ${settings.cpu_count} 个可用 CPU，` +
              `按 ${maxWorkers} 个并发任务建议每任务 ${Math.max(1, Math.floor(settings.cpu_count / maxWorkers))} 个线程。`
            }
            rules={[{ required: true, message: "请填写单任务并行数" }]}
          >
            <InputNumber min={0} max={32} precision={0} style={{ width: 220 }} />
          </Form.Item>
          <Form.Item name="default_output_dir" label="默认输出目录" extra="留空时，新任务仍需要手动选择输出目录。">
            <Space.Compact block>
              <Input allowClear placeholder="尚未设置" />
              <Button icon={<FolderOpenOutlined />} loading={browsing} onClick={browse}>浏览</Button>
            </Space.Compact>
          </Form.Item>
        </Card>

        <Card className="page-card settings-card" title="视频转图片默认参数" bordered={false}>
          <Alert
            type="info"
            showIcon
            message="这些值会自动填入新任务表单，使用历史参数时以历史参数为准。"
          />
          <div className="settings-grid">
            <Form.Item name={["video_frames", "recursive"]} label="递归扫描子目录" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item
              name={["video_frames", "frame_interval"]}
              label="抽帧间隔"
              rules={[{ required: true, message: "请填写抽帧间隔" }]}
            >
              <InputNumber min={1} max={1_000_000} precision={0} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name={["video_frames", "resize"]} label="调整图片尺寸" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name={["video_frames", "resize_mode"]} label="缩放方式">
              <Radio.Group disabled={!resize}>
                <Radio.Button value="letterbox">等比填充</Radio.Button>
                <Radio.Button value="direct">直接缩放</Radio.Button>
              </Radio.Group>
            </Form.Item>
            <Form.Item name={["video_frames", "width"]} label="宽度">
              <InputNumber min={1} max={32768} disabled={!resize} precision={0} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name={["video_frames", "height"]} label="高度">
              <InputNumber min={1} max={32768} disabled={!resize} precision={0} style={{ width: "100%" }} />
            </Form.Item>
          </div>
        </Card>
        <Card className="settings-actions" bordered={false}>
          <Space>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>保存设置</Button>
            <Button icon={<ReloadOutlined />} onClick={reset}>恢复默认</Button>
          </Space>
        </Card>
      </Form>
    </div>
  );
}
