import { AppstoreOutlined, ArrowLeftOutlined, ClearOutlined, PictureOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Button, Card, Result, Spin, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { AppSettings, Task, ToolMetadata } from "../api/types";
import { ToolForm } from "../components/ToolForm";

const { Title, Paragraph, Text } = Typography;

type Props = {
  tool?: ToolMetadata;
  settings: AppSettings | null;
  reuseTaskId: string | null;
  loadingTools: boolean;
  onTaskChanged: (task: Task) => void;
  onBack: () => void;
};

function normalizeReuseParams(
  toolId: string,
  params: Record<string, unknown>,
): { params: Record<string, unknown>; warning?: string } {
  if (toolId !== "video-frames") return { params };

  const normalized = { ...params };
  const inputPath = typeof normalized.input_path === "string" && normalized.input_path
    ? normalized.input_path
    : null;
  const inputDir = typeof normalized.input_dir === "string" && normalized.input_dir
    ? normalized.input_dir
    : null;
  const inputFiles = Array.isArray(normalized.input_files)
    ? normalized.input_files.filter((item): item is string => typeof item === "string" && Boolean(item))
    : [];

  delete normalized.input_files;
  delete normalized.input_dir;
  if (inputPath) {
    normalized.input_path = inputPath;
    return { params: normalized };
  }

  delete normalized.input_path;
  const oldSources = [...(inputDir ? [inputDir] : []), ...inputFiles];
  if (oldSources.length === 1) {
    normalized.input_path = oldSources[0];
    return { params: normalized };
  }
  if (oldSources.length > 1) {
    return {
      params: normalized,
      warning: inputFiles.length > 1 && !inputDir
        ? "旧任务包含多个离散视频，请重新选择单个视频或包含这些视频的目录。"
        : "旧任务包含多个输入来源，请重新选择单个视频或一个视频目录。",
    };
  }
  return { params: normalized };
}

export default function ToolPage({
  tool,
  settings,
  reuseTaskId,
  loadingTools,
  onTaskChanged,
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
        const reuse = normalizeReuseParams(tool.id, task.params);
        setReuseParams(reuse.params);
        if (reuse.warning) message.warning(reuse.warning);
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
      ...(tool?.capabilities.supports_parallel && settings
        ? { parallel_workers: settings.parallel_workers }
        : {}),
      ...(settings?.default_output_dir ? { output_dir: settings.default_output_dir } : {}),
      ...(reuseParams ?? {}),
    }),
    [reuseParams, settings, tool?.id],
  );
  const heroIcon =
    tool?.id === "dinov3-frame-deduplicator" ? <ClearOutlined />
      : tool?.id === "video-frames" ? <VideoCameraOutlined />
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
    </div>
  );
}
