import {
  AppstoreOutlined,
  ArrowRightOutlined,
  ClearOutlined,
  PictureOutlined,
  SearchOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import { Card, Empty, Input, Tag, Typography } from "antd";
import { useMemo, useState } from "react";

import type { ToolMetadata } from "../api/types";

const { Title, Paragraph, Text } = Typography;

function toolIcon(tool: ToolMetadata) {
  if (tool.id === "dinov3-frame-deduplicator") return <ClearOutlined />;
  if (tool.id === "video-frames") return <VideoCameraOutlined />;
  if (tool.category.includes("图像")) return <PictureOutlined />;
  return <AppstoreOutlined />;
}

export default function ToolCenterPage({
  tools,
  onOpen,
}: {
  tools: ToolMetadata[];
  onOpen: (toolId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const groups = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const filtered = normalized
      ? tools.filter((tool) =>
          [tool.name, tool.description, tool.category, tool.id]
            .join(" ")
            .toLocaleLowerCase()
            .includes(normalized),
        )
      : tools;
    const categories = new Map<string, ToolMetadata[]>();
    for (const tool of filtered) {
      categories.set(tool.category, [...(categories.get(tool.category) ?? []), tool]);
    }
    return Array.from(categories.entries());
  }, [query, tools]);

  return (
    <div className="page-container tool-center-page">
      <div className="tool-center-heading">
        <div>
          <Title level={2}>工具中心</Title>
          <Paragraph>选择一个自动化流程，配置参数后交由后台执行。</Paragraph>
        </div>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          value={query}
          placeholder="搜索名称、描述或类别"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      {groups.length ? groups.map(([category, categoryTools]) => (
        <section className="tool-category" key={category}>
          <div className="tool-category-title">
            <Title level={4}>{category}</Title>
            <Text type="secondary">{categoryTools.length} 个工具</Text>
          </div>
          <div className="tool-card-grid">
            {categoryTools.map((tool) => (
              <Card
                key={tool.id}
                hoverable
                className="tool-card"
                onClick={() => onOpen(tool.id)}
                role="link"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onOpen(tool.id);
                }}
              >
                <div className="tool-card-head">
                  <div className="tool-card-icon">{toolIcon(tool)}</div>
                  <Tag color={tool.status === "available" ? "success" : "default"}>
                    {tool.status === "available" ? "可用" : tool.status}
                  </Tag>
                </div>
                <Title level={4}>{tool.name}</Title>
                <Paragraph ellipsis={{ rows: 2 }}>{tool.description}</Paragraph>
                <Text className="tool-card-link">打开工具 <ArrowRightOutlined /></Text>
              </Card>
            ))}
          </div>
        </section>
      )) : <Empty description="没有匹配的工具" />}
    </div>
  );
}
