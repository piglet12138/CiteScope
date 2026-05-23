/**
 * 监测中心 — 三个 Tab:
 *   1. 概览:KPI / 趋势 / 平台明细 / 最近结果
 *   2. 实验运行 (Runs):该客户所有 Run 的列表 + 加入对比
 *   3. 对比视图:多 Run 横向对比(矩阵 + 雷达图)
 *
 * 触发监测改为「创建 Run」(POST /clients/:cid/runs),旧 trigger 兼容路由不再使用。
 */
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Empty,
  Input,
  List,
  Modal,
  Progress,
  Radio,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { ReloadOutlined, ThunderboltOutlined, BarChartOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useParams } from 'react-router-dom';
import dayjs from 'dayjs';
import { listQuestions } from '../api/questions';
import {
  compareMonitorRuns,
  createMonitorRun,
  getMetrics,
  listMonitorResults,
  listMonitorRuns,
} from '../api/monitor';
import type {
  Metrics,
  MonitorPlatform,
  MonitorResult,
  MonitorRun,
  Question,
  RunCompareOut,
  SearchResultItem,
} from '../api/types';
import { useTaskPolling } from '../hooks/useTaskPolling';
import CitationSourcesPanel from '../components/CitationSourcesPanel';

type Period = 'today' | 'week' | 'month';

const platformLabel: Record<string, string> = {
  perplexity: 'Perplexity',
  chatgpt: 'ChatGPT',
  google_ai: 'Google AI',
  doubao: '豆包',
  deepseek: 'DeepSeek',
  kimi: 'Kimi',
};

const CITATION_RE = /\[citation:(\d+)\]/g;

function renderAnswerWithCitations(
  raw: string | null,
  sources: SearchResultItem[] | null,
): ReactNode {
  if (!raw) return <Typography.Text type="secondary">(空回答)</Typography.Text>;
  const byIndex = new Map<number, SearchResultItem>();
  (sources ?? []).forEach((s) => {
    if (typeof s.cite_index === 'number') byIndex.set(s.cite_index, s);
  });

  const nodes: ReactNode[] = [];
  let last = 0;
  const re = new RegExp(CITATION_RE.source, 'g');
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    if (m.index > last) nodes.push(raw.slice(last, m.index));
    const n = parseInt(m[1], 10);
    const src = byIndex.get(n);
    const tip = src ? `${src.title || src.url || `引用 ${n}`}` : `引用 ${n} (未匹配到来源)`;
    nodes.push(
      <Tooltip key={`c-${m.index}`} title={tip}>
        {src?.url ? (
          <a
            href={src.url}
            target="_blank"
            rel="noreferrer"
            style={{ margin: '0 2px', textDecoration: 'none' }}
          >
            <Tag color="blue" style={{ cursor: 'pointer', margin: 0 }}>
              {n}
            </Tag>
          </a>
        ) : (
          <Tag color="default" style={{ margin: '0 2px' }}>
            {n}
          </Tag>
        )}
      </Tooltip>,
    );
    last = m.index + m[0].length;
  }
  if (last < raw.length) nodes.push(raw.slice(last));
  return nodes;
}

