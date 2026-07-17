import { DeleteOutlined, FileAddOutlined, FolderOpenOutlined, PlusOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Radio,
  Space,
  Switch,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";

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

function FileListField({
  value = [],
  onChange,
  title = "选择文件",
  extensions = [],
}: {
  value?: string[];
  onChange?: (v: string[]) => void;
  title?: string;
  extensions?: string[];
}) {
  const [busy, setBusy] = useState(false);
  const browse = async () => {
    setBusy(true);
    try {
      const result = await api.selectFiles({
        title,
        extensions,
        multiple: true,
      });
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
        placeholder="每行一个文件绝对路径，也可点击右侧选择"
        onChange={(event) =>
          onChange?.(
            event.target.value
              .split("\n")
              .map((item) => item.trim())
              .filter(Boolean),
          )
        }
      />
      <Button icon={<FileAddOutlined />} loading={busy} onClick={browse}>
        选择
      </Button>
    </Space.Compact>
  );
}

function FileField({
  value,
  onChange,
  extensions = [],
  title = "选择文件",
}: {
  value?: string;
  onChange?: (v: string) => void;
  extensions?: string[];
  title?: string;
}) {
  const [busy, setBusy] = useState(false);
  const browse = async () => {
    setBusy(true);
    try {
      const result = await api.selectFiles({ title, extensions, multiple: false });
      if (result.paths[0]) onChange?.(result.paths[0]);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Space.Compact block>
      <Input value={value} onChange={(event) => onChange?.(event.target.value)} />
      <Button icon={<FileAddOutlined />} loading={busy} onClick={browse}>浏览</Button>
    </Space.Compact>
  );
}

function StringListField({ value = [], onChange }: { value?: string[]; onChange?: (v: string[]) => void }) {
  const serialized = value.join("\n");
  const [text, setText] = useState(serialized);
  useEffect(() => setText(serialized), [serialized]);
  return (
    <Input.TextArea
      value={text}
      autoSize={{ minRows: 3, maxRows: 10 }}
      placeholder="每行一项"
      onChange={(event) => {
        setText(event.target.value);
        onChange?.(event.target.value.split("\n").map((item) => item.trim()).filter(Boolean));
      }}
    />
  );
}

function KeyValueField({ value = {}, onChange }: { value?: Record<string, string>; onChange?: (v: Record<string, string>) => void }) {
  const serialized = Object.entries(value).map(([key, target]) => `${key}=${target}`).join("\n");
  const [text, setText] = useState(serialized);
  useEffect(() => setText(serialized), [serialized]);
  return (
    <Input.TextArea
      value={text}
      autoSize={{ minRows: 3, maxRows: 10 }}
      placeholder="每行一项，例如 0=floor 或 carpet=rug"
      onChange={(event) => {
        setText(event.target.value);
        const entries = event.target.value.split("\n").map((line) => line.trim()).filter(Boolean).flatMap((line) => {
          const index = line.indexOf("=");
          return index > 0 ? [[line.slice(0, index).trim(), line.slice(index + 1).trim()] as [string, string]] : [];
        });
        onChange?.(Object.fromEntries(entries));
      }}
    />
  );
}

function resolveSchema(schema: JsonSchemaProperty | undefined, defs: Record<string, JsonSchemaProperty>): JsonSchemaProperty {
  if (!schema) return {};
  if (schema.$ref?.startsWith("#/$defs/")) return defs[schema.$ref.slice("#/$defs/".length)] ?? schema;
  return schema;
}

function ObjectListField({
  value = [],
  onChange,
  itemSchema,
  defs,
  name,
  widgets,
  fileFilters,
  pickerTitles,
}: {
  value?: Record<string, unknown>[];
  onChange?: (v: Record<string, unknown>[]) => void;
  itemSchema?: JsonSchemaProperty;
  defs: Record<string, JsonSchemaProperty>;
  name: string;
  widgets: Record<string, string>;
  fileFilters: Record<string, string[]>;
  pickerTitles: Record<string, string>;
}) {
  const resolved = resolveSchema(itemSchema, defs);
  const properties = resolved.properties ?? {};
  const update = (index: number, field: string, fieldValue: unknown) => {
    const next = value.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: fieldValue } : item);
    onChange?.(next);
  };
  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      {value.map((item, index) => (
        <Card
          key={index}
          size="small"
          title={`数据源 ${index + 1}`}
          extra={<Button danger type="text" icon={<DeleteOutlined />} onClick={() => onChange?.(value.filter((_, i) => i !== index))} />}
          className="source-config-card"
        >
          <div className="source-config-grid">
            {Object.entries(properties).map(([field, rawSchema]) => {
              const schema = resolveSchema(rawSchema, defs);
              const fieldValue = item[field];
              const fieldKey = `${name}[].${field}`;
              const widget = widgets[fieldKey];
              const wide = widget === "directory" || widget === "file" || widget === "key-value";
              return (
                <div key={field} className={wide ? "wide" : ""}>
                  <label>{schema.title ?? field}</label>
                  {widget === "directory" ? (
                    <DirectoryField value={fieldValue as string | undefined} onChange={(next) => update(index, field, next)} />
                  ) : widget === "file" ? (
                    <FileField
                      value={fieldValue as string | undefined}
                      onChange={(next) => update(index, field, next)}
                      extensions={fileFilters[fieldKey]}
                      title={pickerTitles[fieldKey]}
                    />
                  ) : widget === "key-value" || schema.additionalProperties ? (
                    <KeyValueField value={fieldValue as Record<string, string> | undefined} onChange={(next) => update(index, field, next)} />
                  ) : (
                    <Input value={fieldValue as string | undefined} onChange={(event) => update(index, field, event.target.value)} />
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      ))}
      <Button type="dashed" icon={<PlusOutlined />} onClick={() => onChange?.([...value, {}])} block>
        添加数据源
      </Button>
    </Space>
  );
}

function DirectoryField({ value, onChange, title }: { value?: string; onChange?: (v: string) => void; title?: string }) {
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
      <Button icon={<FolderOpenOutlined />} loading={busy} onClick={browse} title={title}>
        浏览
      </Button>
    </Space.Compact>
  );
}

function DirectoryListField({ value = [], onChange }: { value?: string[]; onChange?: (v: string[]) => void }) {
  const [busy, setBusy] = useState(false);
  const browse = async () => {
    setBusy(true);
    try {
      const result = await api.selectDirectory();
      if (result.path) onChange?.(Array.from(new Set([...value, result.path])));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      {value.map((path, index) => (
        <Space.Compact block key={`${path}:${index}`}>
          <Input value={path} onChange={(event) => onChange?.(value.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} />
          <Button danger icon={<DeleteOutlined />} onClick={() => onChange?.(value.filter((_, itemIndex) => itemIndex !== index))} />
        </Space.Compact>
      ))}
      <Button type="dashed" icon={<FolderOpenOutlined />} loading={busy} onClick={browse} block>添加目录</Button>
    </Space>
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
  const values = Form.useWatch([], form) ?? defaults;

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
    const pickerTitle = tool.ui_schema.picker_titles?.[name];
    if (widget === "file-list") return <FileListField title={pickerTitle} extensions={tool.ui_schema.file_filters?.[name]} />;
    if (widget === "directory-list") return <DirectoryListField />;
    if (widget === "directory") return <DirectoryField title={pickerTitle} />;
    if (widget === "file") return <FileField title={pickerTitle} extensions={tool.ui_schema.file_filters?.[name]} />;
    if (widget === "string-list") return <StringListField />;
    if (widget === "object-list") {
      return <ObjectListField
        name={name}
        itemSchema={schema.items}
        defs={tool.params_schema.$defs ?? {}}
        widgets={tool.ui_schema.widgets ?? {}}
        fileFilters={tool.ui_schema.file_filters ?? {}}
        pickerTitles={tool.ui_schema.picker_titles ?? {}}
      />;
    }
    if (schema.enum) {
      const labels = tool.ui_schema.enum_labels?.[name] ?? {};
      return (
        <Radio.Group>
          {schema.enum.map((option) => (
            <Radio.Button key={option} value={option}>
              {labels[option] ?? (option === "letterbox" ? "等比填充" : option === "direct" ? "直接缩放" : option)}
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
        message={tool.ui_schema.notice ?? "每次任务都会创建独立输出目录。"}
      />
      <div className="form-grid">
        {order.map((name) => {
          const schema = properties[name];
          if (!schema) return null;
          const visibility = tool.ui_schema.visible_if?.[name];
          if (visibility && values[visibility.field] !== visibility.equals) return null;
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
              className={
                tool.ui_schema.full_width?.includes(name)
                || ["file-list", "directory-list", "directory", "object-list"].includes(tool.ui_schema.widgets?.[name] ?? "")
                  ? "wide" : ""
              }
            >
              {renderControl(name, schema)}
            </Form.Item>
          );
        })}
      </div>
      <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
        {tool.ui_schema.submit_label ?? `创建${tool.name}任务`}
      </Button>
    </Form>
  );
}
