# 5 步上手 — CiteScope GEO 监测平台

> 适合第一次使用平台的人。读完之后能跑完第一个 Run,看到 AI 在某品类里引用了哪些站。预计 10 分钟。

## 这个平台干什么

CiteScope 是 **GEO (Generative Engine Optimization) 效果监测实验平台**。简单说:

- 你给它一组「探针问题」(prompts) + 想监测的品牌
- 它去 ChatGPT / Perplexity / Gemini 等 AI 引擎跑这些问题
- 自动判断 AI 有没有提到你的品牌、引用了哪些第三方网站
- 跨多次 Run 横向对比,看 GEO 干预动作有没有效果

跟普通 SEO 工具的差异:**它衡量的不是 Google 搜索排名,是 AI 回答里的可见度。**

## 第 1 步:配置 API key

打开 [系统配置](/settings) → 默认进入「AI 搜索 / 监测平台」Tab → 至少填 3 把 key:

| Key | 干什么 | 申请 |
|---|---|---|
| OPENAI_OFFICIAL_API_KEY | ChatGPT 监测(Responses API + web search) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| PERPLEXITY_API_KEY | Perplexity Sonar 监测(可走 OpenRouter) | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |
| GOOGLE_AI_API_KEY | Google AI (Gemini) 监测 | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

填完保存,**立即生效,无需重启**。每个平台卡片有「测试」按钮,可单独验证。

**可选 Kimi(国产备选)**:`KIMI_API_KEY` 走 Moonshot 官方 API,仅当客户做中文场景时需要。

详细字段含义见 [API 配置](/guides/settings)。

## 第 2 步:创建监测对象 (品牌)

[品牌列表](/clients) → 新建客户。关键字段:

- **品牌名**:这是 AI 回答里要匹配的字符串
- **行业 / 地区**:做语义上下文
- **关键词 / 别名 (`business_info.keywords`)**:同品牌的其他叫法(英文名、缩写、中文名),都会一并参与 mention 判定
- **网站 URL**:网站 GEO 诊断要用

详见 [监测对象 + 探针问题](/guides/clients-questions)。

## 第 3 步:录入探针问题

进客户详情页 → 「问题库」Tab → 录入问题或 CSV 导入。

好问题的特征:

- **品类问题**:「what are the best [品类] suppliers in 2026?」— 看 AI 给你的品类推荐谁
- **竞品问题**:「compare A vs B for [场景]」— 看竞品归因
- **用途问题**:「best [品类] for [具体用户群]」— 长尾流量

每个客户 5-20 个问题起步,后续可扩。

## 第 4 步:跑第一个 Run

[监测中心](/clients) → 选客户 → 点「新建实验运行」。

- **实验名**:取个能区分干预动作的名字,例如「2026-Q2 baseline」「改 llms.txt 后第 1 周」
- **平台**:勾 Perplexity + ChatGPT + Google AI(配了 key 的都勾上)
- **问题**:从题库选 5-10 个,或临时提问

⚠️ **防封号机制已内置**:
- 每个查询之间随机间隔 8-20 秒(模拟人类阅读)
- 每个平台每天最多 30 次查询(硬上限)
- 一次最多 20 个问题(硬上限)

提交后跳转任务进度页,几分钟内跑完。详见 [实验运行](/guides/runs)。

## 第 5 步:读数据

回到客户的监测中心,4 个 Tab:

| Tab | 看什么 |
|---|---|
| 概览 | 整体提及率、趋势、平台明细 |
| 实验运行 | 历次 Run 列表,可勾选加入对比 |
| 对比视图 | 多 Run 横向矩阵,看干预动作有没有效 |
| 引用来源 | **AI 最爱引用哪些站 + 竞品的 GEO 资产清单** |

详细解读看 [数据分析](/guides/analytics) 和 [引用来源](/guides/citation-sources)。

## 完整教程目录

- [API 配置](/guides/settings) — 各家 key 详解
- [监测对象 + 探针问题](/guides/clients-questions) — 客户字段、问题录入
- [实验运行](/guides/runs) — Run 触发、配额、防封号
- [数据分析](/guides/analytics) — 4 个 Tab 怎么读
- [引用来源](/guides/citation-sources) — 域名聚合 + 竞品归因
- [Website GEO 诊断](/guides/diagnosis) — 单站点 GEO 体检
- [运维 / 部署](/guides/operations) — 任务、用量、备份
