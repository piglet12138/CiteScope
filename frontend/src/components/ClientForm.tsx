/**
 * 客户表单 (新建/编辑). 由父组件控制 visible 与 submit 行为。
 */
import { Alert, Form, Input, Modal, Select, Switch, Typography } from 'antd';
import { useEffect, useMemo } from 'react';
import type { Client, BusinessInfo } from '../api/types';
import type { ClientCreateBody } from '../api/clients';

interface Props {
  open: boolean;
  initial?: Client | null;
  loading?: boolean;
  onCancel: () => void;
  onSubmit: (values: ClientCreateBody) => void;
}

interface FormValues {
  name: string;
  industry: string;
  region: string;
  plan: Client['plan'];
  status: Client['status'];
  description: string;
  address?: string;
  phone?: string;
  website?: string;
  services?: string;
  competitors?: string;
  keywords?: string;
  auto_expand_keywords: boolean;
}

function splitList(s?: string): string[] | undefined {
  if (!s) return undefined;
  const arr = s
    .split(/[,\n,]+/)
    .map((x) => x.trim())
    .filter(Boolean);
  return arr.length ? arr : undefined;
}

function joinList(arr?: string[]): string | undefined {
  return arr && arr.length ? arr.join(', ') : undefined;
}

function buildInitialValues(initial?: Client | null): FormValues {
  if (!initial) {
    return {
      name: '',
      industry: '',
      region: '',
      plan: 'basic',
      status: 'active',
      description: '',
      auto_expand_keywords: true, // 新建默认开
    };
  }
  return {
    name: initial.name,
    industry: initial.industry,
    region: initial.region,
    plan: initial.plan,
    status: initial.status,
    description: initial.business_info?.description ?? '',
    address: initial.business_info?.address,
    phone: initial.business_info?.phone,
    website: initial.business_info?.website,
    services: joinList(initial.business_info?.services),
    competitors: joinList(initial.business_info?.competitors),
    keywords: joinList(initial.business_info?.keywords),
    auto_expand_keywords: false, // 编辑默认关, 避免误扩展
  };
}

export default function ClientForm({ open, initial, loading, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<FormValues>();
  // 用 initial.id (或 'new') 作为 key, 切换客户时强制 remount
  const formKey = useMemo(() => `client-form-${initial?.id ?? 'new'}`, [initial?.id]);
  const initialValues = useMemo(() => buildInitialValues(initial), [initial]);

  // 关闭时清空,避免下次打开残留旧值 (forceRender 模式下 Form 实例不会卸载)
  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue(initialValues);
    }
  }, [open, initialValues, form]);

  const handleOk = async () => {
    const values = await form.validateFields();
    const business_info: BusinessInfo = {
      description: values.description,
      address: values.address || undefined,
      phone: values.phone || undefined,
      website: values.website || undefined,
      services: splitList(values.services),
      competitors: splitList(values.competitors),
      keywords: splitList(values.keywords),
    };
    onSubmit({
      name: values.name,
      industry: values.industry,
      region: values.region,
      plan: values.plan,
      status: values.status,
      business_info,
      auto_expand_keywords: values.auto_expand_keywords,
    });
  };

  return (
    <Modal
      open={open}
      title={initial ? '编辑监测对象' : '新建监测对象'}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={loading}
      forceRender
      width={640}
    >
      <Form
        key={formKey}
        form={form}
        layout="vertical"
        initialValues={initialValues}
        preserve={false}
      >
        <Form.Item name="name" label="品牌名" rules={[{ required: true, message: '请输入品牌名' }]}>
          <Input placeholder="例如:Acme" />
        </Form.Item>
        <Form.Item
          name="industry"
          label="行业"
          rules={[{ required: true, message: '请输入行业' }]}
        >
          <Input placeholder="例如:餐饮 / 教育 / 律所" />
        </Form.Item>
        <Form.Item name="region" label="地区" rules={[{ required: true, message: '请输入地区' }]}>
          <Input placeholder="例如:北京 / 上海" />
        </Form.Item>
        <Form.Item name="plan" label="套餐">
          <Select
            options={[
              { value: 'basic', label: '基础版' },
              { value: 'pro', label: '专业版' },
              { value: 'enterprise', label: '企业版' },
            ]}
          />
        </Form.Item>
        <Form.Item name="status" label="状态">
          <Select
            options={[
              { value: 'active', label: '活跃' },
              { value: 'paused', label: '暂停' },
              { value: 'archived', label: '归档' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="description"
          label="品牌描述"
          rules={[{ required: true, message: '请填写描述' }]}
        >
          <Input.TextArea rows={3} placeholder="一段话介绍品牌 / 产品 / 业务" />
        </Form.Item>
        <Form.Item name="address" label="地址">
          <Input />
        </Form.Item>
        <Form.Item name="phone" label="电话">
          <Input />
        </Form.Item>
        <Form.Item name="website" label="官网">
          <Input placeholder="https://..." />
        </Form.Item>
        <Form.Item name="services" label="主营服务" extra="逗号分隔">
          <Input placeholder="例如:重庆火锅, 海鲜自助" />
        </Form.Item>
        <Form.Item name="competitors" label="竞争对手" extra="逗号分隔">
          <Input placeholder="例如:海底捞, 巴奴" />
        </Form.Item>
        <Form.Item name="keywords" label="关键词" extra="逗号分隔, 可手动增删">
          <Input placeholder="例如:北京火锅推荐, 海鲜自助" />
        </Form.Item>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="品牌识别词库自动扩展"
          description={
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              开启后会调用 LLM, 基于品牌名+行业+描述自动生成别名/子品牌/英文名/常见误写,
              合并到上面的关键词里, 用于监测中心做来源和正文匹配。
              {initial
                ? ' 编辑时默认关闭, 避免把你手动删掉的词加回来。'
                : ' 新建时默认开启。'}
            </Typography.Text>
          }
        />
        <Form.Item
          name="auto_expand_keywords"
          label="自动扩展关键词 (LLM)"
          valuePropName="checked"
          extra="关闭时只保存上面手填的关键词 (品牌主名会自动保底)"
        >
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}
