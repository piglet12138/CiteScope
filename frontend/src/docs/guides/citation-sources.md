# CiteScope · 引用来源 (Citation Sources) 使用手册

> 上线时间：2026-05-23
> 站点：<https://your-citescope-host.example/>
> 入口：客户详情 → **监测中心** → 顶部第 4 个 Tab「**引用来源**」

## 这个功能解决什么问题

跑 GEO 监测只回答了「我有没有被 AI 提到」。要做 GEO 内容投放，你还得回答另外两个问题：

1. **AI 在我这个品类最常引用哪些站？** → 这些站就是我应该铺内容的「弹药库」。
2. **AI 提到竞品时，引用了哪些 URL？** → 这些 URL 就是竞品已经握在手里的「GEO 资产」，反推它们的内容投放策略。

「引用来源」Tab 把每次监测拿到的 citation 拆开 → 解析 redirect → 抽注册域名 → 跨 run 聚合，回答这两个问题。

## 页面三块内容

### ① 引用规模概览

横向 6 个数字：

| 字段 | 含义 |
|---|---|
| 总 citation 数 | 该客户下所有监测 run 累计抓到的 citation 行数 |
| 独立域名 | 解析成功的 citation 去重后的域名数 |
| 已解析 (ok) | 已经抽出 registered domain，可参与聚合统计 |
| 待解析 (pending) | 等后台 worker（每 5 分钟一次）解析的 Gemini 重定向链接 |
| 跳过 (skipped) | ChatGPT 给的 `google.com/maps/search/...` 这类占位 URL，不计入聚合 |
| 失败 (failed) | 域名不可达 / 超时 等永久失败 |

底部还有一行 Tag 显示每个 AI 平台贡献了多少 citation。

### ② 品类高频引用域名 (Top Domains) — 报告 A

> 「我应该把内容铺到哪些站」

| 字段 | 怎么读 |
|---|---|
| 域名 | 注册域名，点击直接打开 |
| 被引次数 | 在选定时间窗内，AI 回答里引用该域名的总次数 |
| 跨平台 | 几家 AI 都引用过这个域名（≥2 表示信号更稳） |
| 支撑品牌提及 | 这个域名的 citation 里，有多少条出现在「**同一句**里同时提到了我的品牌名」——即这个站直接证明了 AI 对我的认知 |

**实操读法**：
- 跨平台 ≥ 2 + 被引 ≥ 10 → 投放优先级高
- 「支撑品牌提及」常年 0，说明 AI 还没把我的品牌跟任何第三方站绑在一起，这就是 GEO 起步现状

### ③ 竞品 GEO 资产清单 (Competitor Assets) — 报告 B

> 「竞品在哪些站铺得最深？」

操作流程：
1. 在输入框填竞品名，多个用逗号分隔（例：`Biorun,CJ,MeetSocks,Sinoknit`）
2. 点「查询」
3. 每个竞品出一张小表：在 AI 提到该竞品的回答里，引用最多的域名

**实操读法**：
- 竞品官网（如 `biorunsocks.com`、`cjsocks.com`）排第 1，说明竞品自己的 SEO/GEO 站本身就是 AI 引用源
- 排第 2-5 的第三方站（如 `made-in-china.com`、`alibaba.com`、`leelinesports.com` 这种「China socks manufacturers list」博客）→ 这些是公共战场，我也能去铺

## 筛选条件

页面中部的筛选条对 Top Domains 和 Competitor Assets **都生效**：

- **时间窗**：近 7 / 30 / 90 / 365 天（默认 30 天）
- **平台**：不选 = 全部；多选可对比单一平台的偏好
- **条数上限**：5-100（默认 20）

改完点「重新加载」才会刷 Top Domains。Competitor Assets 是按「查询」按钮触发。

## 数据来源与更新节奏

