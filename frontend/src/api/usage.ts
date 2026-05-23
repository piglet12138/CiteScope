/**
 * LLM 调用成本与用量 API SDK (M-cost)。
 */
import { apiGet } from './client';

export type UsagePeriod = 'day' | 'week' | 'month' | 'all';

export interface UsageTotal {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  usd_cost: number;
  avg_latency_ms: number;
  error_calls: number;
}

export interface UsageByModelRow {
  provider: string;
  model: string;
  calls: number;
  total_tokens: number;
  usd_cost: number;
}

export interface UsageByPurposeRow {
  purpose: string;
  calls: number;
  total_tokens: number;
  usd_cost: number;
}

export interface UsageSummary {
  period: UsagePeriod;
  client_id: number | null;
  total: UsageTotal;
  by_model: UsageByModelRow[];
  by_purpose: UsageByPurposeRow[];
}

export interface UsageCallRow {
  id: number;
  created_at: string | null;
  client_id: number | null;
  purpose: string;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  usd_cost: number;
  latency_ms: number;
  status: string;
  error: string | null;
}

export interface UsageByClientRow {
  client_id: number | null;
  client_name: string;
  plan: string;
  calls: number;
  total_tokens: number;
  usd_cost: number;
}

export function getUsageSummary(params: { period?: UsagePeriod; client_id?: number }) {
  return apiGet<UsageSummary>('/usage/summary', params as Record<string, unknown>);
}

export function getUsageCalls(params: { client_id?: number; limit?: number }) {
  return apiGet<{ items: UsageCallRow[] }>('/usage/calls', params as Record<string, unknown>);
}

export function getUsageByClient(params: { period?: UsagePeriod }) {
  return apiGet<{ period: UsagePeriod; items: UsageByClientRow[] }>(
    '/usage/by-client',
    params as Record<string, unknown>,
  );
}
