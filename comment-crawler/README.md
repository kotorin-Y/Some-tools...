# 评论抓取与检索工具

这是一个 Python 单文件工具，用于把不同网站、不同结构的评论统一保存到 SQLite，并按字数、时间、评分段、关键词进行检索和导出。它的核心原则是可溯源：每条评论都会保存 `comment_url`、`page_url`、`source_url` 和 `crawled_at`。

## 适用场景

- 游戏舆情分析：TapTap、好游快爆、Bilibili、论坛、新闻站评论区。
- 竞品评分追踪：按高分/中评/低分拆样本。
- 节奏复盘：按关键词、时间窗和长评筛选高质量评论。
- 证据留存：导出 HTML/CSV/JSONL/XLSX，保留可点击来源。

## 基本用法

初始化和抓取示例评论：

```powershell
python .\comment_crawler.py --db .\comments.db crawl --config .\comment_crawler_config.example.json --source demo_html_comments --snapshot-dir .\snapshots
```

检索低分、50字以内、包含“S2”的评论：

```powershell
python .\comment_crawler.py --db .\comments.db search --rating-band low --max-length 50 --keyword S2
```

检索 2026-05-01 到 2026-05-24 期间的长评，并导出为 HTML：

```powershell
python .\comment_crawler.py --db .\comments.db search --start-date 2026-05-01 --end-date 2026-05-24 --min-length 80 --export .\outputs\comments.html
```

查看数据库统计：

```powershell
python .\comment_crawler.py --db .\comments.db stats
```

## 检索条件

- `--keyword`：关键词，可重复传入。
- `--keyword-mode any|all`：多关键词任意命中或全部命中。
- `--min-length / --max-length`：按评论字数筛选。
- `--start-date / --end-date`：按评论时间筛选。
- `--rating-band high|middle|low`：按评分段筛选。默认按满分5分折算：
  - `high`：4分及以上。
  - `middle`：2分到4分之间。
  - `low`：2分以下。
- `--min-rating / --max-rating`：按原始评分筛选。
- `--platform / --source`：按平台或配置源筛选。
- `--export`：导出 `.csv`、`.json`、`.jsonl`、`.html`、`.xlsx`。

## 配置一个 HTML 评论页

在 `comment_crawler_config.example.json` 里新增 source：

```json
{
  "name": "your_site_reviews",
  "platform": "某平台",
  "target": "某游戏评论",
  "mode": "html",
  "rating_max": 5,
  "delay_seconds": 1,
  "max_pages": 3,
  "start_urls": ["https://example.com/game/reviews"],
  "html": {
    "comment_xpath": "//article[contains(@class,'comment')]",
    "fields": {
      "comment_id": "./@data-id",
      "author": ".//*[contains(@class,'author')]/text()",
      "rating": {"xpath": ".//*[contains(@class,'rating')]/@data-score", "type": "float"},
      "created_at": {"xpath": ".//time/@datetime", "type": "date"},
      "content": {"xpath": ".//*[contains(@class,'content')]//text()", "join": " "},
      "comment_url": {"xpath": ".//a[contains(@class,'permalink')]/@href", "type": "url"}
    },
    "next_page_xpath": "//a[@rel='next']/@href"
  }
}
```

## 配置一个 JSON 接口

如果评论来自公开 JSON 接口，使用 `mode: json`：

```json
{
  "name": "your_json_reviews",
  "platform": "某平台",
  "target": "某游戏评论",
  "mode": "json",
  "rating_max": 5,
  "url_template": "https://example.com/api/comments?page={page}",
  "page_url_template": "https://example.com/game/reviews?page={page}",
  "pagination": {"start": 1, "step": 1, "max_pages": 5},
  "json": {
    "items_path": "data.comments",
    "fields": {
      "comment_id": "id",
      "author": "user.name",
      "rating": {"path": "score", "type": "float"},
      "created_at": {"path": "created_at", "type": "date"},
      "content": "content",
      "comment_url": {"path": "url", "type": "url"}
    },
    "next_url_path": "data.next_url"
  }
}
```

## 导入人工整理或浏览器导出的评论

如果平台强依赖登录或反爬，可以先用浏览器或平台后台导出 JSONL，再导入：

```powershell
python .\comment_crawler.py --db .\comments.db import-jsonl --file .\manual_comments.jsonl --platform TapTap --source-name manual_taptap --default-url https://www.taptap.cn/app/188212/review
```

每行 JSON 推荐包含：

```json
{"author":"玩家A","rating":1,"created_at":"2026-05-21","content":"评论正文","comment_url":"https://example.com/review/123","page_url":"https://example.com/reviews"}
```

## 合规与稳定性说明

- 默认会检查 `robots.txt`；只有在你确认有授权时才使用 `--ignore-robots`。
- 对公开网页建议设置 `delay_seconds`，避免高频访问。
- 对需要登录、验证码、签名参数或强动态渲染的网站，不建议绕过限制。可以使用人工导出、公开 API、平台授权接口或浏览器保存的 HTML 再导入。
- 所有检索结果都会保留可浏览来源，适合放进舆情报告、复盘材料或证据表。
