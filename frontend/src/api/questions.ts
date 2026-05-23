/**
 * Question API SDK。重构后:手工录入 + CSV 导入,无 AI 生成。
 */
import { apiGet, apiPost, apiPut, apiDelete, http } from './client';
import type { Envelope } from './client';
import type { Page, Question, QuestionCategory } from './types';

export interface ListQuestionsParams {
  page?: number;
  page_size?: number;
  category?: QuestionCategory;
}

export function listQuestions(clientId: number, params?: ListQuestionsParams) {
  return apiGet<Page<Question>>(
    `/clients/${clientId}/questions`,
    params as Record<string, unknown> | undefined,
  );
}

export interface QuestionDraft {
  text: string;
  category?: QuestionCategory;
  priority?: number;
  language?: string;
}

export interface BulkCreateResult {
  created: number;
  skipped: number;
}

export function bulkCreateQuestions(clientId: number, items: QuestionDraft[]) {
  return apiPost<BulkCreateResult>(`/clients/${clientId}/questions`, { items });
}

export interface CSVImportResult {
  created: number;
  skipped: number;
  errors: string[];
}

export async function importQuestionsCSV(
  clientId: number,
  file: File,
): Promise<CSVImportResult> {
  const form = new FormData();
  form.append('file', file);
  const resp = await http.post<Envelope<CSVImportResult>>(
    `/clients/${clientId}/questions/import-csv`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return resp.data.data;
}

export function updateQuestion(id: number, body: Partial<Question>) {
  return apiPut<Question>(`/questions/${id}`, body);
}

export function deleteQuestion(id: number) {
  return apiDelete<{ deleted: boolean }>(`/questions/${id}`);
}
