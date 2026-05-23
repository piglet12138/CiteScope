/**
 * Axios 客户端 + 响应包络解构。
 *
 * 所有 API 调用走这里;Phase B Agent 2 在此基础上扩展具体接口。
 */
import axios, { AxiosInstance, AxiosResponse } from 'axios';
import { message } from 'antd';

export interface Envelope<T> {
  code: number;
  message: string;
  data: T;
  trace_id: string;
}

const baseURL = (import.meta.env.VITE_API_BASE_URL as string) || '/api';

export const http: AxiosInstance = axios.create({
  baseURL,
  timeout: 30000,
});

http.interceptors.response.use(
  (response: AxiosResponse<Envelope<unknown>>) => {
    const env = response.data;
    if (env.code !== 0) {
      message.error(env.message || '请求失败');
      return Promise.reject(new Error(env.message));
    }
    return response;
  },
  (error) => {
    message.error(error?.message || '网络错误');
    return Promise.reject(error);
  },
);

export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await http.get<Envelope<T>>(url, { params });
  return res.data.data;
}

export async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const res = await http.post<Envelope<T>>(url, body);
  return res.data.data;
}

export async function apiPut<T>(url: string, body?: unknown): Promise<T> {
  const res = await http.put<Envelope<T>>(url, body);
  return res.data.data;
}

export async function apiDelete<T>(url: string): Promise<T> {
  const res = await http.delete<Envelope<T>>(url);
  return res.data.data;
}
