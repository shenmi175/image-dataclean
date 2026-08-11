import { DeleteOutlined, FileAddOutlined, FolderOpenOutlined, PlusOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Space,
  Switch,
  message,
  notification,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { JsonSchemaProperty, ModelComponent, Task, ToolMetadata } from "../api/types";

const { Link, Paragraph, Text } = Typography;

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
    <Space.Compact block className="path-picker multiline-picker">
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
    <Space.Compact block className="path-picker">
      <Input value={value} onChange={(event) => onChange?.(event.target.value)} />
      <Button icon={<FileAddOutlined />} loading={busy} onClick={browse}>浏览</Button>
    </Space.Compact>
  );
}

function FileOrDirectoryField({
  value,
  onChange,
  extensions = [],
  title = "选择视频文件或目录",
}: {
  value?: string;
  onChange?: (v: string) => void;
  extensions?: string[];
  title?: string;
}) {
  const [busy, setBusy] = useState<"file" | "directory" | null>(null);
  const selectFile = async () => {
    setBusy("file");
    try {
      const result = await api.selectFiles({ title, extensions, multiple: false });
      if (result.paths[0]) onChange?.(result.paths[0]);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const selectDirectory = async () => {
    setBusy("directory");
    try {
      const result = await api.selectDirectory();
      if (result.path) onChange?.(result.path);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <Space.Compact block className="path-picker dual-path-picker">
      <Input
        value={value}
        placeholder="输入路径，或选择单个视频/目录"
        onChange={(event) => onChange?.(event.target.value)}
      />
      <Button icon={<FileAddOutlined />} loading={busy === "file"} onClick={selectFile}>
        选文件
      </Button>
      <Button
        icon={<FolderOpenOutlined />}
        loading={busy === "directory"}
        onClick={selectDirectory}
      >
        选目录
      </Button>
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
    <Space.Compact block className="path-picker">
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
        <Space.Compact block className="path-picker" key={`${path}:${index}`}>
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
  const [licenseComponent, setLicenseComponent] = useState<ModelComponent | null>(null);
  const [licenseChecked, setLicenseChecked] = useState(false);
  const [pendingValues, setPendingValues] = useState<Record<string, unknown> | null>(null);
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

  const createTask = async (values: Record<string, unknown>) => {
    try {
      const task = await api.createTask(tool.id, values);
      notification.success({
        placement: "bottomRight",
        duration: 5,
        message: `${tool.name}任务已创建`,
        description: "可前往活动中心查看进度",
      });
      onCreated(task);
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const submit = async (submittedValues: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      if (tool.id === "dinov3-frame-deduplicator") {
        const componentId = String(submittedValues.embedding_provider ?? "dinov3-cpu");
        const component = (await api.components()).find((item) => item.id === componentId);
        if (!component) throw new Error(`未找到模型组件：${componentId}`);
        if (!component.license_accepted) {
          setPendingValues(submittedValues);
          setLicenseComponent(component);
          setLicenseChecked(false);
          return;
        }
      }
      await createTask(submittedValues);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const acceptLicenseAndCreate = async () => {
    if (!licenseComponent || !pendingValues || !licenseChecked) return;
    setSubmitting(true);
    try {
      await api.acceptComponentLicense(
        licenseComponent.id,
        licenseComponent.license.sha256,
      );
      const valuesToSubmit = pendingValues;
      setLicenseComponent(null);
      setPendingValues(null);
      await createTask(valuesToSubmit);
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
    if (widget === "file-or-directory") {
      return <FileOrDirectoryField
        title={pickerTitle}
        extensions={tool.ui_schema.file_filters?.[name]}
      />;
    }
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
      const options = tool.ui_schema.enum_options?.[name] ?? schema.enum;
      return (
        <Radio.Group>
          {options.map((option) => (
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
      return <InputNumber
        min={schema.minimum}
        max={schema.maximum}
        step={schema.multipleOf ?? (type === "number" ? 0.01 : 1)}
        style={{ width: "100%" }}
      />;
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
          if (tool.ui_schema.widgets?.[name] === "hidden") return null;
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
                || ["file-list", "directory-list", "directory", "file", "file-or-directory", "object-list", "string-list", "key-value"].includes(tool.ui_schema.widgets?.[name] ?? "")
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
      <Modal
        title={`接受 ${licenseComponent?.license.name ?? "模型许可证"}`}
        open={Boolean(licenseComponent)}
        okText="接受并创建任务"
        cancelText="取消"
        okButtonProps={{ disabled: !licenseChecked, loading: submitting }}
        onOk={acceptLicenseAndCreate}
        onCancel={() => {
          setLicenseComponent(null);
          setPendingValues(null);
          setLicenseChecked(false);
        }}
      >
        {licenseComponent ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Paragraph>
              {licenseComponent.name} 将在首次运行时匿名下载。模型权重不属于本项目的
              MIT 授权范围，使用前必须接受独立的 {licenseComponent.license.name}。
            </Paragraph>
            <Text>
              许可证版本：{licenseComponent.license.version} · {" "}
              <Link href={licenseComponent.license.url} target="_blank" rel="noreferrer">
                阅读完整许可证
              </Link>
            </Text>
            <Checkbox
              checked={licenseChecked}
              onChange={(event) => setLicenseChecked(event.target.checked)}
            >
              我已阅读并接受该模型许可证
            </Checkbox>
          </Space>
        ) : null}
      </Modal>
    </Form>
  );
}
