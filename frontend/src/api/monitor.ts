/**
 * Monitor (监测 / 实验 Run / 报告) API SDK.
 */
import { apiGet, apiPost } from './client';
import type {
  Metrics,
  MonitorPlatform,
  MonitorResult,
  MonitorRun,
  Page,
  Report,
  RunCompareOut,
  TaskRef,
} from './types';

export function triggerMonitor(
  clientId: number,
  body?: {
    question_ids?: number[];
    platforms?: MonitorPlatform[];
    max_questions?: number;
    extra_question_texts?: string[];
  },
) {
  return apiPost<TaskRef & { run_id?: number }>(`/clients/${clientId}/monitor`, body ?? {});
}

export function getMetrics(clientId: number, period: 'today' | 'week' | 'month' = 'week') {
  return apiGet<Metrics>(`/clients/${clientId}/metrics`, { period });
}

export interface ListMonitorResultsParams {
  question_id?: number;
  platform?: MonitorPlatform;
  page?: number;
  page_size?: number;
}

export function listMonitorResults(clientId: number, params?: ListMonitorResultsParams) {
  return apiGet<Page<MonitorResult>>(
    `/clients/${clientId}/monitor-results`,
    params as Record<string, unknown> | undefined,
  );
}

export function listReports(clientId: number, params?: { page?: number; page_size?: number }) {
  return apiGet<Page<Report>>(
    `/clients/${clientId}/reports`,
    params as Record<string, unknown> | undefined,
  );
}

export function createReport(
  clientId: number,
  body: { period_start: string; period_end: string },
) {
  return apiPost<Report>(`/clients/${clientId}/reports`, body);
}

export function getReport(id: number) {
  return apiGet<Report>(`/reports/${id}`);
}

// ---------- 对比实验 (Run) ----------
export interface RunCreateBody {
  name: string;
  note?: string;
  question_ids?: number[];
  extra_question_texts?: string[];
  platforms?: MonitorPlatform[];
  max_questions?: number;
}

export function createMonitorRun(clientId: number, body: RunCreateBody) {
  return apiPost<TaskRef & { run_id: number }>(`/clients/${clientId}/runs`, body);
}

export function listMonitorRuns(
  clientId: number,
  params?: { page?: number; page_size?: number },
) {
  return apiGet<Page<MonitorRun>>(
    `/clients/${clientId}/runs`,
    params as Record<string, unknown> | undefined,
  );
}

export function getMonitorRun(runId: number) {
  return apiGet<MonitorRun>(`/runs/${runId}`);
}

export function compareMonitorRuns(runIds: number[]) {
  return apiGet<RunCompareOut>(`/runs/compare`, { ids: runIds.join(',') });
}
