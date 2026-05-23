# Website GEO 诊断 (M7)

> M7 是平台的「单站点 GEO 体检」模块。给一个网站 URL,自动跑结构化检查 + AI 友好度评分 + 生成改造建议。和监测中心是独立工作流。

## 入口

进客户详情页 → 「Website 诊断」Tab(或者直接调 `/api/diagnose`)。

## 它检查什么

诊断会自动抓取目标 URL 的 HTML / robots.txt / sitemap.xml / llms.txt,然后跑一组 GEO 维度的规则,产出:

| 维度 | 检查点 |
|---|---|
| **可抓取性** | robots.txt 是否阻止 AI 爬虫(GPTBot, ClaudeBot, Google-Extended, PerplexityBot 等) |
| **AI 友好度** | 是否有 llms.txt、是否有 schema.org 结构化数据、Hreflang、Open Graph |
| **内容质量** | 标题/描述/H1/正文长度、FAQ 块、表格密度 |
| **可信信号** | 联系方式、隐私政策、关于页、备案/认证页 |
| **技术 SEO 底层** | 站点速度、移动适配、HTTPS、规范链接 |

每个维度打分 + 给具体的 actionable 改造建议(写进 `actions_json`)。

## 输出

诊断完跑出一份 `DiagnosisResult`(在 `diagnosis_results` 表),含:

- `overall_score`(0-100 综合分)
- `scores_json`(分维度细分)
- `checks_json`(每条规则的命中/未命中 + 详情)
- `actions_json`(改造建议清单,按优先级排序)

前端展示:雷达图 + 维度卡片 + 建议清单(可勾选生成实施工单)。

## 何时用 M7

- **新客户接入第一周**:先跑一次 baseline 诊断,看现状起点在哪
- **跟监测中心配套**:监测看 AI 端,诊断看自家站。两个数据一起看才知道改了 llms.txt 到底有没有命中 AI 那边
- **客户审稿用**:把 diagnosis report 作为合同里的"诊断报告"deliverable,可控可量

## 历史诊断

`DiagnosisResult` 表按 `(base_url, created_at)` 去重存,可以跑多次看趋势。诊断历史在客户详情页底部有列表。

## 关联

- 配 [API 配置](/guides/settings) 里 LLM_PROVIDER 后,诊断里的「内容质量」维度会用 LLM 评估文本可读性
- 改造建议可以转成 Action items,挂到客户的 Notes 里(目前手动,后续考虑加 Tracker)
