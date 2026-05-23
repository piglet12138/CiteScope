# 实验运行 (Run)

> Run 是平台的核心工作单位。一次 Run = 一组探针问题 × 一批 AI 平台 × 一个时间点,跑完落到数据库,后续所有报表都基于 Run。

## 触发一次 Run

入口:客户的[监测中心](/clients) → 顶部右上角「**新建实验运行**」

### 必填字段

| 字段 | 含义 |
|---|---|
| 实验名 | 一句话标识。例:`2026-Q2 baseline`、`改 llms.txt 后第 1 周` |
| 备注 | 可选,记录本次干预动作 |
| 问题来源 | 「从题库选择」(勾你想跑的问题)或「临时提问」(贴 prompt 文本) |
| 平台 | 至少勾 1 个。Citation 分析三家:Perplexity / ChatGPT / Google AI |
| 最大问题数 | 防止误操作跑太多。默认 5,硬上限 20 |

提交后:
- 立刻创建 MonitorRun 行(状态 `running`)
- 后台异步开跑(APScheduler `BackgroundScheduler`)
- 返回 `task_id`,前端轮询任务进度

## 防封号机制(自动启用)

防止账号被封 / 触发 rate limit:

| 限制 | 默认值 | 改在哪 |
|---|---|---|
| 每查询间隔 | 8-20s 随机 | `m4_monitor/service.py:MIN_DELAY_SEC` |
| 单平台单日上限 | 30 次 | `DAILY_PLATFORM_LIMIT` |
| 单次 Run 问题数硬上限 | 20 | `HARD_MAX_QUESTIONS` |
| 默认问题数(未显式选) | 5 | `DEFAULT_MAX_QUESTIONS` |

**配额逻辑**:每个平台启动 Run 前先 SQL `COUNT` 当天已发起的查询数。超过 `DAILY_PLATFORM_LIMIT` → 整个平台跳过,但其他平台正常。

如果某平台今日已用完,前端会显示 `skipped_quota: ["perplexity", ...]`。

## 跑 Run 时发生什么

针对每个 (问题, 平台) 二元组:

1. `metering_context` 包一层 — 计算这次查询耗时
2. 调对应平台 adapter(`pw.query_ai_sync`)
3. 拿到结果:`raw_answer` + `search_results`(citation 列表)+ `is_mentioned` 等判定字段
4. 写一条 `MonitorResult` 行,立即 commit(前端轮询能看到增量)
5. **同事务把 search_results 展开成 monitor_citations 行**(域名抽取 / span attribution / Gemini wrapper 标 pending)
6. 写 `LLMCallLog` 计量:token 数、$ 成本、延迟、状态
7. sleep 8-20s,下一个

失败的 (问题, 平台) 不会中断整个 Run,会记 `errors[]` 数组继续。

## 多个 Run 的横向对比

监测中心「对比视图」Tab:

1. 在「实验运行」Tab 里勾选 2-N 个 Run(同客户)
2. 切到「对比视图」自动加载
3. 矩阵 + 雷达图同时展示
4. 每个 Run 一行:总体提及率 + 每平台细分

**典型用法 — A/B 测试 GEO 干预动作:**

| Run | 干预 | 提及率 |
|---|---|---|
| baseline-2026Q1 | (无干预) | 12% |
| after-llms-txt-2026Q1 | 加了 llms.txt | 18% |
| after-faq-2026Q2 | 站内加 FAQ schema | 24% |

→ 数字往上就证明动作有效,可以加大投入。数字平或下,这条路放弃。

## Run 的状态机

| status | 含义 |
|---|---|
| `running` | 进行中 |
| `completed` | 全部跑完,无错误 |
| `completed_with_errors` | 跑完但有部分 (问题, 平台) 失败 |

完成后 `finished_at` 字段写入。任务队列页能看到所有 Run 的进度。

## 常见坑

**Q:跑了 5 个问题但只回来 3 条结果?**
A:大概率是配额限制。看返回的 `skipped_quota` 字段,被跳过的平台今天已经用满 30 次。改天再跑或在 service.py 里调高 `DAILY_PLATFORM_LIMIT`(不推荐,容易触发真封号)。

**Q:Perplexity 一直 401 / 503?**
A:走 OpenRouter 时检查 `PERPLEXITY_API_BASE` 是不是 `https://openrouter.ai/api/v1` + `PERPLEXITY_API_KEY` 是不是 `sk-or-` 开头。两者必须配对。

**Q:Gemini 跑完后 citation 都是 pending?**
A:正常 — Gemini 给的是 `vertexaisearch.cloud.google.com/grounding-api-redirect/*` 重定向链接,需要后台 worker 解析。**worker 每 5 分钟跑一次**,1 批 50 条。等几轮就清完。

**Q:能不能并行跑多个 Run?**
A:可以,APScheduler 支持并发。但要注意 SQLite 单写,不要同时跑超过 2-3 个 Run(WAL 模式下读不会阻塞,但写会排队)。

## 关联

- Run 跑完后立即去[数据分析](/guides/analytics) 看结果
- Citation 的具体读法见 [引用来源](/guides/citation-sources)
- 任务进度跟踪在 [任务队列](/tasks),后台细节见 [运维](/guides/operations)
