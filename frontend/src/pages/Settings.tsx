/**
 * 设置页 - 完整运行时配置中心。
 *
 * 用户在此页填写所有 cookie / API key, 提交后写入 backend/data/runtime_config.json,
 * 后端立刻 reload_settings(), 后续任务即用新值。
 *
 * 敏感字段:
 * - GET 时显示 sk-1***xxxx 掩码 + "已配置" 标签
 * - PUT 时空字符串 = 不修改 (避免误清空)
 * - 输入框 placeholder 显示掩码, 实际 value 留空
 */
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleTwoTone,
  CloseCircleTwoTone,
  DeleteOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SaveOutlined,
  ScissorOutlined,
} from '@ant-design/icons';
import {
  FieldDef,
  RuntimeConfig,
  SettingsSchema,
  cleanCookieRaw,
  cleanTokenRaw,
  deleteRuntimeKey,
  getRuntimeConfig,
  getSettingsSchema,
  isSecretValue,
  putRuntimeConfig,
  testLLM,
  testMonitor,
} from '../api/settings';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

const PLATFORM_LABELS: Record<string, string> = {
  chatgpt: 'ChatGPT (OpenAI Responses + web search)',
  perplexity: 'Perplexity Sonar',
  google_ai: 'Google AI (Gemini grounding)',
  doubao: '豆包 (火山方舟 Ark)',
  kimi: 'Kimi (Moonshot)',
  deepseek: 'DeepSeek (网页逆向)',
};

const PLATFORM_DESC: Record<string, string> = {
  chatgpt: '官方 OpenAI key 调 Responses API + web_search_preview 工具,citation 在 annotations 里',
  perplexity: 'Sonar API,citations 在响应顶层数组(可走 OpenRouter 代理)',
  google_ai: 'Gemini API + google_search 工具,grounding 链接会重定向到真实域名(后台 5min 解析一次)',
  doubao: '火山方舟 Ark Responses API + web_search 内置工具,官方 API,Bearer Key',
  kimi: 'Moonshot 官方付费 API,中文/国内场景备选',
  deepseek: 'DeepSeek 官方暂无 search API,只能走 chat.deepseek.com 网页 refresh_token 逆向 (best-effort)',
};

interface FieldRowProps {
  field: FieldDef;
  config: RuntimeConfig;
  onChange: (key: string, value: unknown) => void;
  onClear: (key: string) => void;
  draft: Record<string, unknown>;
}

