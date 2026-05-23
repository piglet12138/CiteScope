/**
 * 任务队列 - 自动 3s 刷新 + 状态过滤 + 行展开查看 result/error.
 */
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { listTasks } from '../api/tasks';
import type { TaskInfo } from '../api/types';

type TaskStatus = TaskInfo['status'];

const statusColor: Record<TaskStatus, string> = {
  queued: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
};

const REFRESH_MS = 3000;

export default function TaskQueue() {
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | undefined>(undefined);
  const statusFilterRef = useRef<TaskStatus | undefined>(undefined);
  statusFilterRef.current = statusFilter;

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const page = await listTasks({
        page: 1,
        page_size: 100,
        status: statusFilterRef.current,
      });
      setTasks(page?.items ?? []);
    } catch (err) {
      // toast'd
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    const id = window.setInterval(fetchTasks, REFRESH_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // refetch on filter change
  useEffect(() => {
    fetchTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  return (
    <Card
      title="任务队列"
      extra={
        <Space>
          <Select
            allowClear
            placeholder="按状态过滤"
            style={{ width: 160 }}
            value={statusFilter}
            onChange={(v) => setStatusFilter(v)}
            options={[
              { value: 'queued', label: '排队' },
              { value: 'running', label: '运行中' },
              { value: 'success', label: '成功' },
              { value: 'failed', label: '失败' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchTasks}>
            手动刷新
          </Button>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">每 3 秒自动刷新</Typography.Paragraph>
      <Table<TaskInfo>
        rowKey="task_id"
        loading={loading}
        dataSource={tasks}
        pagination={{ pageSize: 15 }}
        expandable={{
          expandedRowRender: (record) => (
            <div>
              {record.error && (
                <Typography.Paragraph type="danger">
                  <strong>错误:</strong> {record.error}
                </Typography.Paragraph>
              )}
              <Typography.Paragraph>
                <strong>结果:</strong>
              </Typography.Paragraph>
              <pre
                style={{
                  background: '#f5f5f5',
                  padding: 12,
                  borderRadius: 4,
                  margin: 0,
                  fontSize: 12,
                  maxHeight: 240,
                  overflow: 'auto',
                }}
              >
                {JSON.stringify(record.result ?? {}, null, 2)}
              </pre>
            </div>
          ),
        }}
        columns={[
          {
            title: '任务 ID',
            dataIndex: 'task_id',
            width: 140,
            render: (v: string) => (
              <Typography.Text code copyable={{ text: v }}>
                {v.slice(0, 8)}
              </Typography.Text>
            ),
          },
          { title: '类型', dataIndex: 'type', width: 160 },
          {
            title: '状态',
            dataIndex: 'status',
            width: 110,
            render: (v: TaskStatus) => <Tag color={statusColor[v]}>{v}</Tag>,
          },
          {
            title: '进度',
            dataIndex: 'progress',
            width: 200,
            render: (v: number, r: TaskInfo) => (
              <Progress
                percent={v ?? 0}
                size="small"
                status={
                  r.status === 'failed'
                    ? 'exception'
                    : r.status === 'success'
                    ? 'success'
                    : 'active'
                }
              />
            ),
          },
          { title: '客户ID', dataIndex: 'client_id', width: 90 },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 160,
            render: (v: string) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-'),
          },
          {
            title: '更新时间',
            dataIndex: 'updated_at',
            width: 160,
            render: (v: string) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-'),
          },
        ]}
      />
    </Card>
  );
}
