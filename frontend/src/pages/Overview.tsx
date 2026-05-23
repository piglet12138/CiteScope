/**
 * 总览 - 客户卡片网格 + 当前 mention_rate / 趋势.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Dropdown,
  Empty,
  Modal,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  EditOutlined,
  DeleteOutlined,
  MoreOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  listClients,
  createClient,
  updateClient,
  deleteClient,
  type ClientCreateBody,
} from '../api/clients';
import { getMetrics } from '../api/monitor';
import type { Client, Metrics } from '../api/types';
import ClientForm from '../components/ClientForm';
import TrendArrow from '../components/TrendArrow';

interface MetricBundle {
  metrics: Metrics | null;
  delta: number;
}

const planColor: Record<Client['plan'], string> = {
  basic: 'default',
  pro: 'blue',
  enterprise: 'purple',
};

const statusColor: Record<Client['status'], string> = {
  active: 'green',
  paused: 'orange',
  archived: 'default',
};

export default function Overview() {
  const navigate = useNavigate();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [metricsMap, setMetricsMap] = useState<Record<number, MetricBundle>>({});
  const [formOpen, setFormOpen] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [editing, setEditing] = useState<Client | null>(null);

  const fetchClients = async () => {
    setLoading(true);
    try {
      const page = await listClients({ page: 1, page_size: 20 });
      const items = page?.items ?? [];
      setClients(items);

      // fire metric requests in parallel — tolerate failures
      const results = await Promise.allSettled(items.map((c) => getMetrics(c.id, 'week')));
      const next: Record<number, MetricBundle> = {};
      results.forEach((r, idx) => {
        const cid = items[idx].id;
        if (r.status === 'fulfilled' && r.value) {
          const m = r.value;
          const trend = m.trend ?? [];
          const delta =
            trend.length >= 2
              ? trend[trend.length - 1].mention_rate - trend[0].mention_rate
              : 0;
          next[cid] = { metrics: m, delta };
        } else {
          next[cid] = { metrics: null, delta: 0 };
        }
      });
      setMetricsMap(next);
    } catch (err) {
      // axios interceptor already shows message
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClients();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (c: Client) => {
    setEditing(c);
    setFormOpen(true);
  };

  const handleSubmit = async (values: ClientCreateBody) => {
    setSubmitting(true);
    try {
      if (editing) {
        await updateClient(editing.id, values);
        message.success('监测对象已更新');
      } else {
        await createClient(values);
        message.success('监测对象已创建');
      }
      setFormOpen(false);
      setEditing(null);
      fetchClients();
    } catch (err) {
      // already toast'd
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = (c: Client) => {
    Modal.confirm({
      title: `删除监测对象 “${c.name}”?`,
      content: '该操作将同时移除该品牌下的探针题库、监测结果与实验运行记录,且不可恢复。',
      okText: '确认删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteClient(c.id);
          message.success('监测对象已删除');
          fetchClients();
        } catch (err) {
          // already toast'd
        }
      },
    });
  };

  const empty = useMemo(() => clients.length === 0 && !loading, [clients, loading]);

  return (
    <div>
      <Row align="middle" justify="space-between" style={{ marginBottom: 16 }}>
        <Col>
          <Typography.Title level={3} style={{ margin: 0 }}>
            监测对象总览
          </Typography.Title>
          <Typography.Text type="secondary">所有品牌在生成式 AI 引擎中的最新提及率与趋势</Typography.Text>
        </Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchClients}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建监测对象
            </Button>
          </Space>
        </Col>
      </Row>

      <Spin spinning={loading}>
        {empty ? (
          <Card>
            <Empty description="暂无监测对象,点击右上角“新建监测对象”开始" />
          </Card>
        ) : (
          <Row gutter={[16, 16]}>
            {clients.map((c) => {
              const bundle = metricsMap[c.id];
              const rate = bundle?.metrics?.mention_rate ?? 0;
              return (
                <Col xs={24} sm={12} md={8} lg={6} key={c.id}>
                  <Card
                    hoverable
                    onClick={() => navigate(`/clients/${c.id}`)}
                    title={c.name}
                    extra={
                      <Space size={4} onClick={(e) => e.stopPropagation()}>
                        <Tag color={planColor[c.plan]} style={{ marginRight: 0 }}>
                          {c.plan}
                        </Tag>
                        <Dropdown
                          trigger={['click']}
                          menu={{
                            items: [
                              {
                                key: 'edit',
                                icon: <EditOutlined />,
                                label: '编辑',
                                onClick: ({ domEvent }) => {
                                  domEvent.stopPropagation();
                                  openEdit(c);
                                },
                              },
                              {
                                key: 'delete',
                                icon: <DeleteOutlined />,
                                label: '删除',
                                danger: true,
                                onClick: ({ domEvent }) => {
                                  domEvent.stopPropagation();
                                  handleDelete(c);
                                },
                              },
                            ],
                          }}
                        >
                          <Button
                            type="text"
                            size="small"
                            icon={<MoreOutlined />}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Dropdown>
                      </Space>
                    }
                  >
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      <Space size="small" wrap>
                        <Tag>{c.industry}</Tag>
                        <Tag>{c.region}</Tag>
                        <Tag color={statusColor[c.status]}>{c.status}</Tag>
                      </Space>
                      <Statistic
                        title="提及率 (近 7 天)"
                        value={(rate * 100).toFixed(1)}
                        suffix="%"
                        valueStyle={{ fontSize: 22 }}
                      />
                      <Space>
                        <Typography.Text type="secondary">趋势</Typography.Text>
                        <TrendArrow value={bundle?.delta ?? 0} />
                      </Space>
                    </Space>
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}
      </Spin>

      <ClientForm
        open={formOpen}
        initial={editing}
        loading={submitting}
        onCancel={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