function FieldRow({ field, config, draft, onChange, onClear }: FieldRowProps) {
  const entry = config[field.key];
  const isSecret = field.type === 'password' || field.type === 'textarea';
  const draftValue = draft[field.key];
  const fromRuntime = !!(entry && entry.from_runtime);

  // 显示状态
  let statusTag: React.ReactNode = null;
  if (entry && isSecretValue(entry)) {
    statusTag = entry.configured ? (
      <Tag icon={<CheckCircleTwoTone twoToneColor="#52c41a" />} color="green">
        已配置
      </Tag>
    ) : (
      <Tag icon={<CloseCircleTwoTone twoToneColor="#f5222d" />} color="default">
        未配置
      </Tag>
    );
  } else if (entry && entry.from_runtime) {
    statusTag = <Tag color="blue">运行时</Tag>;
  } else if (entry && !entry.from_runtime) {
    statusTag = <Tag color="default">默认/.env</Tag>;
  }

  // 判断字段是走 token 清洗还是 cookie 清洗
  const isTokenField =
    field.key.endsWith('_REFRESH_TOKEN') || field.key.endsWith('_API_KEY');

  // curl 自动清洗 (针对 textarea/password 类的 cookie / token 字段)
  const handleCurlClean = async () => {
    const v = (draftValue as string) ?? '';
    if (!v) {
      message.info('请先粘贴 curl 命令 / cookie / token 字符串');
      return;
    }
    try {
      if (isTokenField) {
        const r = await cleanTokenRaw(v);
        if (!r.token) {
          message.warning('未能识别出 token, 请检查粘贴内容是否含有 Bearer / localStorage JSON');
          return;
        }
        onChange(field.key, r.token);
        message.success(`已提取 token (${r.token.length} 字符)`);
      } else {
        const r = await cleanCookieRaw(v);
        onChange(field.key, r.cookie);
        message.success(`已提取 cookie (${r.cookie.length} 字符)`);
      }
    } catch {
      // toast'd
    }
  };

  // 构造 placeholder
  let placeholder = field.placeholder || '';
  if (entry && isSecretValue(entry) && entry.configured && entry.masked) {
    placeholder = `当前: ${entry.masked} (留空则不修改)`;
  } else if (!isSecret && entry && !isSecretValue(entry) && entry.value != null && entry.value !== '') {
    placeholder = `当前: ${String(entry.value)}`;
  }

  // 渲染输入控件
  let control: React.ReactNode = null;
  switch (field.type) {
    case 'boolean': {
      const currentValue =
        draftValue !== undefined
          ? Boolean(draftValue)
          : entry && !isSecretValue(entry)
            ? Boolean(entry.value)
            : false;
      control = (
        <Switch
          checked={currentValue}
          onChange={(v) => onChange(field.key, v)}
          checkedChildren="开"
          unCheckedChildren="关"
        />
      );
      break;
    }
    case 'select': {
      const currentValue =
        draftValue !== undefined
          ? (draftValue as string)
          : entry && !isSecretValue(entry)
            ? (entry.value as string) || undefined
            : undefined;
      control = (
        <Select
          style={{ minWidth: 220 }}
          value={currentValue}
          placeholder={placeholder || '请选择'}
          onChange={(v) => onChange(field.key, v)}
          options={(field.options || []).map((o) => ({ label: o, value: o }))}
          allowClear
        />
      );
      break;
    }
    case 'textarea':
      control = (
        <TextArea
          rows={3}
          value={(draftValue as string) ?? ''}
          placeholder={placeholder || '粘贴 cookie 字符串, 如: name1=v1; name2=v2; ...'}
          onChange={(e) => onChange(field.key, e.target.value)}
          autoSize={{ minRows: 2, maxRows: 6 }}
          allowClear
        />
      );
      break;
    case 'password':
      control = (
        <Input.Password
          value={(draftValue as string) ?? ''}
          placeholder={placeholder || '留空则不修改'}
          onChange={(e) => onChange(field.key, e.target.value)}
          autoComplete="new-password"
          allowClear
        />
      );
      break;
    default:
      control = (
        <Input
          value={(draftValue as string) ?? ''}
          placeholder={placeholder}
          onChange={(e) => onChange(field.key, e.target.value)}
          allowClear
        />
      );
  }

  // 操作按钮组: 清除 (运行时已存) + curl 清洗 (textarea/password)
  const actions = (
    <Space size={4} style={{ marginTop: 4 }}>
      {(field.type === 'textarea' || field.type === 'password') && (
        <Button
          size="small"
          icon={<ScissorOutlined />}
          onClick={handleCurlClean}
          title={
            isTokenField
              ? '粘贴 curl / Authorization: Bearer ... / localStorage JSON 后点此, 自动提取 token'
              : '粘贴 curl 后点此, 自动提取 cookie'
          }
        >
          {isTokenField ? '从粘贴提取 token' : '粘贴 curl'}
        </Button>
      )}
      {fromRuntime && (
        <Popconfirm
          title="清除此字段?"
          description="将从 runtime_config.json 中删除, 恢复 .env / 默认值"
          okText="清除"
          okButtonProps={{ danger: true }}
          onConfirm={() => onClear(field.key)}
        >
          <Button size="small" danger icon={<DeleteOutlined />}>
            清除
          </Button>
        </Popconfirm>
      )}
    </Space>
  );

  return (
    <Form.Item
      label={
        <Space size="small">
          <span>{field.label}</span>
          {statusTag}
        </Space>
      }
      help={
        field.help ? (
          <span style={{ whiteSpace: 'pre-wrap' }}>{field.help}</span>
        ) : undefined
      }
      labelCol={{ span: 8 }}
      wrapperCol={{ span: 16 }}
      style={{ marginBottom: 16 }}
    >
      {control}
      {actions}
    </Form.Item>
  );
}