export default function MonitorCenter() {
  const { id } = useParams();
  const clientId = Number(id);

  // ---------- 概览 Tab ----------
  const [period, setPeriod] = useState<Period>('week');
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState<boolean>(false);
  const [results, setResults] = useState<MonitorResult[]>([]);
  const [resultsLoading, setResultsLoading] = useState<boolean>(false);
  const [detailResult, setDetailResult] = useState<MonitorResult | null>(null);

  // ---------- Runs Tab ----------
  const [runs, setRuns] = useState<MonitorRun[]>([]);
  const [runsLoading, setRunsLoading] = useState<boolean>(false);
  const [selectedRunIds, setSelectedRunIds] = useState<number[]>([]);

  // ---------- 对比 Tab ----------
  const [compareData, setCompareData] = useState<RunCompareOut | null>(null);
  const [compareLoading, setCompareLoading] = useState<boolean>(false);

  // 当前活动 tab
  const [activeTab, setActiveTab] = useState<'overview' | 'runs' | 'compare' | 'citations'>(
    'overview',
  );

  // ---------- 触发监测 Modal ----------
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [triggerOpen, setTriggerOpen] = useState<boolean>(false);
  const [triggerSubmitting, setTriggerSubmitting] = useState<boolean>(false);
  const [triggerMode, setTriggerMode] = useState<'library' | 'adhoc'>('library');
  const [runName, setRunName] = useState<string>('');
  const [runNote, setRunNote] = useState<string>('');
  const [questionPool, setQuestionPool] = useState<Question[]>([]);
  const [questionPoolLoading, setQuestionPoolLoading] = useState<boolean>(false);
  const [pickedIds, setPickedIds] = useState<number[]>([]);
  const [adhocText, setAdhocText] = useState<string>('');
  const [pickedPlatforms, setPickedPlatforms] = useState<MonitorPlatform[]>(['perplexity']);

  const detailNodes = useMemo(
    () =>
      detailResult
        ? renderAnswerWithCitations(detailResult.raw_answer, detailResult.search_results)
        : null,
    [detailResult],
  );

  const fetchMetrics = async (p: Period = period) => {
    setMetricsLoading(true);
    try {
      const m = await getMetrics(clientId, p);
      setMetrics(m);
    } finally {
      setMetricsLoading(false);
    }
  };

  const fetchResults = async () => {
    setResultsLoading(true);
    try {
      const page = await listMonitorResults(clientId, { page: 1, page_size: 50 });
      setResults(page?.items ?? []);
    } finally {
      setResultsLoading(false);
    }
  };

  const fetchRuns = async () => {
    setRunsLoading(true);
    try {
      const page = await listMonitorRuns(clientId, { page: 1, page_size: 50 });
      setRuns(page?.items ?? []);
    } finally {
      setRunsLoading(false);
    }
  };

  useEffect(() => {
    if (!Number.isFinite(clientId)) return;
    fetchMetrics(period);
    fetchResults();
    fetchRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, period]);

  const { task: activeTask } = useTaskPolling(activeTaskId, {
    intervalMs: 2000,
    onSuccess: (t) => {
      const r = (t.result ?? {}) as Record<string, unknown>;
      const checked = Number(r.checked ?? 0);
      const errs = (r.errors as string[] | undefined) ?? [];
      const skipped = r.skipped_quota;
      let msg = `监测完成,成功 ${checked} 条`;
      if (errs.length > 0) msg += `,失败 ${errs.length} 条`;
      if (Array.isArray(skipped) && skipped.length > 0) {
        msg += `;${skipped.join('/')} 今日配额已满,已跳过`;
      }
      message.success(msg);
      setActiveTaskId(null);
      fetchMetrics();
      fetchResults();
      fetchRuns();
    },
    onError: (t) => {
      message.error(`监测失败:${t.error ?? '未知错误'}`);
      setActiveTaskId(null);
    },
  });

  const openTriggerModal = async () => {
    setRunName(`实验 ${dayjs().format('MM-DD HH:mm')}`);
    setRunNote('');
    setPickedIds([]);
    setAdhocText('');
    setPickedPlatforms(['perplexity']);
    setTriggerMode('library');
    setTriggerOpen(true);
    setQuestionPoolLoading(true);
    try {
      const page = await listQuestions(clientId, { page: 1, page_size: 200 });
      setQuestionPool(page?.items ?? []);
    } finally {
      setQuestionPoolLoading(false);
    }
  };

  const parseAdhocLines = (raw: string): string[] =>
    raw
      .split('\n')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

  const submitTrigger = async () => {
    if (!runName.trim()) {
      message.warning('请填写实验名');
      return;
    }
    if (pickedPlatforms.length === 0) {
      message.warning('至少选一个平台');
      return;
    }

    let questionCount = 0;
    const body: Parameters<typeof createMonitorRun>[1] = {
      name: runName.trim(),
      note: runNote.trim() || undefined,
      platforms: pickedPlatforms,
    };

    if (triggerMode === 'library') {
      if (pickedIds.length === 0) {
        message.warning('请至少勾选一个问题');
        return;
      }
      if (pickedIds.length > 20) {
        message.warning('一次最多 20 个问题 (防封号硬上限)');
        return;
      }
      body.question_ids = pickedIds;
      questionCount = pickedIds.length;
    } else {
      const lines = parseAdhocLines(adhocText);
      if (lines.length === 0) {
        message.warning('请输入至少一行问题文本');
        return;
      }
      if (lines.length > 20) {
        message.warning('一次最多 20 个问题 (防封号硬上限)');
        return;
      }
      body.extra_question_texts = lines;
      questionCount = lines.length;
    }

    setTriggerSubmitting(true);
    try {
      const ref = await createMonitorRun(clientId, body);
      setActiveTaskId(ref.task_id);
      setTriggerOpen(false);
      const total = questionCount * pickedPlatforms.length;
      message.info(
        `已创建 Run #${ref.run_id},共 ${total} 次查询,预计 ${Math.ceil((total * 35) / 60)} 分钟`,
      );
      fetchRuns();
    } finally {
      setTriggerSubmitting(false);
    }
  };

  const triggerCompare = async (ids: number[]) => {
    if (ids.length < 2) {
      message.warning('请至少选择 2 个 Run 进行对比');
      return;
    }
    setCompareLoading(true);
    setActiveTab('compare');
    try {
      const data = await compareMonitorRuns(ids);
      setCompareData(data);
    } finally {
      setCompareLoading(false);
    }
  };

  // -------- charts --------
  const trend = metrics?.trend ?? [];
  const lineOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 24, bottom: 32 },
    xAxis: {
      type: 'category',
      data: trend.map((t) => t.date),
    },
    yAxis: {
      type: 'value',
      max: 1,
      axisLabel: {
        formatter: (v: number) => `${(v * 100).toFixed(0)}%`,
      },
    },
    series: [
      {
        type: 'line',
        data: trend.map((t) => t.mention_rate),
        smooth: true,
        areaStyle: { opacity: 0.2 },
        name: '提及率',
      },
    ],
  };

  const radarOption = useMemo(() => {
    if (!compareData || compareData.runs.length === 0) return null;
    const indicators = compareData.platforms.map((p) => ({
      name: platformLabel[p] ?? p,
      max: 1,
    }));
    return {
      tooltip: { trigger: 'item' },
      legend: {
        bottom: 0,
        data: compareData.runs.map((r) => r.run_name),
      },
      radar: {
        indicator: indicators.length
          ? indicators
          : [{ name: 'all', max: 1 }],
        axisName: { color: '#555' },
      },
      series: [
        {
          type: 'radar',
          areaStyle: { opacity: 0.15 },
          data: compareData.runs.map((r) => ({
            name: r.run_name,
            value: compareData.platforms.map((p) => {
              const cell = r.by_platform.find((c) => c.platform === p);
              return cell ? cell.mention_rate : 0;
            }),
          })),
        },
      ],
    };
  }, [compareData]);

  if (!Number.isFinite(clientId)) {
    return <Empty description="无效的监测对象 ID" />;
  }

  // -------- 概览 Tab content --------
  const overviewTab = (
    <Spin spinning={metricsLoading}>
      {activeTask && activeTask.status !== 'success' && activeTask.status !== 'failed' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={
            <Space direction="vertical" style={{ width: '100%' }} size={4}>
              <Typography.Text>
                监测进行中 — 每个查询之间会间隔 8-20 秒模拟人类操作 (防封号)
              </Typography.Text>
              <Progress
                percent={activeTask.progress}
                status={activeTask.status === 'running' ? 'active' : 'normal'}
                size="small"
              />
            </Space>
          }
        />
      )}

      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="提及率"
              value={((metrics?.mention_rate ?? 0) * 100).toFixed(1)}
              suffix="%"
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="首位提及率"
              value={((metrics?.first_mention_rate ?? 0) * 100).toFixed(1)}
              suffix="%"
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="带链接引用率"
              value={((metrics?.link_citation_rate ?? 0) * 100).toFixed(1)}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      <Card type="inner" title="提及率趋势" style={{ marginTop: 16 }}>
        {trend.length > 0 ? (
          <ReactECharts option={lineOption} style={{ height: 280 }} />
        ) : (
          <Empty description="暂无趋势数据" />
        )}
      </Card>

      <Card type="inner" title="平台明细" style={{ marginTop: 16 }}>
        <Table
          rowKey="platform"
          dataSource={metrics?.by_platform ?? []}
          pagination={false}
          columns={[
            {
              title: '平台',
              dataIndex: 'platform',
              render: (v: string) => platformLabel[v] ?? v,
            },
            {
              title: '提及率',
              dataIndex: 'mention_rate',
              render: (v: number) => `${(v * 100).toFixed(1)}%`,
            },
            { title: '样本量', dataIndex: 'sample_size' },
          ]}
        />
      </Card>

      <Card type="inner" title="最近监测结果" style={{ marginTop: 16 }}>
        <Table<MonitorResult>
          rowKey="id"
          loading={resultsLoading}
          dataSource={results}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: 'ID', dataIndex: 'id', width: 70 },
            { title: 'Run', dataIndex: 'run_id', width: 70, render: (v) => v ?? '-' },
            {
              title: '平台',
              dataIndex: 'platform',
              width: 100,
              render: (v: MonitorPlatform) => platformLabel[v] ?? v,
            },
            { title: '题目ID', dataIndex: 'question_id', width: 90 },
            {
              title: '提及',
              dataIndex: 'is_mentioned',
              width: 80,
              render: (v: boolean) => (v ? <Tag color="green">是</Tag> : <Tag>否</Tag>),
            },
            { title: '位置', dataIndex: 'position', width: 70 },
            {
              title: '链接',
              dataIndex: 'has_link',
              width: 70,
              render: (v: boolean) => (v ? '✓' : '-'),
            },
            {
              title: '情感',
              dataIndex: 'sentiment',
              width: 90,
              render: (v: string | null) => {
                if (!v) return '-';
                const color = v === 'positive' ? 'green' : v === 'negative' ? 'red' : 'default';
                return <Tag color={color}>{v}</Tag>;
              },
            },
            {
              title: '回答摘要',
              dataIndex: 'raw_answer',
              ellipsis: true,
              render: (v: string | null) => {
                const stripped = (v ?? '').replace(CITATION_RE, '').trim();
                return (
                  <Typography.Text ellipsis style={{ maxWidth: 280 }}>
                    {stripped || '-'}
                  </Typography.Text>
                );
              },
            },
            {
              title: '来源',
              dataIndex: 'search_results',
              width: 70,
              render: (v: SearchResultItem[] | null) =>
                v && v.length > 0 ? <Tag color="geekblue">{v.length}</Tag> : '-',
            },
            {
              title: '检查时间',
              dataIndex: 'checked_at',
              width: 160,
              render: (v: string) => (v ? dayjs(v).format('MM-DD HH:mm') : '-'),
            },
            {
              title: '操作',
              key: 'actions',
              width: 80,
              fixed: 'right' as const,
              render: (_: unknown, row: MonitorResult) => (
                <Button type="link" size="small" onClick={() => setDetailResult(row)}>
                  详情
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </Spin>
  );

  // -------- Runs Tab content --------
  const runStatusMeta: Record<string, { color: string; label: string }> = {
    running: { color: 'processing', label: '进行中' },
    completed: { color: 'success', label: '完成' },
    completed_with_errors: { color: 'warning', label: '有部分失败' },
    failed: { color: 'error', label: '失败' },
  };

  const runsTab = (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={fetchRuns}>
          刷新
        </Button>
        <Button
          icon={<BarChartOutlined />}
          type="primary"
          disabled={selectedRunIds.length < 2}
          onClick={() => triggerCompare(selectedRunIds)}
        >
          对比选中 ({selectedRunIds.length})
        </Button>
        <Typography.Text type="secondary">
          勾选 2 个以上 Run 进入对比视图
        </Typography.Text>
      </Space>
      <Table<MonitorRun>
        rowKey="id"
        loading={runsLoading}
        dataSource={runs}
        pagination={{ pageSize: 10 }}
        rowSelection={{
          selectedRowKeys: selectedRunIds,
          onChange: (keys) => setSelectedRunIds(keys as number[]),
        }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 70 },
          { title: '实验名', dataIndex: 'name' },
          {
            title: '平台',
            dataIndex: 'platforms',
            width: 200,
            render: (v: string[]) =>
              (v || []).map((p) => (
                <Tag key={p}>{platformLabel[p] ?? p}</Tag>
              )),
          },
          { title: '题数', dataIndex: 'question_count', width: 80 },
          { title: '样本', dataIndex: 'sample_size', width: 80 },
          {
            title: '提及率',
            dataIndex: 'mention_rate',
            width: 100,
            render: (v: number) => `${(v * 100).toFixed(1)}%`,
          },
          {
            title: '状态',
            dataIndex: 'status',
            width: 120,
            render: (v: string) => {
              const m = runStatusMeta[v] ?? { color: 'default', label: v };
              return <Tag color={m.color}>{m.label}</Tag>;
            },
          },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 160,
            render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
          },
          {
            title: '操作',
            key: 'actions',
            width: 110,
            render: (_: unknown, row: MonitorRun) => (
              <Button
                size="small"
                type="link"
                onClick={() => triggerCompare([row.id])}
              >
                查看
              </Button>
            ),
          },
        ]}
      />
    </>
  );

  // -------- 对比 Tab content --------
  const compareTab = (
    <Spin spinning={compareLoading}>
      {!compareData || compareData.runs.length === 0 ? (
        <Empty description="去「实验运行」勾选 2 个 Run 再进入对比" />
      ) : (
        <>
          <Card type="inner" title="平台 × Run 提及率矩阵" style={{ marginBottom: 16 }}>
            <Table
              rowKey="run_id"
              dataSource={compareData.runs}
              pagination={false}
              columns={[
                { title: '实验', dataIndex: 'run_name' },
                {
                  title: '合计',
                  key: 'all',
                  render: (_: unknown, r) =>
                    `${(r.overall.mention_rate * 100).toFixed(1)}% (n=${r.overall.sample_size})`,
                },
                ...compareData.platforms.map((p) => ({
                  title: platformLabel[p] ?? p,
                  key: p,
                  render: (_: unknown, r: RunCompareOut['runs'][number]) => {
                    const cell = r.by_platform.find((c) => c.platform === p);
                    return cell
                      ? `${(cell.mention_rate * 100).toFixed(1)}% (n=${cell.sample_size})`
                      : '-';
                  },
                })),
              ]}
            />
          </Card>

          {radarOption && (
            <Card type="inner" title="各平台提及率雷达图">
              <ReactECharts option={radarOption} style={{ height: 380 }} />
            </Card>
          )}
        </>
      )}
    </Spin>
  );

  return (
    <>
      <Card
        title="GEO 效果监测"
        extra={
          <Space>
            <Radio.Group value={period} onChange={(e) => setPeriod(e.target.value)}>
              <Radio.Button value="today">今日</Radio.Button>
              <Radio.Button value="week">本周</Radio.Button>
              <Radio.Button value="month">本月</Radio.Button>
            </Radio.Group>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                fetchMetrics();
                fetchResults();
                fetchRuns();
              }}
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={openTriggerModal}
              loading={!!activeTaskId}
              disabled={!!activeTaskId}
            >
              新建实验运行
            </Button>
          </Space>
        }
      >
        <Tabs
          activeKey={activeTab}
          onChange={(k) =>
            setActiveTab(k as 'overview' | 'runs' | 'compare' | 'citations')
          }
          items={[
            { key: 'overview', label: '概览', children: overviewTab },
            { key: 'runs', label: `实验运行 (${runs.length})`, children: runsTab },
            { key: 'compare', label: '对比视图', children: compareTab },
            {
              key: 'citations',
              label: '引用来源',
              children: <CitationSourcesPanel clientId={clientId} />,
            },
          ]}
        />
      </Card>

      <Modal
        open={triggerOpen}
        onCancel={() => setTriggerOpen(false)}
        onOk={submitTrigger}
        okText="开始监测"
        cancelText="取消"
        confirmLoading={triggerSubmitting}
        title="新建实验运行 (Run)"
        width={720}
        destroyOnClose
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="防封号机制已启用"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              <li>每个查询之间随机间隔 8-20 秒,模拟人类阅读节奏</li>
              <li>每个平台每天最多 30 次 (硬上限,超出自动跳过)</li>
              <li>一次最多 20 个问题 (硬上限),建议 5-10 个起步</li>
            </ul>
          }
        />

        <Row gutter={12} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Typography.Text strong>实验名 *</Typography.Text>
            <Input
              value={runName}
              onChange={(e) => setRunName(e.target.value)}
              placeholder="例如:2026-Q2 baseline / 改 llms.txt 后第 1 周"
              maxLength={120}
            />
          </Col>
          <Col span={12}>
            <Typography.Text strong>备注 (可选)</Typography.Text>
            <Input
              value={runNote}
              onChange={(e) => setRunNote(e.target.value)}
              placeholder="对照说明 / 本次干预动作 ..."
              maxLength={300}
            />
          </Col>
        </Row>

        <Tabs
          activeKey={triggerMode}
          onChange={(k) => setTriggerMode(k as 'library' | 'adhoc')}
          items={[
            {
              key: 'library',
              label: '从题库选择',
              children: (
                <Spin spinning={questionPoolLoading}>
                  {questionPool.length === 0 ? (
                    <Empty description="题库为空,先去监测对象详情录入,或切到「临时提问」" />
                  ) : (
                    <>
                      <Space style={{ marginBottom: 8 }}>
                        <Button
                          size="small"
                          onClick={() =>
                            setPickedIds(questionPool.slice(0, 5).map((q) => q.id))
                          }
                        >
                          快选前 5 个
                        </Button>
                        <Button size="small" onClick={() => setPickedIds([])}>
                          清空
                        </Button>
                        <Typography.Text type="secondary">
                          已选 {pickedIds.length} / {questionPool.length}
                        </Typography.Text>
                      </Space>
                      <div
                        style={{
                          maxHeight: 240,
                          overflowY: 'auto',
                          border: '1px solid #f0f0f0',
                          borderRadius: 6,
                          padding: 8,
                        }}
                      >
                        <Checkbox.Group
                          value={pickedIds}
                          onChange={(v) => setPickedIds(v as number[])}
                          style={{ width: '100%' }}
                        >
                          <Space direction="vertical" style={{ width: '100%' }}>
                            {questionPool.map((q) => (
                              <Checkbox key={q.id} value={q.id}>
                                <Typography.Text>
                                  <Tag color="default">{q.category}</Tag>
                                  {q.text}
                                </Typography.Text>
                              </Checkbox>
                            ))}
                          </Space>
                        </Checkbox.Group>
                      </div>
                    </>
                  )}
                </Spin>
              ),
            },
            {
              key: 'adhoc',
              label: '临时提问',
              children: (
                <>
                  <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
                    每行一个问题。临时问题会以 <Tag>adhoc</Tag> 类别写入,不会出现在主题库,但本次监测结果会保留。
                  </Typography.Paragraph>
                  <Input.TextArea
                    value={adhocText}
                    onChange={(e) => setAdhocText(e.target.value)}
                    placeholder={'例如:\n中国哪家工厂的袜子最值得 OEM?\n冬天最舒适的羊毛袜品牌?'}
                    rows={6}
                    showCount
                    maxLength={2000}
                  />
                </>
              ),
            },
          ]}
        />

        <Divider style={{ margin: '12px 0' }} />

        <div style={{ marginBottom: 8 }}>
          <Typography.Text strong>目标 AI 引擎:</Typography.Text>
        </div>
        <Checkbox.Group
          value={pickedPlatforms}
          onChange={(v) => setPickedPlatforms(v as MonitorPlatform[])}
        >
          <Checkbox value="perplexity">Perplexity</Checkbox>
          <Checkbox value="chatgpt">ChatGPT</Checkbox>
          <Checkbox value="google_ai">Google AI (Gemini)</Checkbox>
          <Checkbox value="doubao">豆包</Checkbox>
          <Checkbox value="deepseek">DeepSeek</Checkbox>
          <Checkbox value="kimi">Kimi</Checkbox>
        </Checkbox.Group>

        <div style={{ marginTop: 12 }}>
          {(() => {
            const qCount =
              triggerMode === 'library' ? pickedIds.length : parseAdhocLines(adhocText).length;
            const total = qCount * pickedPlatforms.length;
            if (total === 0) {
              return <Typography.Text type="secondary">请先选/输问题并勾选平台</Typography.Text>;
            }
            const minMin = Math.ceil((total * 25 + total * 8) / 60);
            const maxMin = Math.ceil((total * 40 + total * 20) / 60);
            return (
              <Typography.Text type="secondary">
                共 {qCount} 个问题 × {pickedPlatforms.length} 个引擎 = {total} 次查询,
                预计耗时 {minMin}-{maxMin} 分钟
              </Typography.Text>
            );
          })()}
        </div>
      </Modal>

      <Modal
        open={!!detailResult}
        onCancel={() => setDetailResult(null)}
        footer={null}
        width={760}
        title={
          detailResult
            ? `监测详情 #${detailResult.id} · ${platformLabel[detailResult.platform] ?? detailResult.platform}`
            : '监测详情'
        }
        destroyOnClose
      >
        {detailResult && (
          <>
            <Space wrap size={[8, 8]} style={{ marginBottom: 12 }}>
              <Tag color={detailResult.is_mentioned ? 'green' : 'default'}>
                {detailResult.is_mentioned ? '已提及' : '未提及'}
              </Tag>
              {detailResult.position != null && <Tag>位置 {detailResult.position}</Tag>}
              {detailResult.has_link && <Tag color="cyan">含链接</Tag>}
              {detailResult.sentiment && (
                <Tag
                  color={
                    detailResult.sentiment === 'positive'
                      ? 'green'
                      : detailResult.sentiment === 'negative'
                        ? 'red'
                        : 'default'
                  }
                >
                  {detailResult.sentiment}
                </Tag>
              )}
              <Typography.Text type="secondary">
                {dayjs(detailResult.checked_at).format('YYYY-MM-DD HH:mm:ss')}
              </Typography.Text>
            </Space>

            <Card type="inner" size="small" title="AI 回答">
              <Typography.Paragraph
                style={{
                  whiteSpace: 'pre-wrap',
                  margin: 0,
                  maxHeight: 360,
                  overflowY: 'auto',
                }}
              >
                {detailNodes}
              </Typography.Paragraph>
            </Card>

            <Divider style={{ margin: '16px 0 8px' }}>
              引用来源
              {detailResult.search_results && detailResult.search_results.length > 0
                ? ` (${detailResult.search_results.length})`
                : ''}
            </Divider>

            {detailResult.search_results && detailResult.search_results.length > 0 ? (
              <List<SearchResultItem>
                size="small"
                dataSource={detailResult.search_results}
                renderItem={(item) => {
                  let host = '';
                  try {
                    host = item.url ? new URL(item.url).hostname.replace(/^www\./, '') : '';
                  } catch {
                    host = '';
                  }
                  const publishedLabel =
                    typeof item.published_at === 'number' && item.published_at > 0
                      ? dayjs(item.published_at * 1000).format('YYYY-MM-DD')
                      : '';
                  return (
                    <List.Item key={`${item.cite_index}-${item.url}`}>
                      <List.Item.Meta
                        avatar={
                          <Space size={4} align="center">
                            {item.cite_index != null && (
                              <Tag color="blue" style={{ marginRight: 0 }}>
                                {item.cite_index}
                              </Tag>
                            )}
                            {item.site_icon ? (
                              <img
                                src={item.site_icon}
                                alt=""
                                width={16}
                                height={16}
                                style={{ borderRadius: 3, display: 'block' }}
                                onError={(e) => {
                                  (e.currentTarget as HTMLImageElement).style.display = 'none';
                                }}
                              />
                            ) : null}
                          </Space>
                        }
                        title={
                          item.url ? (
                            <a href={item.url} target="_blank" rel="noreferrer">
                              {item.title || item.url}
                            </a>
                          ) : (
                            <Typography.Text>{item.title || '(无标题)'}</Typography.Text>
                          )
                        }
                        description={
                          <>
                            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                              {item.snippet || item.url}
                            </Typography.Text>
                            {(host || publishedLabel) && (
                              <div style={{ marginTop: 4 }}>
                                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                                  {host}
                                  {host && publishedLabel ? ' · ' : ''}
                                  {publishedLabel}
                                </Typography.Text>
                              </div>
                            )}
                          </>
                        }
                      />
                    </List.Item>
                  );
                }}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次回答未联网搜索" />
            )}
          </>
        )}
      </Modal>
    </>
  );
}
