/**
 * 与 backend Pydantic schema 对齐的 TypeScript 类型。
 *
 * 重构后只保留 GEO 效果监测实验平台所需的模型。
 */

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Client {
  id: number;
  name: string;
  industry: string;
  region: string;
  business_info: BusinessInfo;
  plan: 'basic' | 'pro' | 'enterprise';
  status: 'active' | 'paused' | 'archived';
  created_at: string;
  updated_at: string;
}

export interface BusinessInfo {
  description: string;
  address?: string;
  phone?: string;
  website?: string;
  services?: string[];
  competitors?: string[];
  keywords?: string[];
}

export type QuestionCategory = 'recommend' | 'compare' | 'price' | 'review' | 'other';

export interface Question {
  id: number;
  client_id: number;
  text: string;
  category: QuestionCategory;
  priority: number;
  is_active: boolean;
  language?: string;
  created_at: string;
}

export type MonitorPlatform =
  | 'perplexity'
  | 'chatgpt'
  | 'google_ai'
  | 'doubao'
  | 'deepseek'
  | 'kimi';

/** AI 回答中引用的搜索来源, cite_index 与 raw_answer 中的 [citation:N] 对齐 */
export interface SearchResultItem {
  cite_index: number | null;
  title: string;
  url: string;
  snippet: string;
  published_at: number | null;
  site_icon: string | null;
}

export interface MonitorResult {
  id: number;
  client_id: number;
  question_id: number;
  run_id: number | null;
  platform: MonitorPlatform;
  is_mentioned: boolean;
  position: number | null;
  has_link: boolean;
  sentiment: 'positive' | 'neutral' | 'negative' | null;
  raw_answer: string | null;
  search_results: SearchResultItem[] | null;
  screenshot_path: string | null;
  checked_at: string;
}

export interface Metrics {
  client_id: number;
  period: 'today' | 'week' | 'month';
  mention_rate: number;
  first_mention_rate: number;
  link_citation_rate: number;
  sentiment_accuracy: number;
  trend: { date: string; mention_rate: number }[];
  by_platform: { platform: string; mention_rate: number; sample_size: number }[];
}

export interface Report {
  id: number;
  client_id: number;
  period_start: string;
  period_end: string;
  summary: string;
  metrics_snapshot: Metrics;
  created_at: string;
}

export type RunStatus = 'running' | 'completed' | 'completed_with_errors' | 'failed';

export interface MonitorRun {
  id: number;
  client_id: number;
  name: string;
  note: string | null;
  platforms: string[];
  question_count: number;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  mention_rate: number;
  sample_size: number;
}

export interface RunPlatformCell {
  platform: string;
  mention_rate: number;
  first_mention_rate: number;
  link_citation_rate: number;
  sample_size: number;
}

export interface RunCompareEntry {
  run_id: number;
  run_name: string;
  created_at: string;
  overall: RunPlatformCell;
  by_platform: RunPlatformCell[];
}

export interface RunCompareOut {
  runs: RunCompareEntry[];
  platforms: string[];
}

export type TaskType = 'monitor' | 'report';

export interface TaskInfo {
  task_id: string;
  type: TaskType;
  status: 'queued' | 'running' | 'success' | 'failed';
  progress: number;
  result: Record<string, unknown> | null;
  error: string | null;
  client_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface TaskRef {
  task_id: string;
  status: string;
  extra?: Record<string, unknown>;
}
