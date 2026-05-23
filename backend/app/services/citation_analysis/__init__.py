"""Citation Source Analysis 子模块。

把 MonitorResult.search_results 的 raw JSON 规范化展平到 monitor_citations 表,
解析 redirect、抽取注册域名、根据 raw_answer 里 `[citation:N]` 标记与品牌
出现位置的共现关系标 supports_brand_mention,最终支撑两份报表:

- Report A: 品类高频引用域名 Top N (品牌可以去哪些站铺内容)
- Report B: 竞品 GEO 资产清单 (竞品被推荐时 AI 引用了哪些 URL)
"""
