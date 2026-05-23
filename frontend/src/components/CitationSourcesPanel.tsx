/**
 * Citation Sources 报表面板。
 *
 * 三块:
 *  1. 顶部统计条:总 citation 数 / unique domain 数 / by_status / by_platform
 *  2. Top-domains 表:品类引用域名 Top N (可调时间窗 / 平台)
 *  3. 竞品 GEO 资产清单:输入竞品名 → 看 AI 提及该竞品时引用了哪些域名
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { ReloadOutlined, BarChartOutlined, BookOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import {
  getCitationStats,
  getCompetitorAssets,
  getTopDomains,
} from '../api/citationReports';
import type {
  CitationStats,
  CompetitorGroup,
  TopDomainItem,
} from '../api/citationReports';

const PLATFORM_OPTIONS: { value: string; label: string }[] = [
  { value: 'perplexity', label: 'Perplexity' },
  { value: 'chatgpt', label: 'ChatGPT' },
  { value: 'google_ai', label: 'Google AI' },
  { value: 'doubao', label: '豆包' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'kimi', label: 'Kimi' },
];

const DAYS_OPTIONS = [
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
  { value: 90, label: '近 90 天' },
  { value: 365, label: '近 1 年' },
];

export default function CitationSourcesPanel({ clientId }: { clientId: number }) {
  const [stats, setStats] = useState<CitationStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // Filter state — 共用于 top-domains & competitor-assets
  const [days, setDays] = useState<number>(30);
  const [limit, setLimit] = useState<number>(20);
  const [platforms, setPlatforms] = useState<string[]>([]);

  // Top-domains
  const [topDomains, setTopDomains] = useState<TopDomainItem[]>([]);
  const [topLoading, setTopLoading] = useState(false);

  // Competitor assets
  const [competitorsInput, setCompetitorsInput] = useState<string>('');
  const [competitorResults, setCompetitorResults] = useState<CompetitorGroup[]>([]);
  const [competitorLoading, setCompetitorLoading] = useState(false);

  const fetchStats = async () => {
    setStatsLoading(true);
    try {
      const s = await getCitationStats(clientId);
      setStats(s);
    } finally {
      setStatsLoading(false);
    }
  };

  const fetchTopDomains = async () => {
    setTopLoading(true);
    try {
      const r = await getTopDomains(clientId, {
        days,
        limit,
        platforms: platforms.length > 0 ? platforms.join(',') : undefined,
      });
      setTopDomains(r.items ?? []);
    } finally {
      setTopLoading(false);
    }
  };

  const fetchCompetitors = async () => {
    const competitors = competitorsInput.trim();
    if (!competitors) {
      message.warning('先填一个或多个竞品名,逗号分隔');
      return;
    }
    setCompetitorLoading(true);
    try {
      const r = await getCompetitorAssets(clientId, {
        competitors,
        days,
        limit,
        platforms: platforms.length > 0 ? platforms.join(',') : undefined,
      });
      setCompetitorResults(r.results ?? []);
    } finally {
      setCompetitorLoading(false);
    }
  };

  useEffect(() => {
    if (!Number.isFinite(clientId)) return;
    fetchStats();
    fetchTopDomains();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  const topDomainsColumns = useMemo(
    () => [
      {
        title: '#',
        width: 50,
        render: (_: unknown, __: TopDomainItem, idx: number) => idx + 1,
      },
      {
        title: '域名',
        dataIndex: 'domain',
        render: (d: string) => (
          <a href={`https://${d}`} target="_blank" rel="noreferrer">
            {d}
          </a>
        ),
      },
      {
        title: '被引次数',
        dataIndex: 'appearances',
        sorter: (a: TopDomainItem, b: TopDomainItem) => a.appearances - b.appearances,
        defaultSortOrder: 'descend' as const,
        width: 110,
      },
      {
        title: '跨平台',
        dataIndex: 'platforms_count',
        width: 90,
        render: (n: number) => <Tag color={n >= 2 ? 'green' : 'default'}>{n}</Tag>,
      },
      {
        title: '支撑品牌提及',
        dataIndex: 'supports_brand_count',
        width: 130,
        render: (n: number) =>
          n > 0 ? <Tag color="blue">{n}</Tag> : <Typography.Text type="secondary">—</Typography.Text>,
      },
    ],
    [],
  );

  const competitorAssetColumns = [
    {
      title: '域名',
      dataIndex: 'domain',
      render: (d: string) => (
        <a href={`https://${d}`} target="_blank" rel="noreferrer">
          {d}
        </a>
      ),
    },
    {
      title: '被引次数',
      dataIndex: 'cited_times',
      width: 100,
      sorter: (a: { cited_times: number }, b: { cited_times: number }) =>
        a.cited_times - b.cited_times,
      defaultSortOrder: 'descend' as const,
    },
    {
      title: '样本 URL',
      dataIndex: 'sample_url',
      ellipsis: true,
      render: (u: string | null) =>
        u ? (
          <a href={u} target="_blank" rel="noreferrer">
            {u}
          </a>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* ---------- 1. 顶部统计条 ---------- */}
      <Card
        size="small"
        title={
          <Space>
            <BarChartOutlined />
            <span>引用规模概览</span>
          </Space>
        }
        extra={
          <Space>
            <Link to="/guides/citation-sources" target="_blank">
              <Button size="small" icon={<BookOutlined />}>
                使用手册
              </Button>
            </Link>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => {
                fetchStats();
                fetchTopDomains();
              }}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <Spin spinning={statsLoading}>
          <Row gutter={16}>
            <Col span={4}>
              <Statistic title="总 citation 数" value={stats?.total_citations ?? 0} />
            </Col>
            <Col span={4}>
              <Statistic title="独立域名" value={stats?.unique_domains ?? 0} />
            </Col>
            <Col span={4}>
              <Statistic
                title="已解析 (ok)"
                value={stats?.by_status?.ok ?? 0}
                valueStyle={{ color: '#52c41a' }}
              />
            </Col>
            <Col span={4}>
              <Statistic
                title="待解析 (pending)"
                value={stats?.by_status?.pending ?? 0}
                valueStyle={{ color: '#faad14' }}
              />
            </Col>
            <Col span={4}>
              <Statistic
                title="跳过 (skipped)"
                value={stats?.by_status?.skipped ?? 0}
                valueStyle={{ color: '#999' }}
              />
            </Col>
            <Col span={4}>
              <Statistic
                title="失败 (failed)"
                value={stats?.by_status?.failed ?? 0}
                valueStyle={{ color: '#ff4d4f' }}
              />
            </Col>
          </Row>
          {stats?.by_platform && (
            <div style={{ marginTop: 12 }}>
              <Typography.Text type="secondary" style={{ marginRight: 8 }}>
                平台分布:
              </Typography.Text>
              {Object.entries(stats.by_platform).map(([p, n]) => (
                <Tag key={p}>
                  {p} · {n}
                </Tag>
              ))}
            </div>
          )}
        </Spin>
      </Card>

      {/* ---------- 共用筛选条 ---------- */}
      <Card size="small">
        <Space wrap>
          <span>时间窗:</span>
          <Select
            value={days}
            onChange={setDays}
            options={DAYS_OPTIONS}
            style={{ width: 130 }}
          />
          <span>平台:</span>
          <Select
            mode="multiple"
            allowClear
            placeholder="不选 = 全部"
            value={platforms}
            onChange={setPlatforms}
            options={PLATFORM_OPTIONS}
            style={{ minWidth: 240 }}
          />
          <span>条数上限:</span>
          <InputNumber min={5} max={100} value={limit} onChange={(v) => setLimit(Number(v) || 20)} />
          <Button type="primary" onClick={fetchTopDomains}>
            重新加载
          </Button>
        </Space>
      </Card>

      {/* ---------- 2. Top domains ---------- */}
      <Card
        title="品类高频引用域名 (Top Domains)"
        extra={
          <Typography.Text type="secondary">
            AI 在该客户的探针问题里最常引用的第三方域名 — 优先去这些站铺内容
          </Typography.Text>
        }
      >
        {topDomains.length === 0 && !topLoading ? (
          <Empty description="暂无数据 — 跑一轮 Run / 或检查筛选条件" />
        ) : (
          <Table
            loading={topLoading}
            rowKey="domain"
            dataSource={topDomains}
            columns={topDomainsColumns}
            pagination={false}
            size="small"
          />
        )}
      </Card>

      {/* ---------- 3. Competitor assets ---------- */}
      <Card
        title="竞品 GEO 资产清单 (Competitor Assets)"
        extra={
          <Typography.Text type="secondary">
            AI 提到竞品名时,实际引用了哪些 URL — 反推竞品的 AI 弹药库
          </Typography.Text>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="本报表基于 raw_answer LIKE 匹配竞品名,只覆盖 monitor 跑过的题目。若要精确归因,可把竞品名加进客户资料的 keywords/brand_aliases,之后 supports_brand_mention 会更准。"
        />
        <Space style={{ marginBottom: 12 }}>
          <Input
            placeholder="竞品名,逗号分隔,如:Biorun,CJ,MeetSocks,Sinoknit"
            value={competitorsInput}
            onChange={(e) => setCompetitorsInput(e.target.value)}
            style={{ width: 480 }}
            onPressEnter={fetchCompetitors}
          />
          <Button type="primary" loading={competitorLoading} onClick={fetchCompetitors}>
            查询
          </Button>
        </Space>

        {competitorResults.length === 0 ? (
          <Empty description="先填竞品名查询" />
        ) : (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {competitorResults.map((g) => (
              <Card key={g.competitor} type="inner" title={`竞品: ${g.competitor}`}>
                {g.items.length === 0 ? (
                  <Empty
                    description={`AI 回答里没有匹配到 "${g.competitor}",或匹配的 monitor 都没解析出 citation`}
                  />
                ) : (
                  <Table
                    rowKey="domain"
                    dataSource={g.items}
                    columns={competitorAssetColumns}
                    pagination={false}
                    size="small"
                  />
                )}
              </Card>
            ))}
          </Space>
        )}
      </Card>
    </Space>
  );
}