export default function Settings() {
  const [schema, setSchema] = useState<SettingsSchema | null>(null);
  const [config, setConfig] = useState<RuntimeConfig>({});
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    Promise.all([getSettingsSchema(), getRuntimeConfig()])
      .then(([sch, cfg]) => {
        setSchema(sch);
        setConfig(cfg);
        setDraft({});
      })
      .catch(() => message.error('加载配置失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleChange = (key: string, value: unknown) => {
    setDraft((d) => ({ ...d, [key]: value }));
  };

  const handleClear = async (key: string) => {
    try {
      await deleteRuntimeKey(key);
      message.success(`已清除 ${key}`);
      // 同时把 draft 中的草稿值也清掉
      setDraft((d) => {
        const next = { ...d };
        delete next[key];
        return next;
      });
      refresh();
    } catch {
      // toast'd
    }
  };

  const dirtyCount = Object.keys(draft).length;

  const handleSave = async () => {
    if (dirtyCount === 0) {
      message.info('没有要保存的修改');
      return;
    }
    setSaving(true);
    try {
      const res = await putRuntimeConfig(draft);
      message.success(`已保存 ${res.count} 项配置`);
      refresh();
    } catch (e) {
      // client.ts 拦截器已经 message.error
    } finally {
      setSaving(false);
    }
  };

  const handleTestLLM = async () => {
    setTesting('llm');
    try {
      const r = await testLLM();
      if (r.ok) {
        message.success(`LLM 连通: ${r.preview?.slice(0, 60) ?? 'OK'}`);
      } else {
        message.error(`LLM 失败: ${r.error}`);
      }
    } finally {
      setTesting(null);
    }
  };

  const handleTestPlatform = async (kind: 'monitor', platform: string) => {
    setTesting(`${kind}:${platform}`);
    try {
      const r = await testMonitor(platform);
      if (r.ok) {
        message.success(`${PLATFORM_LABELS[platform] ?? platform}: ${r.message ?? 'OK'}`);
      } else {
        message.error(`${PLATFORM_LABELS[platform] ?? platform}: ${r.error}`);
      }
    } finally {
      setTesting(null);
    }
  };

  // 按 category 分组字段
  const fieldsByCategory = useMemo(() => {
    const out: Record<string, FieldDef[]> = {};
    schema?.fields.forEach((f) => {
      if (!out[f.category]) out[f.category] = [];
      out[f.category].push(f);
    });
    return out;
  }, [schema]);

  const monitorsByPlatform = useMemo(() => {
    const out: Record<string, FieldDef[]> = {};
    (fieldsByCategory.monitor || []).forEach((f) => {
      const p = f.platform || 'misc';
      if (!out[p]) out[p] = [];
      out[p].push(f);
    });
    return out;
  }, [fieldsByCategory]);

  if (!schema) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin spinning={loading} tip="加载配置..." />
      </div>
    );
  }

  return (
    <Spin spinning={loading || saving}>
      {/* ---------- 简短教程 / 当前状态 ---------- */}
      <Card size="small" style={{ marginBottom: 16 }} bodyStyle={{ padding: 16 }}>
        <Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>
          📘 这里干什么用
        </Title>
        <Paragraph style={{ marginBottom: 8 }}>
          CiteScope 跑 GEO 监测 + Citation 分析,需要拿到 AI 搜索平台的 key 才能调真实接口。
          这页就是统一管 key 的地方,所有改动写入{' '}
          <Text code>backend/data/runtime_config.json</Text>,
          覆盖 <Text code>.env</Text>,保存后立即生效(无需重启)。
        </Paragraph>
        <Paragraph style={{ marginBottom: 8 }}>
          <Text strong>跑一次完整 Citation 分析,至少要 3 把 key:</Text>
        </Paragraph>
        <ul style={{ marginTop: 0, paddingLeft: 20, marginBottom: 8 }}>
          <li>
            <Text strong>OpenAI Official API Key</Text> →{' '}
            <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">
              platform.openai.com/api-keys
            </a>
            (ChatGPT web 搜索)
          </li>
          <li>
            <Text strong>Perplexity Sonar API Key</Text> →{' '}
            <a href="https://www.perplexity.ai/settings/api" target="_blank" rel="noreferrer">
              perplexity.ai/settings/api
            </a>
            (或走 OpenRouter,见字段说明)
          </li>
          <li>
            <Text strong>Google AI (Gemini) API Key</Text> →{' '}
            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">
              aistudio.google.com/apikey
            </a>
            (Gemini grounding 搜索)
          </li>
        </ul>
        <Paragraph style={{ marginBottom: 0 }} type="secondary">
          可选:Kimi(Moonshot API key)是国产备选,不填也能跑前 3 家。
          填完之后到 <Link to="/clients">品牌列表</Link> 选一个客户 → 监测中心 → 新建实验运行。
          每个平台都有「测试」按钮,可单独验证连通性。
          完整使用流程见{' '}
          <Link to="/guides">教程总览</Link>{' '}或{' '}
          <Link to="/guides/settings">API 配置详解</Link>。
        </Paragraph>
      </Card>

      <Card
        title={
          <Space>
            <Title level={4} style={{ margin: 0 }}>
              系统配置中心
            </Title>
            {dirtyCount > 0 && <Tag color="orange">{dirtyCount} 项未保存</Tag>}
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={refresh}>
              刷新
            </Button>
            <Popconfirm
              title="保存配置"
              description={`确认写入 ${dirtyCount} 项变更到 runtime_config.json?`}
              onConfirm={handleSave}
              disabled={dirtyCount === 0}
            >
              <Button
                type="primary"
                icon={<SaveOutlined />}
                disabled={dirtyCount === 0}
                loading={saving}
              >
                保存
              </Button>
            </Popconfirm>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Alert
          type="info"
          showIcon
          message="配置生效说明"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              <li>密码字段:留空 = 不修改(避免误清空);要清除用每行的「清除」按钮(仅 from_runtime 字段显示)。</li>
              <li>普通字段(Model / URL):留空 = 恢复 .env 默认值。</li>
              <li>保存后立即生效,无需重启 backend。</li>
              <li>所有写入落到 backend/data/runtime_config.json,不进 git。</li>
            </ul>
          }
          style={{ marginBottom: 16 }}
        />

        <Tabs
          defaultActiveKey="monitor"
          items={[
            {
              key: 'monitor',
              label: 'AI 搜索 / 监测平台',
              children: (
                <div>
                  <Alert
                    type="info"
                    showIcon
                    message="Citation 分析三家(ChatGPT / Perplexity / Google AI)是跑 Run 的最低门槛。豆包走火山方舟 Ark 官方 API。Kimi 是 Moonshot 官方付费 API。DeepSeek 官方目前没有 search API,只能走网页逆向(标 best-effort)。"
                    style={{ marginBottom: 16 }}
                  />
                  {Object.entries(monitorsByPlatform).map(([platform, fields]) => (
                    <Card
                      key={platform}
                      type="inner"
                      size="small"
                      title={
                        <Space direction="vertical" size={2} style={{ width: '100%' }}>
                          <Text strong>{PLATFORM_LABELS[platform] ?? platform}</Text>
                          {PLATFORM_DESC[platform] && (
                            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                              {PLATFORM_DESC[platform]}
                            </Text>
                          )}
                        </Space>
                      }
                      style={{ marginBottom: 16 }}
                      extra={
                        <Button
                          size="small"
                          icon={<ExperimentOutlined />}
                          loading={testing === `monitor:${platform}`}
                          onClick={() => handleTestPlatform('monitor', platform)}
                        >
                          测试
                        </Button>
                      }
                    >
                      <Form layout="horizontal">
                        {fields.map((f) => (
                          <FieldRow key={f.key} field={f} config={config} draft={draft} onChange={handleChange} onClear={handleClear} />
                        ))}
                      </Form>
                    </Card>
                  ))}
                </div>
              ),
            },
            {
              key: 'general',
              label: '其他',
              children: (
                <Form layout="horizontal">
                  {(fieldsByCategory.general || []).map((f) => (
                    <FieldRow key={f.key} field={f} config={config} draft={draft} onChange={handleChange} onClear={handleClear} />
                  ))}
                </Form>
              ),
            },
          ]}
        />
      </Card>
    </Spin>
  );
}