| 数据 | 来源 |
|---|---|
| Citation 原始数据 | `monitor_results.search_results`（每次 Run 自动写入） |
| Citation 解析 | 监测写入时即时算好域名；Gemini 重定向链接走后台 worker（每 5 min 一批 50 条） |
| 报表 | 实时 SQL 聚合，无缓存 |

**所以**：
- 新跑完一个 Run，Top Domains 立刻就有新增（普通域名）
- 如果 Gemini 平台占比高，等 5 min 一轮再刷，pending 会逐步归零

## 历史数据回填

如果在功能上线之前已经跑过的 Run（数据库里有 `monitor_results.search_results` 但没有 `monitor_citations`），用回填脚本一次拉平：

```bash
ssh <your-host> 'cd /opt/citescope/backend && \
  .venv/bin/python -m scripts.backfill_citations'
```

可选参数：

```
--limit N             只处理前 N 条
--client-id ID        只回填指定客户
--since YYYY-MM-DD    只回填该日期之后的
--verbose             调试日志
```

**幂等**：同一条 `monitor_result_id` 反复跑只会保留最新一份 citation。

## 部署 / 重启

| 操作 | 命令 |
|---|---|
| 重启后端（含 worker 重新计时） | `ssh <your-host> 'sudo systemctl restart citescope.service'` |
| 查看后端日志 | `ssh <your-host> 'sudo tail -f /var/log/citescope/backend.log'` |
| 查看 worker 跑没跑 | `ssh <your-host> 'grep "citation resolver" /var/log/citescope/backend.log \| tail'` |
| 备份 SQLite | `ssh <your-host> 'cp /opt/citescope/backend/data/geo.db{,.bak.$(date +%F)}'` |

> 关于前端更新：源码改动后必须在本地 `npm run build` 出 `dist/`，再 scp 到 `/opt/citescope/frontend/dist/`。目标主机没装 Node。

## 已知限制 / FAQ

**Q：为什么 ChatGPT 大量 citation 显示 status=skipped？**
A：ChatGPT 在没拿到真实页面 URL 时会用 `https://www.google.com/maps/search/...?utm_source=openai` 当占位。这是平台行为，本身没有第三方网页可指向，所以归到 skipped 不污染聚合。如果想去掉这种占位，可在 `chatgpt.py` 适配器里跳过 `annotation.type=="url_citation"` 中带这个 host 的项。

**Q：「支撑品牌提及」一直是 0 怎么办？**
A：两种情况：
1. AI 回答里根本没提你的品牌（GEO 起步期常见）
2. 客户资料里没填 `keywords` / `brand_aliases`，导致品牌匹配只用 `client.name` 字符串匹配。在客户详情里补充别名后，下一轮 Run 就会重新计算。

**Q：竞品分析的精度怎么提升？**
A：把竞品名（不带商标后缀，纯品牌）加进客户的 `keywords`，之后 `monitor_citations.supports_brand_mention` 在该客户下会同时覆盖自己 + 竞品的品牌提及。再用 SQL 直查
```sql
SELECT domain, COUNT(*) FROM monitor_citations
WHERE supports_brand_mention=1 AND ... GROUP BY domain;
```
能拿到比按 raw_answer LIKE 更准的结果。**前提**：竞品名要够独特（不要用 "CJ" 这种字面短的，容易误匹）。

**Q：报表为什么有时跑得慢？**
A：Top Domains / Competitor Assets 是实时聚合 SQL。当前 SQLite 单库，几千条 citation 内 < 100 ms。如果未来到 10 万级别再考虑加 ClickHouse 分层。

## 相关文件

- 后端代码：`/opt/citescope/backend/app/services/citation_analysis/`
- 后端路由：`/opt/citescope/backend/app/routers/citation_reports.py`
- 回填脚本：`/opt/citescope/backend/scripts/backfill_citations.py`
- 前端组件：`frontend/src/components/CitationSourcesPanel.tsx`
- 前端 API SDK：`frontend/src/api/citationReports.ts`
- GitHub：<https://github.com/piglet12138/CiteScope> 分支 `main`
