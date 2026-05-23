# 数据分析 — 监测中心 4 个 Tab

> 监测中心是 CiteScope 的主战场。每个客户都有一个独立的监测中心,4 个 Tab 各自回答不同问题。

## Tab 1:概览

回答 **「这个客户当前 GEO 现状怎么样?」**

### 顶部 KPI

| 指标 | 含义 | 怎么用 |
|---|---|---|
| 提及率 (mention_rate) | 跑过的 (问题, 平台) 对中,AI 提到品牌的比例 | 这是核心北极星指标 |
| 首位提及率 (first_mention_rate) | AI 列表式回答中,品牌排第 1 的比例 | 高代表 AI 把你当首选 |
| 链接引用率 (link_citation_rate) | mention 同时给了官网链接的比例 | 高代表 AI 不仅知道你,还导流 |
| 情感准确性 (sentiment_accuracy) | mention 是 positive 的比例 | 多数情况是 1.0(AI 商业问题答得客气) |

### 平台分布 + 趋势

- 平台细分:每个 AI 引擎单独的提及率 + 样本数。**如果 Perplexity 70% 但 ChatGPT 10%,说明只有特定渠道在引用你**。
- 趋势:按天聚合,看干预动作对应的拐点。

### 周期选择

- `today` — 今天
- `week` — 近 7 天
- `month` — 近 30 天(默认)

### 最近结果列表

下半部分是最近 50 条 MonitorResult,可以点开看 AI 的完整 raw_answer + citation。

## Tab 2:实验运行 (Runs)

回答 **「我做过哪些干预实验?」**

- 列表展示该客户所有 Run,按时间倒序
- 每行:实验名、状态、跑的问题数、平台、整体提及率
- **勾选 2-N 个 Run** 后底部按钮可切到「对比视图」

## Tab 3:对比视图

回答 **「我这次 GEO 动作有没有效果?」**

入参:Tab 2 勾选的 Run id 列表。

### 矩阵视图

横轴 = 平台,纵轴 = Run,单元格 = 提及率。颜色梯度直观看出哪次 Run 在哪个平台改善最大。

### 雷达图

把每个 Run 的多平台提及率叠在同一张雷达图上。如果新 Run 的雷达比旧的"鼓"出去一圈,就是改善;有的方向凹进去,说明那个平台反而下降。

### 实操用法

```
baseline-2026Q1     → 跑完先做 baseline
干预动作 A          → 加 llms.txt
A-after-2026Q1      → 1 周后跑一次对比

if A-after 提及率 > baseline → A 有效,继续投入
else → A 无效,换方向
```

## Tab 4:引用来源 ⭐

回答 **「AI 引用哪些站?竞品的 GEO 资产在哪?」**

这是平台最有价值的 Tab,完整说明见 [引用来源](/guides/citation-sources)。简要:

- **引用规模概览**:总 citation 数 / 独立域名 / 解析状态
- **Top Domains**:AI 最常引用的第三方域名 → 我应该铺内容的弹药库
- **Competitor Assets**:输入竞品名,看 AI 提到该竞品时引用了哪些 URL → 反推竞品的 GEO 资产

## 跨 Tab 的数据一致性

- `MonitorResult` 行是所有 Tab 的基础
- 概览 / 实验运行 / 对比视图 直接基于 `MonitorResult`
- 引用来源 基于 `monitor_citations`(MonitorResult.search_results 展开)

如果发现某个 Tab 数据缺失,可能是:
- 历史 Run 跑的时候 citation 还没上线 → 跑 `backfill_citations.py`(见 [运维](/guides/operations))
- Gemini citation 还在 pending 状态 → 等下一轮 worker(5min)

## 常见问题

**Q:提及率为什么是 0?**
A:三种可能:1. AI 真的没提你品牌(GEO 起步常见,这就是要优化的起点);2. 品牌别名没配全(回去检查 `business_info.keywords`);3. 问题写得太烂(问题里直接写品牌名导致 AI 复述,平台正确识别为「问题里就有,不算 mention」)。

**Q:对比视图加载不出来?**
A:确认勾的是同一个客户的 Run。跨客户对比目前不支持(语义不对)。

**Q:首位提及率永远是 0?**
A:首位判定要求 AI 回答里有清晰的编号列表(`1. xxx` 或 `- xxx`)且品牌在第 1 位。如果 AI 回答是段落体,这个指标会一直是 0,正常。
