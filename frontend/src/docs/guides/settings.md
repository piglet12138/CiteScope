# API 配置详解

> 平台所有 AI 搜索的 key 统一在 [系统配置](/settings) 页管理。**全部走官方 API key**,不再维护逆向 Cookie / JWT 流。

## 配置生效机制

- 优先级:`runtime_config.json` > `.env` > 代码默认值
- UI 保存 → 写入 `backend/data/runtime_config.json` → 后端 `reload_settings()` 立刻生效,**无需重启**
- 敏感字段:**留空 = 不修改**,避免误清空。彻底删除请用「清除」按钮(仅 `from_runtime=true` 时显示)

## Tab 结构

| Tab | 干什么 |
|---|---|
| AI 搜索 / 监测平台 | 4 家 AI 引擎的 key — ChatGPT / Perplexity / Gemini 三家是 Citation 分析必需,Kimi 是国产备选 |
| 其他 | 日志级别等运维参数 |

## Citation 分析三家(主)

### ChatGPT — `OPENAI_OFFICIAL_API_KEY` + `OPENAI_API_KEY` (兜底)

- 走 Responses API + `web_search_preview` 工具
- citation 在 `output[].content[].annotations[]` 里,type=`url_citation`
- 模型在 `OPENAI_MONITOR_MODEL`,默认 `gpt-4o-mini` 即可
- ChatGPT 给的 url 经常是 `https://www.google.com/maps/search/X?utm_source=openai` 这种占位 — 平台识别后归到 `skipped` 不污染聚合
- 两个 key 字段同填:优先 `OPENAI_OFFICIAL_API_KEY`,没填回退 `OPENAI_API_KEY`。一般用同一个 key 即可

### Perplexity — `PERPLEXITY_API_KEY` + `PERPLEXITY_MODEL` + `PERPLEXITY_API_BASE`

两种部署模式:

**模式 A — 直连官方:**
- `PERPLEXITY_API_BASE` = 留空(走默认 `https://api.perplexity.ai`)
- `PERPLEXITY_MODEL` = `sonar` / `sonar-pro` / `sonar-reasoning`
- `PERPLEXITY_API_KEY` = Sonar key

**模式 B — OpenRouter 代理(当前 ANV 在用):**
- `PERPLEXITY_API_BASE` = `https://openrouter.ai/api/v1`
- `PERPLEXITY_MODEL` = `perplexity/sonar-pro-search`
- `PERPLEXITY_API_KEY` = OpenRouter key(sk-or-... 开头)

OpenRouter 模式的好处:统一计费、自动 fallback、跨多家共用一把 key。

### Google AI — `GOOGLE_AI_API_KEY`

- 用 `gemini-2.5-flash` 或 `gemini-2.5-pro`(模型在 adapter 里硬编)
- 启用 `google_search` 工具(注意是新名字,不是 `googleSearchRetrieval`)
- citation 在 `candidates[0].groundingMetadata.groundingChunks[]`
- ⚠️ Gemini 给的 url 是 `vertexaisearch.cloud.google.com/grounding-api-redirect/*` 重定向,**后台 worker 每 5 分钟自动 resolve 一批** 50 条,转成真实落地域名

## Kimi(可选,国产备选)

- `KIMI_API_KEY` = Moonshot 官方付费 API key
- 申请:[platform.moonshot.cn/console/api-keys](https://platform.moonshot.cn/console/api-keys)
- 仅在客户做中文/国内场景监测时需要;ANV 当前业务是出口,可以不配

## 中文 AI 引擎(可选)

### 豆包 — `ARK_API_KEY` + `DOUBAO_MODEL` + `ARK_API_BASE`

- **走官方 API**:火山方舟 (Volcengine Ark) Responses API + 内置 `web_search` 工具
- 调用:`POST https://ark.cn-beijing.volces.com/api/v3/responses`,body 里 `tools:[{type:"web_search"}]`,单轮拿带 citation 的最终答案
- API Key:火山引擎控制台 → 方舟 → API Key 管理,Bearer 直接用
- 模型:默认 `doubao-seed-1-6-250615`,可改 thinking / flash 变体
- 引用字段:`output[].content[].annotations[].url_citation` 含 url + title + start_index + end_index;adapter 自动插 `[citation:N]` 标记到正文,supports_brand_mention 能正常算
- 计费:按 token + 每次 search call 单独计费(网页内容计入 prompt token)
- 国内主体,海外 IP 需走 ark.ap-southeast.bytepluses.com 或代理

### DeepSeek — `DEEPSEEK_REFRESH_TOKEN` (⚠️ best-effort)

- **DeepSeek 官方 API 暂时没有 web search 工具**(2026-05 状态)
- 唯一可行路径:走 chat.deepseek.com 网页 `refresh_token` + WASM POW 逆向
- 获取步骤:F12 → Application → Local Storage → chat.deepseek.com → key=`userToken` 那行 → 复制 value JSON
- 标记 best-effort:DeepSeek 反爬有 POW + token 可能 30 天失效,需要定期重抠
- 等 DeepSeek 推官方 search endpoint 后会切换回 API 模式

## 测试连通

每个平台卡片右上角有「测试」按钮:发一次 ping,验证 key 是否可用。多数走 key-presence 校验(不实调外部 API,避免烧钱);DeepSeek 实调一次刷 access_token 验证 refresh_token 是否还活。

## 关于已经下线的字段

下面这些字段从历史版本起就不再展示:

| 字段 | 原因 |
|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` | 平台不再生成文章,LLM 服务整体下线 |
| `GEO_USE_MOCK` | 不再支持 mock 模式 |
| `DOUBAO_REFRESH_TOKEN` / `DOUBAO_COOKIE` | 豆包改走火山方舟 Ark 官方 API,网页逆向下线 |
| `KIMI_BEARER` / `KIMI_COOKIE` | 改用 Moonshot 官方 API,不再走网页 JWT |

`.env` 里如果还残留这些值不影响 — 只是 UI 不再暴露编辑入口。

## 常见问题

**Q:UI 上保存了 OPENAI_OFFICIAL_API_KEY,但「测试 ChatGPT」失败说 not configured?**
A:检查是不是粘成了带前后空格/换行的字符串。复制 key 时只复制 `sk-...` 那段。

**Q:Perplexity 设置 PERPLEXITY_API_BASE 为 OpenRouter,但跑 Run 时 401?**
A:走 OpenRouter 时 `PERPLEXITY_API_KEY` 应该填 OpenRouter 的 key(sk-or-... 开头),不是 Perplexity 官方的 key。

**Q:误把 OPENAI_OFFICIAL_API_KEY 清空了想恢复?**
A:`backend/data/runtime_config.json` 里手动删掉对应字段,服务自动回退到 `.env` 里的默认值。
