export type TaskStatus =
  | "pending"
  | "running"
  | "paused"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed"
  | "interrupted";

export type ToolMetadata = {
  id: string;
  name: string;
  category: string;
  version: string;
  description: string;
  status: string;
  supports_pause: boolean;
  supports_resume_after_restart: boolean;
  params_schema: {
    properties: Record<string, JsonSchemaProperty>;
    required?: string[];
  };
  ui_schema: {
    order?: string[];
    widgets?: Record<string, string>;
  };
};

export type JsonSchemaProperty = {
  title?: string;
  type?: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  enum?: string[];
  anyOf?: JsonSchemaProperty[];
  items?: JsonSchemaProperty;
};

export type Task = {
  id: string;
  tool_id: string;
  tool_version: string;
  status: TaskStatus;
  params: Record<string, unknown>;
  current: number;
  total: number | null;
  progress: number | null;
  message: string;
  speed: number | null;
  success_count: number;
  failure_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  output_path: string | null;
  source_task_id: string | null;
  error_summary: string | null;
  revision: number;
};

export type TaskLog = {
  id: number;
  event_type: string;
  level: string | null;
  message: string;
  created_at: string;
};

export type TaskFailure = {
  id: number;
  item: string;
  error: string;
  created_at: string;
};

export type TaskDetail = Task & {
  failures: TaskFailure[];
};

export type HistoryCounts = Record<"completed" | "failed" | "cancelled" | "interrupted", number>;

export type HistoryResponse = {
  items: Task[];
  total: number;
  counts: HistoryCounts;
};

export type VideoFramesDefaults = {
  recursive: boolean;
  frame_interval: number;
  resize: boolean;
  width: number;
  height: number;
  resize_mode: "letterbox" | "direct";
};

export type AppSettings = {
  max_workers: number;
  default_max_workers: number;
  recommended_workers: number;
  default_output_dir: string | null;
  video_frames: VideoFramesDefaults;
};

export type SettingsUpdate = Pick<
  AppSettings,
  "max_workers" | "default_output_dir" | "video_frames"
>;
