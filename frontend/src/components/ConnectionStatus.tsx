import {
  CheckCircleFilled,
  CloudSyncOutlined,
  DisconnectOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import { Tag } from "antd";

import type { ConnectionState } from "../api/client";

const status = {
  connecting: { color: "processing", label: "正在连接", icon: <LoadingOutlined spin /> },
  connected: { color: "success", label: "后端已连接", icon: <CheckCircleFilled /> },
  reconnecting: { color: "warning", label: "正在重新连接", icon: <CloudSyncOutlined spin /> },
  offline: { color: "error", label: "后端离线", icon: <DisconnectOutlined /> },
} as const;

export function ConnectionStatus({ state, compact = false }: { state: ConnectionState; compact?: boolean }) {
  const current = status[state];
  return (
    <Tag icon={current.icon} color={current.color}>
      {compact && state === "connected" ? "实时通道已连接" : current.label}
    </Tag>
  );
}
