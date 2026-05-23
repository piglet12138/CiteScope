/**
 * Settings API SDK.
 *
 * 新版: 完整可写运行时配置 + 旧版只读列表 (兼容)。
 */
import { apiDelete, apiGet, apiPost, apiPut } from './client';

// ============================================================
// 运行时配置中心
// ============================================================

export interface LLMSetting {
  provider: string;
  model: string;
  configured: boolean;
}

export function getLLMSetting() {
  return apiGet<LLMSetting>('/settings/llm');
}

export type FieldType = 'text' | 'password' | 'textarea' | 'boolean' | 'select';

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  category: 'general' | 'llm' | 'monitor';
  platform?: string;
  options?: string[];
  placeholder?: string;
  help?: string;
}

export interface CategoryDef {
  key: string;
  label: string;
}

export interface SettingsSchema {
  fields: FieldDef[];
  categories: CategoryDef[];
}

/** GET /settings/runtime 返回的字段值 — 普通字段 */
export interface RuntimeFieldValue {
  value: unknown;
  from_runtime: boolean;
}

/** GET /settings/runtime 返回的字段值 — 敏感字段 (已掩码) */
export interface RuntimeSecretValue {
  configured: boolean;
  masked: string;
  from_runtime: boolean;
}

export type RuntimeFieldEntry = RuntimeFieldValue | RuntimeSecretValue;

export type RuntimeConfig = Record<string, RuntimeFieldEntry>;

export function isSecretValue(v: RuntimeFieldEntry): v is RuntimeSecretValue {
  return typeof (v as RuntimeSecretValue).configured === 'boolean';
}

export function getSettingsSchema() {
  return apiGet<SettingsSchema>('/settings/schema');
}

export function getRuntimeConfig() {
  return apiGet<RuntimeConfig>('/settings/runtime');
}

export function putRuntimeConfig(updates: Record<string, unknown>) {
  return apiPut<{ updated: string[]; count: number }>('/settings/runtime', { updates });
}

export function deleteRuntimeKey(key: string) {
  return apiDelete<{ deleted: string[] }>(`/settings/runtime/${encodeURIComponent(key)}`);
}

export function cleanCookieRaw(raw: string) {
  return apiPost<{ cookie: string }>('/settings/clean-cookie', { raw });
}

export function cleanTokenRaw(raw: string) {
  return apiPost<{ token: string }>('/settings/clean-token', { raw });
}

export interface TestResult {
  ok: boolean;
  message?: string;
  preview?: string;
  error?: string;
}

export function testLLM() {
  return apiPost<TestResult>('/settings/test/llm');
}

export function testMonitor(platform: string) {
  return apiPost<TestResult>(`/settings/test/monitor/${platform}`);
}
