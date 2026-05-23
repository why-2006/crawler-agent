import type { ContentChange, TaskCreateInput, TaskDetail, TaskSummary, TrackingStat } from "../types";

const BASE = "/api";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  createTask: (data: TaskCreateInput) =>
    request<{ task_id: string; status: string; created_at: string }>("/tasks", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listTasks: () => request<TaskSummary[]>("/tasks"),

  getTask: (taskId: string) => request<TaskDetail>(`/tasks/${taskId}`),

  deleteTask: (taskId: string) =>
    request<{ task_id: string; status: string }>(`/tasks/${taskId}`, {
      method: "DELETE",
    }),

  updateSchedule: (taskId: string, recurring_interval_minutes: number) =>
    request<{ task_id: string; recurring_interval_minutes: number }>(
      `/tasks/${taskId}/schedule?recurring_interval_minutes=${recurring_interval_minutes}`,
      { method: "PUT" }
    ),

  cancelSchedule: (taskId: string) =>
    request<{ task_id: string; status: string }>(`/tasks/${taskId}/schedule`, {
      method: "DELETE",
    }),

  getChanges: (taskGroupId?: string, url?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (taskGroupId) params.set("task_group_id", taskGroupId);
    if (url) params.set("url", url);
    params.set("limit", String(limit));
    return request<ContentChange[]>(`/tasks/tracking/changes?${params}`);
  },

  getTrackingStats: (taskGroupId?: string) => {
    const params = taskGroupId ? `?task_group_id=${taskGroupId}` : "";
    return request<TrackingStat[]>(`/tasks/tracking/stats${params}`);
  },
};

export function createWsUrl(taskId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/tasks/${taskId}`;
}
