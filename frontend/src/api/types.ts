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
  capabilities: {
    transfer_modes: Array<"copy" | "move">;
  };
  params_schema: {
    properties: Record<string, JsonSchemaProperty>;
    required?: string[];
    $defs?: Record<string, JsonSchemaProperty>;
  };
  ui_schema: {
    order?: string[];
    widgets?: Record<string, string>;
    submit_label?: string;
    notice?: string;
    enum_labels?: Record<string, Record<string, string>>;
    file_filters?: Record<string, string[]>;
    picker_titles?: Record<string, string>;
    full_width?: string[];
    visible_if?: Record<string, { field: string; equals: unknown }>;
  };
};

export type TaskConflict = {
  id: string;
  task_id: string;
  source_path: string;
  target_path: string;
  status: "pending" | "resolved" | "abandoned";
  action: "skip" | "overwrite" | "rename" | null;
  scope: "current" | "remaining" | null;
  created_at: string;
  resolved_at: string | null;
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
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  additionalProperties?: JsonSchemaProperty | boolean;
  $ref?: string;
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
  pending_conflict: TaskConflict | null;
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
