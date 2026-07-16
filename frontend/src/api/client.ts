import type {
  AppSettings,
  HistoryResponse,
  SettingsUpdate,
  Task,
  TaskDetail,
  TaskLog,
  TaskStatus,
  ToolMetadata,
} from "./types";

declare global {
  interface Window {
    pywebview?: {
      api?: {
        select_directory?: () => Promise<string | null>;
        select_files?: () => Promise<string[]>;
      };
    };
  }
}

function readToken(): string | null {
  const match = window.location.hash.match(/(?:^#|&)token=([^&]+)/);
  if (!match) return null;
  const token = decodeURIComponent(match[1]);
  history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  return token;
}

export const sessionToken = readToken();

export type HistoryQuery = {
  statuses?: TaskStatus[];
  toolId?: string;
  query?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  offset?: number;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (sessionToken) headers.set("Authorization", `Bearer ${sessionToken}`);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    throw new Error(detail || `请求失败 (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  tools: () => apiFetch<ToolMetadata[]>("/tools"),
  tasks: () => apiFetch<Task[]>("/tasks?limit=200"),
  activeTasks: (limit = 100) => apiFetch<Task[]>(`/tasks/active?limit=${limit}`),
  history: (filters: HistoryQuery) => {
    const query = new URLSearchParams();
    filters.statuses?.forEach((status) => query.append("status", status));
    if (filters.toolId) query.set("tool_id", filters.toolId);
    if (filters.query) query.set("query", filters.query);
    if (filters.dateFrom) query.set("date_from", filters.dateFrom);
    if (filters.dateTo) query.set("date_to", filters.dateTo);
    query.set("limit", String(filters.limit ?? 20));
    query.set("offset", String(filters.offset ?? 0));
    return apiFetch<HistoryResponse>(`/tasks/history?${query}`);
  },
  task: (taskId: string) => apiFetch<TaskDetail>(`/tasks/${taskId}`),
  createTask: (toolId: string, params: Record<string, unknown>) =>
    apiFetch<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify({ tool_id: toolId, params }),
    }),
  action: (taskId: string, action: "pause" | "resume" | "cancel" | "retry") =>
    apiFetch<Task>(`/tasks/${taskId}/${action}`, { method: "POST" }),
  deleteTask: (taskId: string, deleteOutput = false) =>
    apiFetch<{ deleted: boolean; output_deleted: boolean }>(
      `/tasks/${taskId}?delete_output=${deleteOutput}`,
      { method: "DELETE" },
    ),
  logs: (taskId: string) => apiFetch<TaskLog[]>(`/tasks/${taskId}/logs`),
  settings: () => apiFetch<AppSettings>("/settings"),
  saveSettings: (settings: SettingsUpdate) =>
    apiFetch<AppSettings>("/settings", { method: "PUT", body: JSON.stringify(settings) }),
  resetSettings: () => apiFetch<AppSettings>("/settings/reset", { method: "POST" }),
  selectDirectory: async () => {
    const nativeSelect = window.pywebview?.api?.select_directory;
    if (nativeSelect) return { path: await nativeSelect() };
    return apiFetch<{ path: string | null }>("/dialogs/select-directory", { method: "POST" });
  },
  selectFiles: async () => {
    const nativeSelect = window.pywebview?.api?.select_files;
    if (nativeSelect) return { paths: await nativeSelect() };
    return apiFetch<{ paths: string[] }>("/dialogs/select-files", { method: "POST" });
  },
  openPath: (path: string) =>
    apiFetch<void>("/system/open-path", { method: "POST", body: JSON.stringify({ path }) }),
};

export function connectEvents(
  onEvent: (event: { type: string; task_id: string; task?: Task }) => void,
  onState: (connected: boolean) => void,
): () => void {
  const tokenQuery = sessionToken ? `?token=${encodeURIComponent(sessionToken)}` : "";
  const source = new EventSource(`/api/events/stream${tokenQuery}`);
  source.onopen = () => onState(true);
  source.onmessage = (message) => onEvent(JSON.parse(message.data));
  source.onerror = () => onState(false);
  return () => {
    source.close();
  };
}
