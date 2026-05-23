# 监测对象 + 探针问题

> 跑 GEO 监测要先把「监测谁」和「问什么」配清楚。这两者不动好,后面所有分析都失真。

## 监测对象 (Client)

入口:[品牌列表](/clients) → 「新建客户」

### 关键字段

| 字段 | 用途 | 写法建议 |
|---|---|---|
| `name` | 主品牌名,**直接用于 mention 判定** | 用 AI 回答里最可能出现的写法。例:`Acme`(不要 `Acme Co Co., Ltd.`) |
| `industry` | 行业 | 自由文本,主要给前端展示 |
| `region` | 主要目标地区 | 例:`Global B2B`、`North America` |
| `target_markets` | JSON 数组,出口市场列表 | 例:`["US","EU","JP"]` |
| `language` | 客户主语言 | `en` / `zh` — 决定生成的探针问题用什么语言模板 |
| `website_url` | 官网 | Website GEO 诊断要用 |
| `business_info` | 自由 JSON 字段,**最关键的是 `keywords` / `brand_aliases`** | 见下 |

### `business_info` 里的别名(决定 mention 检测精度)

`business_info` 是一段 JSON,里面三个字段会被合并成「品牌关键词列表」一起匹配:

```json
{
  "keywords": ["Acme", "Acme Co", "Acme Ltd"],
  "brand_aliases": ["ANV"],
  "aliases": ["安维袜业"]
}
```

合并规则:`client.name` + `keywords` + `brand_aliases` + `aliases`,**全部去重 + 大小写不敏感匹配**。

**实操建议:**
- 主品牌名(client.name)写 AI **最可能直接念** 的版本
- `keywords` 放英文别名 / 缩写 / 商标变体
- `aliases` 放中文名 / 旧名
- ⚠️ **不要放过于通用的词**(如 `socks`、`factory`),会撞一堆假阳性

### 多客户场景

- 平台支持多客户,每个客户独立题库、独立 Run、独立报表
- 数据库层(SQLite)用 `client_id` 做强隔离
- 当前 ANV 是唯一付费客户(id=1),理论上可以同时跑十几个客户共用一台 MC

## 探针问题 (Question / Probe)

入口:进客户详情页 → 「问题库」Tab

### 三类好问题

每个客户准备一个题库,理想分布:

| 类别 | 例子 | 目的 |
|---|---|---|
| **品类推荐** | "What are the best B2B sock manufacturers in China for 2026?" | 看 AI 给品类推谁,top N 名单里有没有自己 |
| **竞品对比** | "Compare CJ Socks vs Biorun for high-volume OEM orders" | 看竞品归因,AI 引用了竞品的哪些 URL |
| **用途/长尾** | "Best socks supplier for athletic compression brands" | 长尾流量,客户群细分 |

ANV 实测题库示例:5-8 个品类问题 + 5-8 个竞品问题 + 3-5 个用途问题。

### CSV 导入

题库支持 CSV 批量导入(在客户详情页底部),格式:

```csv
text,category,priority
What are the top sock OEM factories in China?,category,10
Compare Acme vs CJ for high-MOQ orders,competitor,8
```

- `category` 是分组标签,纯展示用
- `priority` 数字大优先(用于未选中时按优先级取前 N)

### 临时提问 (adhoc)

跑 Run 时如果想加一个不入题库的问题,选「新建 Run」→ 「临时提问」Tab → 一行一个。

这些问题会以 `is_active=False` 的 adhoc 状态进库,跑完就不再出现在题库默认视图里,但仍可在结果列表里筛选。

## 关键词 vs 问题文本 的关系

**问题文本里出现品牌名不算 mention!** 平台只看 AI **回答里**有没有品牌词。

所以问题尽量用「品类/竞品/场景」描述,**不要把自己的品牌写在问题里**(不然你测的是 AI 的复读能力,不是 GEO 可见度)。

反例(❌):"How is Acme compared to other Chinese sock factories?" — AI 多半会直接复述 Acme。
正例(✅):"Who are the top 5 sock OEM factories in China for international brands?" — 这才能看 AI 主动是否提到 Acme。

## 关联

- 题库改完之后,下一次 Run 才会生效
- 品牌别名改完,**对历史 Run 数据不会反算**;只影响新一轮 Run 的 mention 判定和 citation 的 supports_brand_mention 字段
- 如果想回填新别名到旧数据,跑 backfill 脚本(见 [运维](/guides/operations))
