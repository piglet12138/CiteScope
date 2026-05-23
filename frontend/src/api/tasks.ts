/**
 * Task queue API SDK. Contract §2.7.
 */
import { apiGet, apiPost } from './client';
import type { Page, TaskInfo } from './types';

export interface ListTasksParams {
  status?: 'queued' | 'running' | 'success' | 'failed';
  client_id?: number;
  page?: number;
  page_size?: number;
}

export function listTasks(params?: ListTasksParams) {
  return apiGet<Page<TaskInfo>>('/tasks', params as Record<string, unknown> | undefined);
}

export function getTask(id: string) {
  return apiGet<TaskInfo>(`/tasks/${id}`);
}

export function cancelTask(id: string) {
  return apiPost<TaskInfo>(`/tasks/${id}/cancel`);
}
