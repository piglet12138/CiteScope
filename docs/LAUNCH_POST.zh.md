# 发布 CiteScope —— 开源 AI Citation 分析平台

*2026-05-23 发布,约 1800 字。*

---

如果你 2026 年还在做品牌增长,八成已经发现一个不太舒服的现象:**有相当一部分购买意图的流量正在从 Google 流向 AI 对话窗口。**

当客户问 ChatGPT「2026 年中国最好的 B2B 袜厂有哪些」或者问 Perplexity「北美进口冷链物流找谁」,他们拿到的是一段 200 字的回答,点名三到五家供应商,带可点击的引用。他们不会再去翻十条蓝色链接。他们直接从 AI 的短名单里挑。

如果你的品牌不在这份短名单上,你就是隐形的 —— 哪怕 Google 上同样的搜索词你排第一。

这就是 **GEO** —— 生成式引擎优化(Generative Engine Optimization),或者 **AEO** —— 应答引擎优化(Answer Engine Optimization),2026 年中开始更常用的叫法。一个意思:优化 AI 搜索的可见度,而不只是 Google。

这个赛道很热。Topify、Profound、Peec.ai、Otterly、AthenaHQ —— 全部在过去 18 个月里冒出来,统一收 80-500 美元/月,告诉品牌:「ChatGPT 提到你的频率是 X%,提到你竞品的频率是 Y%,这些是 AI 引用的 URL。」

**今天我们开源 CiteScope**,一个 MIT 协议的自部署平台。商业工具能干的事它都能干,加上一个所有商业工具都没做的事。

