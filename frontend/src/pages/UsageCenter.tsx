/**
 * LLM 用量与成本中心 (M-cost)。
 *
 * - 顶部 KPI: 总调用 / 总 token / 总成本 / 平均延迟 / 错误数
 * - 按 provider/model 分布
 * - 按 purpose (pipeline 步骤) 分布
 * - 按客户排行
 * - 最近 N 条调用明细
 */
import { useEffect, useState } from 'react';
import {
  Card,
  Col,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getUsageByClient,
  getUsageCalls,
  getUsageSummary,
  type UsageByClientRow,
  type UsageByModelRow,
  type UsageByPurposeRow,
  type UsageCallRow,
  type UsagePeriod,
  type UsageSummary,
} from '../api/usage';
import { listClients } from '../api/clients';
import type { Client } from '../api/types';

const PERIOD_OPTIONS: { value: UsagePeriod; label: string }[] = [
  { value: 'day', label: '今日' },
  { value: 'week', label: '近 7 天' },
  { value: 'month', label: '近 30 天' },
  { value: 'all', label: '全部' },
];

const fmtUsd = (v: number) => `$${(v ?? 0).toFixed(4)}`;
const fmtInt = (v: number) => (v ?? 0).toLocaleString();

export default function UsageCenter() {
  const [period, setPeriod] = useState<UsagePeriod>('month');
  const [clientId, setClientId] = useState<number | undefined>(undefined);
  const [clients, setClients] = useState<Client[]>([]);

  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [byClient, setByClient] = useState<UsageByClientRow[]>([]);
  const [calls, setCalls] = useState<UsageCallRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listClients({ page: 1, page_size: 200 })
      .then((p) => setClients(p?.items ?? []))
      .catch(() => {});
  }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [s, bc, cs] = await Promise.all([
        getUsageSummary({ period, client_id: clientId }),
        getUsageByClient({ period }),
        getUsageCalls({ client_id: clientId, limit: 100 }),
      ]);
      setSummary(s);
      setByClient(bc?.items ?? []);
      setCalls(cs?.items ?? []);
    } catch {
      /* toast'd */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, clientId]);

  const total = summary?.total;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title="LLM 用量与成本"
        extra={
          <Space>
            <Segmented
              value={period}
              onChange={(v) => setPeriod(v as UsagePeriod)}
              options={PERIOD_OPTIONS}
            />
            <Select
              allowClear
              placeholder="按客户过滤"
              style={{ width: 200 }}
              value={clientId}
              onChange={(v) => setClientId(v)}
              showSearch
              optionFilterProp="label"
              options={clients.map((c) => ({ value: c.id, label: c.name }))}
            />
            <Typography.Link onClick={fetchAll}>
              <ReloadOutlined /> 刷新
            </Typography.Link>
          </Space>
        }
      >
        <Row gutter={16}>
          <Col span={5}>
            <Statistic title="调用次数" value={fmtInt(total?.calls ?? 0)} loading={loading} />
          </Col>
          <Col span={5}>
            <Statistic
              title="总 token"
              value={fmtInt(total?.total_tokens ?? 0)}
              loading={loading}
            />
          </Col>
          <Col span={5}>
            <Statistic
              title="总成本 (USD)"
              value={fmtUsd(total?.usd_cost ?? 0)}
              loading={loading}
              valueStyle={{ color: '#cf1322' }}
            />
          </Col>
          <Col span={5}>
            <Statistic
              title="平均延迟 (ms)"
              value={fmtInt(total?.avg_latency_ms ?? 0)}
              loading={loading}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title="失败次数"
              value={fmtInt(total?.error_calls ?? 0)}
              loading={loading}
              valueStyle={{
                color: (total?.error_calls ?? 0) > 0 ? '#cf1322' : undefined,
              }}
            />
          </Col>
        </Row>
        {total && total.total_tokens > 0 && (
          <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            prompt {fmtInt(total.prompt_tokens)} tok · completion{' '}
            {fmtInt(total.completion_tokens)} tok
          </Typography.Paragraph>
        )}
      </Card>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="按 provider / model" size="small">
            <Table<UsageByModelRow>
              size="small"
              rowKey={(r) => `${r.provider}-${r.model}`}
              loading={loading}
              dataSource={summary?.by_model ?? []}
              pagination={false}
              columns={[
                { title: 'Provider', dataIndex: 'provider', width: 100 },
                { title: 'Model', dataIndex: 'model', ellipsis: true },
                {
                  title: '调用',
                  dataIndex: 'calls',
                  width: 70,
                  align: 'right',
                  render: fmtInt,
                },
                {
                  title: 'Token',
                  dataIndex: 'total_tokens',
                  width: 100,
                  align: 'right',
                  render: fmtInt,
                },
                {
                  title: '成本',
                  dataIndex: 'usd_cost',
                  width: 100,
                  align: 'right',
                  render: fmtUsd,
                },
              ]}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="按 purpose (pipeline 步骤)" size="small">
            <Table<UsageByPurposeRow>
              size="small"
              rowKey="purpose"
              loading={loading}
              dataSource={summary?.by_purpose ?? []}
              pagination={{ pageSize: 8 }}
              columns={[
                { title: 'Purpose', dataIndex: 'purpose', ellipsis: true },
                {
                  title: '调用',
                  dataIndex: 'calls',
                  width: 70,
                  align: 'right',
                  render: fmtInt,
                },
                {
                  title: 'Token',
                  dataIndex: 'total_tokens',
                  width: 100,
                  align: 'right',
                  render: fmtInt,
                },
                {
                  title: '成本',
                  dataIndex: 'usd_cost',
                  width: 100,
                  align: 'right',
                  render: fmtUsd,
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Card title="客户成本排行" size="small">
        <Table<UsageByClientRow>
          size="small"
          rowKey={(r) => `${r.client_id ?? 'null'}`}
          loading={loading}
          dataSource={byClient}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: '客户', dataIndex: 'client_name', ellipsis: true },
            {
              title: '套餐',
              dataIndex: 'plan',
              width: 100,
              render: (v: string) => <Tag>{v}</Tag>,
            },
            {
              title: '调用',
              dataIndex: 'calls',
              width: 100,
              align: 'right',
              render: fmtInt,
            },
            {
              title: 'Token',
              dataIndex: 'total_tokens',
              width: 130,
              align: 'right',
              render: fmtInt,
            },
            {
              title: '成本 (USD)',
              dataIndex: 'usd_cost',
              width: 130,
              align: 'right',
              render: (v: number) => (
                <Typography.Text type="danger">{fmtUsd(v)}</Typography.Text>
              ),
            },
          ]}
        />
      </Card>

      <Card title="最近 100 次调用" size="small">
        <Table<UsageCallRow>
          size="small"
          rowKey="id"
          loading={loading}
          dataSource={calls}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 1100 }}
          expandable={{
            rowExpandable: (r) => Boolean(r.error),
            expandedRowRender: (r) => (
              <Typography.Paragraph type="danger" style={{ margin: 0 }}>
                {r.error}
              </Typography.Paragraph>
            ),
          }}
          columns={[
            {
              title: '时间',
              dataIndex: 'created_at',
              width: 140,
              render: (v: string | null) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-'),
            },
            { title: 'Purpose', dataIndex: 'purpose', width: 200, ellipsis: true },
            { title: 'Provider', dataIndex: 'provider', width: 90 },
            { title: 'Model', dataIndex: 'model', width: 160, ellipsis: true },
            {
              title: 'Prompt',
              dataIndex: 'prompt_tokens',
              width: 80,
              align: 'right',
              render: fmtInt,
            },
            {
              title: 'Completion',
              dataIndex: 'completion_tokens',
              width: 90,
              align: 'right',
              render: fmtInt,
            },
            {
              title: '成本',
              dataIndex: 'usd_cost',
              width: 100,
              align: 'right',
              render: fmtUsd,
            },
            {
              title: '延迟',
              dataIndex: 'latency_ms',
              width: 80,
              align: 'right',
              render: (v: number) => `${v} ms`,
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 80,
              render: (v: string) => (
                <Tag color={v === 'ok' ? 'success' : 'error'}>{v}</Tag>
              ),
            },
            { title: '监测对象', dataIndex: 'client_id', width: 90 },
          ]}
        />
      </Card>
    </Space>
  );
}
