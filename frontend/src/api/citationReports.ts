/**
 * Citation Source Analysis 报表 API SDK。
 *
 * 对应后端 routers/citation_reports.py:
 *   GET /clients/:id/citation-reports/stats
 *   GET /clients/:id/citation-reports/top-domains
 *   GET /clients/:id/citation-reports/competitor-assets
 */
import { apiGet } from './client';

export interface CitationStats {
  client_id: number;
  total_citations: number;
  by_status: Record<string, number>;
  by_platform: Record<string, number>;
  unique_domains: number;
}

export interface TopDomainItem {
  domain: string;
  appearances: number;
  platforms_count: number;
  supports_brand_count: number;
}

export interface TopDomainsResponse {
  client_id: number;
  period_days: number;
  platforms_filter: string[] | null;
  limit: number;
  items: TopDomainItem[];
}

export interface CompetitorAssetItem {
  domain: string;
  cited_times: number;
  sample_url: string | null;
  sample_title: string | null;
}

export interface CompetitorGroup {
  competitor: string;
  items: CompetitorAssetItem[];
}

export interface CompetitorAssetsResponse {
  client_id: number;
  period_days: number;
  platforms_filter: string[] | null;
  limit: number;
  competitors: string[];
  results: CompetitorGroup[];
}

export function getCitationStats(clientId: number) {
  return apiGet<CitationStats>(`/clients/${clientId}/citation-reports/stats`);
}

export interface TopDomainsParams {
  days?: number;
  limit?: number;
  platforms?: string;
}

export function getTopDomains(clientId: number, params?: TopDomainsParams) {
  return apiGet<TopDomainsResponse>(
    `/clients/${clientId}/citation-reports/top-domains`,
    params as Record<string, unknown> | undefined,
  );
}

export interface CompetitorAssetsParams {
  competitors: string;
  days?: number;
  limit?: number;
  platforms?: string;
}

export function getCompetitorAssets(clientId: number, params: CompetitorAssetsParams) {
  return apiGet<CompetitorAssetsResponse>(
    `/clients/${clientId}/citation-reports/competitor-assets`,
    params as unknown as Record<string, unknown>,
  );
}
