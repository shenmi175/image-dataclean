import { FolderOpenOutlined, VideoCameraAddOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Radio,
  Space,
  Switch,
  message,
} from "antd";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { JsonSchemaProperty, Task, ToolMetadata } from "../api/types";

type Props = {
  tool: ToolMetadata;
  onCreated: (task: Task) => void;
  initialOverrides?: Record<string, unknown>;
};

function schemaType(schema: JsonSchemaProperty): string | undefined {
  if (schema.type) return schema.type;
  return schema.anyOf?.find((option) => option.type !== "null")?.type;
}

function FileListField({ value = [], onChange }: { value?: string[]; onChange?: (v: string[]) => void }) {
  const [busy, setBusy] = useState(false);
  const browse = async () => {
    setBusy(true);
    try {
      const result = await api.selectFiles();
      if (result.paths.length) onChange?.(Array.from(new Set([...value, ...result.paths])));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Space.Compact block>
      <Input.TextArea
        value={value.join("\n")}
        autoSize={{ minRows: 2, maxRows: 5 }}
        placeholder="每行一个视频绝对路径，也可点击右侧选择"
        onChange={(event) =>
          onChange?.(
            event.target.value
              .split("\n")
              .map((item) => item.trim())
              .filter(Boolean),
          )
        }
      />
      <Button icon={<VideoCameraAddOutlined />} loading={busy} onClick={browse}>
        选择
      </Button>
    </Space.Compact>
  );
}

function DirectoryField({ value, onChange }: { value?: string; onChange?: (v: string) => void }) {
  const [busy, setBusy] = useState(false);
  const browse = async () => {
    setBusy(true);
    try {
      const result = await api.selectDirectory();
      if (result.path) onChange?.(result.path);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Space.Compact block>
      <Input value={value} onChange={(event) => onChange?.(event.target.value)} />
      <Button icon={<FolderOpenOutlined />} loading={busy} onClick={browse}>
        浏览
      </Button>
    </Space.Compact>
  );
}

export function ToolForm({ tool, onCreated, initialOverrides = {} }: Props) {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const properties = tool.params_schema.properties;
  const order = tool.ui_schema.order ?? Object.keys(properties);
  const defaults = useMemo(
    () => ({
      ...Object.fromEntries(
        Object.entries(properties)
          .filter(([, property]) => property.default !== undefined)
          .map(([name, property]) => [name, property.default]),
      ),
      ...initialOverrides,
    }),
    [initialOverrides, properties],
  );

  const submit = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      const task = await api.createTask(tool.id, values);
      message.success("任务已创建，将按并发限制自动执行");
      onCreated(task);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const renderControl = (name: string, schema: JsonSchemaProperty) => {
    const widget = tool.ui_schema.widgets?.[name];
    if (widget === "file-list") return <FileListField />;
    if (widget === "directory") return <DirectoryField />;
    if (schema.enum) {
      return (
        <Radio.Group>
          {schema.enum.map((option) => (
            <Radio.Button key={option} value={option}>
              {option === "letterbox" ? "等比填充" : option === "direct" ? "直接缩放" : option}
            </Radio.Button>
          ))}
        </Radio.Group>
      );
    }
    const type = schemaType(schema);
    if (type === "boolean") return <Switch />;
    if (type === "integer" || type === "number") {
      return <InputNumber min={schema.minimum} max={schema.maximum} style={{ width: "100%" }} />;
    }
    return <Input />;
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={defaults}
      onFinish={submit}
      className="tool-form"
    >
      <Alert
        type="info"
        showIcon
        message="文件和目录可同时使用，重复视频会自动去重。每次任务都会创建独立输出目录。"
      />
      <div className="form-grid">
        {order.map((name) => {
          const schema = properties[name];
          if (!schema) return null;
          const rules = [];
          if (tool.params_schema.required?.includes(name)) {
            rules.push({ required: true, message: `请填写${schema.title ?? name}` });
          }
          return (
            <Form.Item
              key={name}
              name={name}
              label={schema.title ?? name}
              rules={rules}
              valuePropName={schemaType(schema) === "boolean" ? "checked" : "value"}
              className={name === "input_files" || name === "input_dir" || name === "output_dir" ? "wide" : ""}
            >
              {renderControl(name, schema)}
            </Form.Item>
          );
        })}
      </div>
      <Form.Item shouldUpdate noStyle>
        {() => (
          <Checkbox className="agreement" defaultChecked disabled>
            输出图片固定为 JPEG（质量 95），取消任务时保留已生成图片
          </Checkbox>
        )}
      </Form.Item>
      <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
        创建视频转图片任务
      </Button>
    </Form>
  );
}
