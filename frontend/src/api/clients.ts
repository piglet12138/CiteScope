/**
 * Client (商家) API SDK.
 * Aligned with docs/api-contract.md §2.2
 */
import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Client, Page } from './types';

export type ClientCreateBody = Omit<Client, 'id' | 'created_at' | 'updated_at'> & {
  /** 创建时是否调 LLM 自动扩展 business_info.keywords (别名/子品牌/英文名). 默认 true */
  auto_expand_keywords?: boolean;
};
export type ClientUpdateBody = Partial<Omit<Client, 'id' | 'created_at' | 'updated_at'>> & {
  /** 更新时是否触发 LLM 再扩展关键词. 默认 false, 避免误把用户删掉的词加回来 */
  auto_expand_keywords?: boolean;
};

export interface ListClientsParams {
  page?: number;
  page_size?: number;
  status?: 'active' | 'paused' | 'archived';
}

export function listClients(params?: ListClientsParams) {
  return apiGet<Page<Client>>('/clients', params as Record<string, unknown> | undefined);
}

export function getClient(id: number) {
  return apiGet<Client>(`/clients/${id}`);
}

export function createClient(body: ClientCreateBody) {
  return apiPost<Client>('/clients', body);
}

export function updateClient(id: number, body: ClientUpdateBody) {
  return apiPut<Client>(`/clients/${id}`, body);
}

export function deleteClient(id: number) {
  return apiDelete<{ deleted: boolean }>(`/clients/${id}`);
}

/** 调 LLM 重跑一次品牌识别关键词 (覆盖当前 business_info.keywords) */
export function regenerateClientKeywords(id: number) {
  return apiPost<Client>(`/clients/${id}/regenerate-keywords`, {});
}
