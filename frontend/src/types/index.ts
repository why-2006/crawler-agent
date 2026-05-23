export type TaskStatus = "queued" | "running" | "completed" | "failed" | "stopped";

export interface TaskSummary {
  task_id: string;
  seed_url: string;
  status: TaskStatus;
  pages_crawled: number;
  pages_discovered: number;
  result_count: number;
  created_at: string;
  recurring_interval_minutes?: number;
  task_group_id?: string | null;
}

export interface ExtractedRecord {
  source_url: string;
  data: Record<string, unknown>;
}

export interface DataInsight {
  insight_type: string;
  chart_type: string;
  title: string;
  data: {
    categories: string[];
    series: { name: string; values: number[] }[];
  };
  description: string;
}

export interface GroupTask {
  task_id: string;
  status: string;
  created_at: string;
  result_count: number;
  changes_detected: number;
}

export interface TaskDetail {
  task_id: string;
  seed_url: string;
  data_description: string;
  max_depth: number;
  max_pages: number;
  use_javascript: boolean;
  status: TaskStatus;
  pages_crawled: number;
  pages_discovered: number;
  result_count: number;
  results: ExtractedRecord[];
  insights: DataInsight[];
  changes_detected: number;
  recurring_interval_minutes: number;
  task_group_id: string | null;
  group_tasks: GroupTask[];
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProgressEvent {
  type: "progress" | "page_crawled" | "data_extracted" | "completed" | "error" | "insights" | "content_changed";
  pages_crawled: number;
  pages_discovered: number;
  url?: string;
  items?: Record<string, unknown>[];
  message?: string;
  insights?: DataInsight[];
  change_summary?: string;
  change_count?: number;
  detected_at?: string;
}

export interface TaskCreateInput {
  seed_url: string;
  data_description: string;
  max_depth: number;
  max_pages: number;
  use_javascript: boolean;
  recurring_interval_minutes: number;
}

export interface ContentChange {
  id: number;
  task_id: string;
  url: string;
  old_content_hash: string | null;
  new_content_hash: string;
  change_summary: string | null;
  detected_at: string;
}

export interface TrackingStat {
  url: string;
  change_count: number;
  last_changed_at: string | null;
  last_seen_at: string;
}