[github.com/your-org/CiteScope](https://github.com/your-org/CiteScope)(替换为真实 URL)

## CiteScope 是什么

CiteScope 就是你如果手里有两个工程师 + 一个周末,你会自己造的那个 AI 搜索监测平台。具体来说:

- FastAPI 后端,跟六个 AI 搜索引擎对接(ChatGPT、Perplexity、Gemini、豆包、Kimi、DeepSeek)。优先走官方 API,没有官方 API 的那家(目前只剩 DeepSeek)走有据可查的 best-effort 逆向
- React + Antd 仪表板,四个核心页面 GEO 工具都有:总览、Run 历史、Run 对比、Citation 来源分析
- 后台 worker,每 5 分钟把 Gemini 的 `vertexaisearch.cloud.google.com/grounding-api-redirect/*` 解析成真实落地域名
- 单 SQLite 文件,一个 Docker 容器,1 GB 内存够跑
- 站内嵌入式教程中心,因为"文档藏在 wiki 深处"是产品死掉的主要原因之一

一行命令起服务:

```bash
git clone https://github.com/your-org/CiteScope.git
cd CiteScope
cp backend/.env.example backend/.env  # 填 API key
docker compose up -d
```

打开 `localhost:3000`,创建客户,粘贴探针问题,点「新建实验运行」。五分钟后你就有数据了。

## 唯一一个其他工具都没做的事

下面才是关键。商业 GEO 工具能告诉你这种话:

> 「上周你这个品类的 AI 回答里 Reddit 被引用了 78%。」

CiteScope 能告诉你**这句话**,还能再加一句更有用的:

> 「Reddit 被引用 78%。其中 23 次精确地支撑了提到你品牌的句子 —— 对比 55 次支撑的是无关竞品提及或行业通用论述。」

这叫**段落归因 (span attribution)**:把 AI 回答里的 `[citation:N]` 标记和品牌出现的实际位置交叉计算。它告诉你「Reddit 是高频引用源」(对,但没用)和「Reddit 30% 的时候在背书你品牌」(有用:加大 Reddit 投入)或「Reddit 引用了你品类里所有人除了你」(有用:gap 分析)的区别。

算法本身不难 —— 中英文混排的分句 + 品牌词位置和 citation 标记位置的区间交集。大概 90 行 Python (`backend/app/services/citation_analysis/span_attribution.py`)。难点不在算法,在于愿意做这一刀,而不是只画 PPT 仪表板。

商业工具没做这个,有两个原因:
1. 实时计算成本不低,营销卖点又不直观
2. 一旦做了,会暴露"citation 追踪"在大多数工具里其实有多浅

我们做了,因为我们用得上。我们的真实使用场景是一家 B2B 出口企业 —— 需要搞清楚哪些竞品在 AI 上更可见,以及 AI 的权威信号从哪些站来。「Reddit 很热」远远不够具体。

## 为什么开源

三个真实理由。

**第一,底层数据本身不是壁垒。** 所有 GEO 工具本质上做的是同一件事:把探针问题打到 AI 引擎、解析回答、存数据库、画图。差异在工作流打磨、集成、偶尔的某个聪明功能(Topify 的 source analysis,Profound 的企业 polish)。这些都不算火箭科学。整个行业卖的是 20 美元/月的服务,定价 200 美元/月,因为大多数买家懒得自托管。这个差价迟早会被磨平。

**第二,AI 搜索变化太快,闭源工具跟不上。** OpenAI 给 Responses API 加新字段。Google 把 `googleSearchRetrieval` 改名 `google_search`。Perplexity 决定 Sonar Pro 的 citations 跟 Sonar 不一样。一家新的中文 AI 引擎上线 Web Search,返回结构完全不同(豆包火山方舟 Ark 的 web_search builtin tool 就是 2026 Q1 上线的)。闭源 SaaS 得排路线图、发版本、更新文档、培训客服 —— 周期至少两周。CiteScope:复制一个 adapter,改六行,半天上线。

**第三,我们想撑住 GEO 长尾的研究者。** 研究 AI bias 的学者、服务垂直行业的小代理商、有奇怪需求的品牌(「监测 50 个行业 Telegram 群组同时还要 AI 搜索」)。这些场景没法挤进 $99-499/月的 SaaS 定价模型。开源解锁他们。

## v0.1 (今天) 有什么

- **6 家 AI 引擎**,citation 输出统一:ChatGPT (Responses + web search)、Perplexity (Sonar / OpenRouter 兼容)、Gemini (`google_search` 工具 + grounding redirect 自动解析)、豆包 (火山方舟 Ark `web_search` 内置工具)、Kimi (Moonshot API)、DeepSeek (`chat.deepseek.com` 逆向兜底)
- **Citation 来源分析**:Top Domains 报表 + Competitor Assets 报表
- **段落归因**:每条 citation 的 `supports_brand_mention` 字段
- **Run 实验**:矩阵 + 雷达图横向对比,验证 GEO 干预动作是否有效
- **Website GEO 诊断**:单 URL 体检(robots.txt、llms.txt、schema.org、AI 爬虫准入)
- **站内教程中心**:8 个模块独立 guide
- **防封号默认**:随机间隔、单日配额、硬上限

## v0.1 (今天) 没有什么

- 按地区监测(OpenAI 的 `user_location`、Perplexity 的 ccTLD pinning)
- 告警(Slack / Webhook 触发提及率下滑)
- 多租户 API key 隔离
- Postgres 后端(目前只支持 SQLite)
- 前端代码分割(当前 bundle ~2.6 MB)
- 公开只读报表 URL(按客户分享)

路线图在 README,欢迎 PR。

## 配置,一段话讲完

你需要三家 API key:OpenAI(用 ChatGPT web search 的 `OPENAI_OFFICIAL_API_KEY`)、Perplexity(直连或走 OpenRouter)、Google AI Studio。可选:火山方舟接豆包、Moonshot 接 Kimi。填进 `backend/.env`,跑 `docker compose up -d`,打开 `localhost:3000`。设置页每个字段都有详细说明 + 申请链接。站内教程中心(`/guides`)带你跑完第一个 Run。

预估第一周 API 花费,典型 100 prompt × 3 平台 × 周频度:大约 5-15 美元。Topify 用 99 美元/月给你的是同样的数据。

## 我们希望听到的反馈

- **Bug 报告**,任何类型 —— 适配器输出和 vendor 真实响应不匹配、span attribution 处理某种 Unicode 出错、运维问题
- **新 adapter 贡献**,我们目前没覆盖的引擎 —— Bing Copilot、Claude.ai、You.com、Brave Search 都在心愿单上
- **使用场景故事** —— 你想用这份数据做什么,商业工具不让你做的?告诉我们,我们优先做能解锁那些工作流的功能

## 最后一句

GEO 在 2027 年会变成基础线。每个在乎可发现性的品牌都会去测它。问题是测的方式 —— 是订一个 99 美元/月的 Topify dashboard,还是用你自家 0 美元/月的 SQLite 文件,顺带保留二次开发的自由度。

我们押第二种世界。如果你也认同,[给我们点个 Star](https://github.com/your-org/CiteScope),跑一个 Run 试试,告诉我们缺什么。

---

**项目地址**:[github.com/your-org/CiteScope](https://github.com/your-org/CiteScope)
**License**:MIT
**技术栈**:FastAPI, React + Antd, react-markdown, tldextract, httpx, APScheduler
**跟商业工具对比详表**:[docs/COMPARISON.md](./COMPARISON.md)
