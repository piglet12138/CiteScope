/**
 * 监测对象详情 — 品牌档案 / 探针题库(手工 + CSV) / 报告。
 */
import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  InputNumber,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
  RadarChartOutlined,
} from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { getClient, updateClient } from '../api/clients';
import {
  bulkCreateQuestions,
  deleteQuestion,
  importQuestionsCSV,
  listQuestions,
} from '../api/questions';
import { createReport, listReports } from '../api/monitor';
import type { Client, Question, QuestionCategory, Report } from '../api/types';
import ClientForm from '../components/ClientForm';

const categoryLabel: Record<string, string> = {
  recommend: '推荐类',
  compare: '对比类',
  price: '价格类',
  review: '评价类',
  other: '其他',
};

const categoryOptions = Object.entries(categoryLabel).map(([k, v]) => ({
  value: k,
  label: v,
}));

export default function ClientDetail() {
  const { id } = useParams();
  const clientId = Number(id);
  const navigate = useNavigate();

  const [client, setClient] = useState<Client | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [editOpen, setEditOpen] = useState<boolean>(false);
  const [editing, setEditing] = useState<boolean>(false);

  // questions
  const [questions, setQuestions] = useState<Question[]>([]);
  const [questionsLoading, setQuestionsLoading] = useState<boolean>(false);
  const [selectedQuestionIds, setSelectedQuestionIds] = useState<number[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<QuestionCategory | undefined>(undefined);

  // 新增题目 modal
  const [createOpen, setCreateOpen] = useState<boolean>(false);
  const [createMode, setCreateMode] = useState<'single' | 'batch'>('single');
  const [draftText, setDraftText] = useState<string>('');
  const [draftBatch, setDraftBatch] = useState<string>('');
  const [draftCategory, setDraftCategory] = useState<QuestionCategory>('other');
  const [draftPriority, setDraftPriority] = useState<number>(5);
  const [submitting, setSubmitting] = useState<boolean>(false);

  // reports
  const [reports, setReports] = useState<Report[]>([]);
  const [reportsLoading, setReportsLoading] = useState<boolean>(false);
  const [reportRange, setReportRange] = useState<[string, string] | null>(null);

  const fetchClient = async () => {
    setLoading(true);
    try {
      const c = await getClient(clientId);
      setClient(c);
    } finally {
      setLoading(false);
    }
  };

  const fetchQuestions = async () => {
    setQuestionsLoading(true);
    try {
      const page = await listQuestions(clientId, {
        page: 1,
        page_size: 200,
        category: categoryFilter,
      });
      setQuestions(page?.items ?? []);
    } finally {
      setQuestionsLoading(false);
    }
  };

  const fetchReports = async () => {
    setReportsLoading(true);
    try {
      const page = await listReports(clientId, { page: 1, page_size: 50 });
      setReports(page?.items ?? []);
    } finally {
      setReportsLoading(false);
    }
  };

  useEffect(() => {
    if (!Number.isFinite(clientId)) return;
    fetchClient();
    fetchQuestions();
    fetchReports();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  useEffect(() => {
    if (Number.isFinite(clientId)) fetchQuestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryFilter]);

  const handleEdit = async (values: Parameters<typeof updateClient>[1]) => {
    setEditing(true);
    try {
      await updateClient(clientId, values);
      message.success('已更新');
      setEditOpen(false);
      fetchClient();
    } finally {
      setEditing(false);
    }
  };

  const handleDeleteQuestion = async (qid: number) => {
    await deleteQuestion(qid);
    message.success('已删除');
    fetchQuestions();
  };

  const handleBatchDelete = async () => {
    if (!selectedQuestionIds.length) return;
    await Promise.all(selectedQuestionIds.map((qid) => deleteQuestion(qid)));
    message.success(`已删除 ${selectedQuestionIds.length} 条`);
    setSelectedQuestionIds([]);
    fetchQuestions();
  };

  const resetDraft = () => {
    setDraftText('');
    setDraftBatch('');
    setDraftCategory('other');
    setDraftPriority(5);
    setCreateMode('single');
  };

  const handleSubmitCreate = async () => {
    setSubmitting(true);
    try {
      const items =
        createMode === 'single'
          ? draftText.trim()
            ? [
                {
                  text: draftText.trim(),
                  category: draftCategory,
                  priority: draftPriority,
                },
              ]
            : []
          : draftBatch
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
              .map((text) => ({
                text,
                category: draftCategory,
                priority: draftPriority,
              }));
      if (!items.length) {
        message.warning('请至少输入一条题目');
        return;
      }
      const r = await bulkCreateQuestions(clientId, items);
      message.success(`新建 ${r.created} 条,跳过 ${r.skipped} 条`);
      setCreateOpen(false);
      resetDraft();
      fetchQuestions();
    } finally {
      setSubmitting(false);
    }
  };

  const csvUploadProps: UploadProps = {
    accept: '.csv,.txt',
    showUploadList: false,
    beforeUpload: async (file) => {
      try {
        const r = await importQuestionsCSV(clientId, file);
        message.success(`CSV 导入: 新建 ${r.created} 条,跳过 ${r.skipped} 条`);
        fetchQuestions();
      } catch {
        // 错误已 toast
      }
      return false; // 不走 antd 默认上传
    },
  };

  const handleCreateReport = async () => {
    if (!reportRange) {
      message.warning('请选择日期范围');
      return;
    }
    try {
      await createReport(clientId, {
        period_start: reportRange[0],
        period_end: reportRange[1],
      });
      message.success('报告已生成');
      fetchReports();
    } catch {
      // toast'd
    }
  };

  if (!Number.isFinite(clientId)) {
    return <Empty description="无效的监测对象 ID" />;
  }

  return (
    <Spin spinning={loading}>
      <Card
        title={
          <Space>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {client?.name ?? '加载中...'}
            </Typography.Title>
            {client && <Tag color="blue">{client.plan}</Tag>}
            {client && <Tag>{client.status}</Tag>}
          </Space>
        }
        extra={
          <Space>
            <Button
              type="primary"
              icon={<RadarChartOutlined />}
              onClick={() => navigate(`/clients/${clientId}/monitor`)}
              disabled={!client}
            >
              进入监测中心
            </Button>
            <Button
              icon={<EditOutlined />}
              onClick={() => setEditOpen(true)}
              disabled={!client}
            >
              编辑
            </Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        {client ? (
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="行业">{client.industry}</Descriptions.Item>
            <Descriptions.Item label="地区">{client.region}</Descriptions.Item>
            <Descriptions.Item label="描述" span={2}>
              {client.business_info?.description}
            </Descriptions.Item>
            <Descriptions.Item label="官网">{client.business_info?.website ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="电话">{client.business_info?.phone ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="主营服务" span={2}>
              {(client.business_info?.services ?? []).join(', ') || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="竞争对手" span={2}>
              {(client.business_info?.competitors ?? []).join(', ') || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="品牌关键词 / 别名" span={2}>
              {(client.business_info?.keywords ?? []).join(', ') || '-'}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="暂无数据" />
        )}
      </Card>

      <Tabs
        defaultActiveKey="questions"
        items={[
          {
            key: 'questions',
            label: `探针题库 (${questions.length})`,
            children: (
              <>
                <Space style={{ marginBottom: 12 }} wrap>
                  <Select
                    allowClear
                    placeholder="按类别过滤"
                    style={{ width: 160 }}
                    value={categoryFilter}
                    onChange={(v) => setCategoryFilter(v)}
                    options={categoryOptions}
                  />
                  <Button icon={<ReloadOutlined />} onClick={fetchQuestions}>
                    刷新
                  </Button>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => {
                      resetDraft();
                      setCreateOpen(true);
                    }}
                  >
                    新增题目
                  </Button>
                  <Upload {...csvUploadProps}>
                    <Button icon={<UploadOutlined />}>
                      CSV 导入
                    </Button>
                  </Upload>
                  {selectedQuestionIds.length > 0 && (
                    <Popconfirm
                      title={`删除选中的 ${selectedQuestionIds.length} 条?`}
                      okText="删除"
                      okButtonProps={{ danger: true }}
                      onConfirm={handleBatchDelete}
                    >
                      <Button danger icon={<DeleteOutlined />}>
                        删除选中 ({selectedQuestionIds.length})
                      </Button>
                    </Popconfirm>
                  )}
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    CSV 列:text(必填), category, priority, language
                  </Typography.Text>
                </Space>
                <Table<Question>
                  rowKey="id"
                  loading={questionsLoading}
                  dataSource={questions}
                  pagination={{ pageSize: 20 }}
                  rowSelection={{
                    selectedRowKeys: selectedQuestionIds,
                    onChange: (keys) => setSelectedQuestionIds(keys as number[]),
                  }}
                  columns={[
                    { title: 'ID', dataIndex: 'id', width: 70 },
                    { title: '题目', dataIndex: 'text' },
                    {
                      title: '类别',
                      dataIndex: 'category',
                      width: 110,
                      render: (v: string) => <Tag>{categoryLabel[v] ?? v}</Tag>,
                    },
                    { title: '优先级', dataIndex: 'priority', width: 80 },
                    {
                      title: '操作',
                      width: 80,
                      render: (_: unknown, q: Question) => (
                        <Popconfirm
                          title="删除这条题目?"
                          okText="删除"
                          okButtonProps={{ danger: true }}
                          onConfirm={() => handleDeleteQuestion(q.id)}
                        >
                          <Button type="link" danger size="small">
                            删除
                          </Button>
                        </Popconfirm>
                      ),
                    },
                  ]}
                />
              </>
            ),
          },
          {
            key: 'monitor',
            label: '监测中心',
            children: (
              <Card>
                <Space direction="vertical">
                  <Typography.Text>查看 KPI 总览、平台拆分、实验运行 (Run) 列表和对比视图</Typography.Text>
                  <Button
                    type="primary"
                    icon={<RadarChartOutlined />}
                    onClick={() => navigate(`/clients/${clientId}/monitor`)}
                  >
                    打开监测中心
                  </Button>
                </Space>
              </Card>
            ),
          },
          {
            key: 'reports',
            label: `报告 (${reports.length})`,
            children: (
              <>
                <Space style={{ marginBottom: 12 }}>
                  <DatePicker.RangePicker
                    onChange={(range) => {
                      if (range && range[0] && range[1]) {
                        setReportRange([
                          range[0].format('YYYY-MM-DD'),
                          range[1].format('YYYY-MM-DD'),
                        ]);
                      } else {
                        setReportRange(null);
                      }
                    }}
                  />
                  <Button type="primary" onClick={handleCreateReport}>
                    生成报告
                  </Button>
                  <Button icon={<ReloadOutlined />} onClick={fetchReports}>
                    刷新
                  </Button>
                </Space>
                <List
                  loading={reportsLoading}
                  dataSource={reports}
                  locale={{ emptyText: <Empty description="暂无报告" /> }}
                  renderItem={(r) => (
                    <List.Item>
                      <List.Item.Meta
                        title={`#${r.id} · ${r.period_start} → ${r.period_end}`}
                        description={
                          <Typography.Paragraph
                            ellipsis={{ rows: 2 }}
                            style={{ margin: 0 }}
                          >
                            {r.summary}
                          </Typography.Paragraph>
                        }
                      />
                    </List.Item>
                  )}
                />
              </>
            ),
          },
        ]}
      />

      <ClientForm
        open={editOpen}
        initial={client}
        loading={editing}
        onCancel={() => setEditOpen(false)}
        onSubmit={handleEdit}
      />

      <Modal
        open={createOpen}
        title="新增探针题目"
        onCancel={() => {
          setCreateOpen(false);
          resetDraft();
        }}
        onOk={handleSubmitCreate}
        confirmLoading={submitting}
        okText="保存"
        width={620}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Typography.Text>录入方式:</Typography.Text>
            <Select
              value={createMode}
              onChange={(v) => setCreateMode(v)}
              style={{ width: 180 }}
              options={[
                { value: 'single', label: '单条录入' },
                { value: 'batch', label: '批量录入(每行一条)' },
              ]}
            />
          </Space>

          {createMode === 'single' ? (
            <Input.TextArea
              value={draftText}
              onChange={(e) => setDraftText(e.target.value)}
              rows={3}
              placeholder="输入一条探针问题,例如:中国最好的袜子代工厂是哪家?"
              maxLength={1000}
              showCount
            />
          ) : (
            <Input.TextArea
              value={draftBatch}
              onChange={(e) => setDraftBatch(e.target.value)}
              rows={8}
              placeholder="每行一条题目,空行会被忽略"
            />
          )}

          <Space>
            <Typography.Text>类别:</Typography.Text>
            <Select
              value={draftCategory}
              onChange={(v) => setDraftCategory(v)}
              style={{ width: 160 }}
              options={categoryOptions}
            />
            <Typography.Text>优先级:</Typography.Text>
            <InputNumber
              min={1}
              max={10}
              value={draftPriority}
              onChange={(v) => setDraftPriority((v as number) ?? 5)}
            />
          </Space>
        </Space>
      </Modal>
    </Spin>
  );
}
