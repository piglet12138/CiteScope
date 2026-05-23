/**
 * Guide manifest:slug → { 标题、摘要、图标分类、markdown 内容 }。
 *
 * 因为 Vite ?raw import 是静态的,必须显式声明每条 import。
 * 添加新 guide 流程:
 *   1) 新建 guides/<slug>.md
 *   2) 在下面 import 一行 + 加进 GUIDES dict
 *   3) 完事 — 路由 /guides/<slug> 自动生效
 */
import gettingStartedMd from './getting-started.md?raw';
import settingsMd from './settings.md?raw';
import clientsQuestionsMd from './clients-questions.md?raw';
import runsMd from './runs.md?raw';
import analyticsMd from './analytics.md?raw';
import citationSourcesMd from './citation-sources.md?raw';
import diagnosisMd from './diagnosis.md?raw';
import operationsMd from './operations.md?raw';

export interface GuideMeta {
  slug: string;
  title: string;
  summary: string;
  order: number;
  category: 'start' | 'config' | 'workflow' | 'analysis' | 'ops';
  content: string;
}

export const GUIDES: Record<string, GuideMeta> = {
  'getting-started': {
    slug: 'getting-started',
    title: '5 步上手',
    summary: '第一次用平台?跟这篇 10 分钟跑完第一个 Run,看到 AI 引用哪些站。',
    order: 1,
    category: 'start',
    content: gettingStartedMd,
  },
  settings: {
    slug: 'settings',
    title: 'API 配置详解',
    summary: '各家 AI 搜索 key 申请 + 填写,Citation 分析三家必备:ChatGPT / Perplexity / Gemini。',
    order: 2,
    category: 'config',
    content: settingsMd,
  },
  'clients-questions': {
    slug: 'clients-questions',
    title: '监测对象 + 探针问题',
    summary: '客户字段 / 品牌关键词配置 / 题库录入 / CSV 导入 / 三类好问题。',
    order: 3,
    category: 'workflow',
    content: clientsQuestionsMd,
  },
  runs: {
    slug: 'runs',
    title: '实验运行 (Run)',
    summary: '触发 Run / 防封号 / 配额管理 / 多 Run 对比 — 平台的核心工作单位。',
    order: 4,
    category: 'workflow',
    content: runsMd,
  },
  analytics: {
    slug: 'analytics',
    title: '数据分析',
    summary: '监测中心 4 个 Tab(概览 / 实验运行 / 对比 / 引用来源)分别回答什么问题。',
    order: 5,
    category: 'analysis',
    content: analyticsMd,
  },
  'citation-sources': {
    slug: 'citation-sources',
    title: '引用来源 (Citation Sources)',
    summary: 'AI 最爱引用哪些站 + 竞品 GEO 资产清单 — 反推 GEO 投放方向。',
    order: 6,
    category: 'analysis',
    content: citationSourcesMd,
  },
  diagnosis: {
    slug: 'diagnosis',
    title: 'Website GEO 诊断',
    summary: 'M7 模块:单站点 GEO 体检 — 抓 robots/sitemap/llms.txt + 评分 + 改造建议。',
    order: 7,
    category: 'analysis',
    content: diagnosisMd,
  },
  operations: {
    slug: 'operations',
    title: '运维 / 部署',
    summary: '服务管理 / 日志 / 备份 / 数据回填 / 常见故障 — 给操作员看的速查表。',
    order: 8,
    category: 'ops',
    content: operationsMd,
  },
};

export const GUIDE_LIST: GuideMeta[] = Object.values(GUIDES).sort((a, b) => a.order - b.order);

export const CATEGORY_LABELS: Record<GuideMeta['category'], string> = {
  start: '🚀 入门',
  config: '⚙️ 配置',
  workflow: '📋 工作流程',
  analysis: '📊 数据分析',
  ops: '🛠️ 运维',
};
