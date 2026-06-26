#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Config-driven comment crawler and searchable comment archive.

The tool focuses on traceability:
- Every stored comment keeps comment_url, page_url, source_url and crawled_at.
- Optional raw snapshots can be saved for audit.
- Search results can be exported with clickable source columns.

It intentionally avoids hard-coding one platform's private API. Add a platform
by describing its HTML or JSON structure in a config file.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html as html_lib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from lxml import html as lxml_html
except Exception as exc:  # pragma: no cover - dependency check at runtime
    raise SystemExit("缺少 lxml，请先安装 lxml，或使用 Codex bundled Python。") from exc


SCHEMA = """
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    source_name TEXT NOT NULL,
    target TEXT,
    comment_id TEXT,
    author TEXT,
    rating REAL,
    rating_max REAL DEFAULT 5,
    rating_band TEXT,
    content TEXT NOT NULL,
    content_length INTEGER NOT NULL,
    created_at TEXT,
    comment_url TEXT,
    page_url TEXT NOT NULL,
    source_url TEXT NOT NULL,
    crawled_at TEXT NOT NULL,
    raw TEXT,
    fingerprint TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_comments_platform ON comments(platform);
CREATE INDEX IF NOT EXISTS idx_comments_source ON comments(source_name);
CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at);
CREATE INDEX IF NOT EXISTS idx_comments_rating_band ON comments(rating_band);
CREATE INDEX IF NOT EXISTS idx_comments_content_length ON comments(content_length);
"""


DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日",
)


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = normalize_space(str(value))
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Support second and millisecond timestamps.
        ts = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        return dt.datetime.fromtimestamp(ts).replace(microsecond=0).isoformat(sep=" ")

    text = normalize_space(str(value))
    if not text:
        return None

    # Chinese relative timestamps seen in community comments.
    rel = re.fullmatch(r"(\d+)\s*(秒|分钟|小时|天|周|月|年)前", text)
    if rel:
        amount = int(rel.group(1))
        unit = rel.group(2)
        delta_map = {
            "秒": dt.timedelta(seconds=amount),
            "分钟": dt.timedelta(minutes=amount),
            "小时": dt.timedelta(hours=amount),
            "天": dt.timedelta(days=amount),
            "周": dt.timedelta(weeks=amount),
            "月": dt.timedelta(days=30 * amount),
            "年": dt.timedelta(days=365 * amount),
        }
        return (dt.datetime.now() - delta_map[unit]).replace(microsecond=0).isoformat(sep=" ")

    if text.startswith("昨天"):
        tail = normalize_space(text.replace("昨天", "", 1))
        base = dt.datetime.now() - dt.timedelta(days=1)
        if re.fullmatch(r"\d{1,2}:\d{2}", tail):
            hour, minute = [int(x) for x in tail.split(":")]
            base = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return base.replace(microsecond=0).isoformat(sep=" ")

    # ISO strings with timezone suffix can be normalized by fromisoformat.
    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(iso_text)
        if parsed.tzinfo:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed.replace(microsecond=0).isoformat(sep=" ")
    except ValueError:
        pass

    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).replace(microsecond=0).isoformat(sep=" ")
        except ValueError:
            continue
    return text


def rating_band(rating: Optional[float], rating_max: Optional[float] = 5) -> Optional[str]:
    if rating is None:
        return None
    max_value = rating_max or 5
    if max_value <= 0:
        max_value = 5
    normalized = rating / max_value
    if normalized >= 0.8:
        return "high"
    if normalized >= 0.4:
        return "middle"
    return "low"


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def make_fingerprint(row: Dict[str, Any]) -> str:
    stable = "|".join(
        normalize_space(str(row.get(k) or ""))
        for k in ("platform", "source_name", "comment_id", "comment_url", "author", "created_at", "content")
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def insert_comment(conn: sqlite3.Connection, row: Dict[str, Any]) -> bool:
    content = normalize_space(row.get("content") or "")
    if not content:
        return False
    row = dict(row)
    row["content"] = content
    row["content_length"] = len(content)
    row["rating"] = parse_float(row.get("rating"))
    row["rating_max"] = parse_float(row.get("rating_max")) or 5
    row["rating_band"] = rating_band(row["rating"], row["rating_max"])
    row["created_at"] = parse_date(row.get("created_at"))
    row["crawled_at"] = row.get("crawled_at") or now_iso()
    row["fingerprint"] = make_fingerprint(row)
    columns = [
        "platform",
        "source_name",
        "target",
        "comment_id",
        "author",
        "rating",
        "rating_max",
        "rating_band",
        "content",
        "content_length",
        "created_at",
        "comment_url",
        "page_url",
        "source_url",
        "crawled_at",
        "raw",
        "fingerprint",
    ]
    values = [row.get(col) for col in columns]
    placeholders = ",".join("?" for _ in columns)
    try:
        conn.execute(
            f"INSERT INTO comments ({','.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return True
    except sqlite3.IntegrityError:
        return False


def fetch_url(url: str, user_agent: str, timeout: int = 20) -> Tuple[str, bytes]:
    parsed = urllib.parse.urlparse(url)
    is_remote_or_file = parsed.scheme in {"http", "https", "file"}
    if not is_remote_or_file and (re.match(r"^[a-zA-Z]:\\", url) or url.startswith("\\\\")):
        url = Path(url).resolve().as_uri()
    elif not is_remote_or_file and Path(url).exists():
        url = Path(url).resolve().as_uri()

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        final_url = resp.geturl()
        return final_url, resp.read()


def robots_allowed(url: str, user_agent: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return True
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    parser = urllib.robotparser.RobotFileParser()
    try:
        parser.set_url(robots_url)
        parser.read()
        return parser.can_fetch(user_agent, url)
    except Exception:
        # If robots cannot be read, do not block local research by default.
        return True


def save_snapshot(snapshot_dir: Optional[Path], source_name: str, source_url: str, body: bytes) -> Optional[str]:
    if not snapshot_dir:
        return None
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256((source_name + source_url + now_iso()).encode("utf-8")).hexdigest()[:16]
    suffix = ".json" if body[:1] in (b"{", b"[") else ".html"
    path = snapshot_dir / f"{source_name}_{digest}{suffix}"
    path.write_bytes(body)
    return str(path)


def extract_xpath(node: Any, spec: Any, base_url: str = "") -> Any:
    if spec is None:
        return None
    if isinstance(spec, str):
        spec = {"xpath": spec}
    xpath = spec.get("xpath")
    if not xpath:
        return spec.get("default")
    values = node.xpath(xpath)
    if not isinstance(values, list):
        values = [values]

    cleaned: List[str] = []
    for value in values:
        if hasattr(value, "text_content"):
            cleaned.append(normalize_space(value.text_content()))
        else:
            cleaned.append(normalize_space(str(value)))

    joiner = spec.get("join", " ")
    value = joiner.join(v for v in cleaned if v)
    if not value:
        value = spec.get("default")

    value_type = spec.get("type", "text")
    if value_type == "float":
        return parse_float(value)
    if value_type == "date":
        return parse_date(value)
    if value_type == "url" and value:
        return urllib.parse.urljoin(base_url, value)
    return value


def get_json_path(obj: Any, path: Optional[str]) -> Any:
    if not path:
        return obj
    current = obj
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def normalize_json_field(item: Dict[str, Any], field_spec: Any, base_url: str = "") -> Any:
    if field_spec is None:
        return None
    if isinstance(field_spec, str):
        field_spec = {"path": field_spec}
    value = get_json_path(item, field_spec.get("path"))
    if value is None:
        value = field_spec.get("default")
    value_type = field_spec.get("type", "text")
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if value_type == "float":
        return parse_float(value)
    if value_type == "date":
        return parse_date(value)
    if value_type == "url" and value:
        return urllib.parse.urljoin(base_url, str(value))
    return normalize_space(str(value)) if value is not None else None


def crawl_html_source(
    conn: sqlite3.Connection,
    source: Dict[str, Any],
    user_agent: str,
    snapshot_dir: Optional[Path],
    max_pages_override: Optional[int],
    ignore_robots: bool,
) -> Tuple[int, int]:
    html_cfg = source.get("html", {})
    start_urls = source.get("start_urls") or []
    if not start_urls:
        raise ValueError(f"{source.get('name')} 缺少 start_urls")

    inserted = 0
    seen = 0
    max_pages = max_pages_override or int(source.get("max_pages") or html_cfg.get("max_pages") or 1)
    delay = float(source.get("delay_seconds", 1.0))

    for start_url in start_urls:
        page_url = start_url
        for _ in range(max_pages):
            if not ignore_robots and not robots_allowed(page_url, user_agent):
                print(f"跳过 robots.txt 不允许的页面：{page_url}", file=sys.stderr)
                break
            final_url, body = fetch_url(page_url, user_agent=user_agent, timeout=int(source.get("timeout", 20)))
            snapshot = save_snapshot(snapshot_dir, source["name"], final_url, body)
            doc = lxml_html.fromstring(body)
            doc.make_links_absolute(final_url)
            nodes = doc.xpath(html_cfg["comment_xpath"])
            for node in nodes:
                fields = {
                    key: extract_xpath(node, spec, base_url=final_url)
                    for key, spec in html_cfg.get("fields", {}).items()
                }
                row = {
                    "platform": source.get("platform") or source["name"],
                    "source_name": source["name"],
                    "target": source.get("target"),
                    "rating_max": source.get("rating_max", 5),
                    "page_url": page_url,
                    "source_url": final_url,
                    "raw": json.dumps({"snapshot": snapshot, "mode": "html"}, ensure_ascii=False),
                    **fields,
                }
                if not row.get("comment_url"):
                    row["comment_url"] = final_url
                if insert_comment(conn, row):
                    inserted += 1
                seen += 1

            next_xpath = html_cfg.get("next_page_xpath")
            if not next_xpath:
                break
            next_values = doc.xpath(next_xpath)
            if not next_values:
                break
            next_url = next_values[0]
            if hasattr(next_url, "text_content"):
                next_url = next_url.text_content()
            page_url = urllib.parse.urljoin(final_url, str(next_url))
            time.sleep(delay)
    conn.commit()
    return seen, inserted


def crawl_json_source(
    conn: sqlite3.Connection,
    source: Dict[str, Any],
    user_agent: str,
    snapshot_dir: Optional[Path],
    max_pages_override: Optional[int],
    ignore_robots: bool,
) -> Tuple[int, int]:
    json_cfg = source.get("json", {})
    paging = source.get("pagination", {})
    max_pages = max_pages_override or int(paging.get("max_pages") or source.get("max_pages") or 1)
    page = int(paging.get("start", 1))
    step = int(paging.get("step", 1))
    delay = float(source.get("delay_seconds", 1.0))
    url_template = source.get("url_template")
    if not url_template:
        raise ValueError(f"{source.get('name')} 缺少 url_template")

    inserted = 0
    seen = 0
    next_url: Optional[str] = None

    for _ in range(max_pages):
        url = next_url or url_template.format(page=page)
        if not ignore_robots and not robots_allowed(url, user_agent):
            print(f"跳过 robots.txt 不允许的接口：{url}", file=sys.stderr)
            break
        final_url, body = fetch_url(url, user_agent=user_agent, timeout=int(source.get("timeout", 20)))
        snapshot = save_snapshot(snapshot_dir, source["name"], final_url, body)
        payload = json.loads(body.decode(source.get("encoding", "utf-8")))
        items = get_json_path(payload, json_cfg.get("items_path"))
        if not items:
            break
        if isinstance(items, dict):
            items = list(items.values())
        for item in items:
            if not isinstance(item, dict):
                continue
            fields = {
                key: normalize_json_field(item, spec, base_url=final_url)
                for key, spec in json_cfg.get("fields", {}).items()
            }
            row = {
                "platform": source.get("platform") or source["name"],
                "source_name": source["name"],
                "target": source.get("target"),
                "rating_max": source.get("rating_max", 5),
                "page_url": source.get("page_url_template", final_url).format(page=page),
                "source_url": final_url,
                "raw": json.dumps({"snapshot": snapshot, "item": item}, ensure_ascii=False),
                **fields,
            }
            if not row.get("comment_url"):
                row["comment_url"] = row["page_url"]
            if insert_comment(conn, row):
                inserted += 1
            seen += 1

        next_path = json_cfg.get("next_url_path")
        next_value = get_json_path(payload, next_path) if next_path else None
        next_url = urllib.parse.urljoin(final_url, str(next_value)) if next_value else None
        if not next_url:
            page += step
        time.sleep(delay)
    conn.commit()
    return seen, inserted


def crawl_command(args: argparse.Namespace) -> None:
    cfg = read_json(Path(args.config))
    user_agent = args.user_agent or cfg.get("user_agent") or "CommentCrawler/1.0 (+research; respectful)"
    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else None
    conn = connect_db(Path(args.db))
    total_seen = 0
    total_inserted = 0
    for source in cfg.get("sources", []):
        if args.source and source.get("name") not in args.source:
            continue
        mode = source.get("mode")
        if mode == "html":
            seen, inserted = crawl_html_source(conn, source, user_agent, snapshot_dir, args.max_pages, args.ignore_robots)
        elif mode == "json":
            seen, inserted = crawl_json_source(conn, source, user_agent, snapshot_dir, args.max_pages, args.ignore_robots)
        else:
            raise ValueError(f"不支持的 source mode：{mode}")
        print(f"{source.get('name')}: 抓取 {seen} 条，新增 {inserted} 条")
        total_seen += seen
        total_inserted += inserted
    print(f"完成：抓取 {total_seen} 条，新增 {total_inserted} 条，数据库 {args.db}")


def import_jsonl_command(args: argparse.Namespace) -> None:
    conn = connect_db(Path(args.db))
    inserted = 0
    seen = 0
    with Path(args.file).open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            row.setdefault("platform", args.platform or row.get("platform") or "import")
            row.setdefault("source_name", args.source_name or row.get("source_name") or Path(args.file).stem)
            row.setdefault("page_url", row.get("comment_url") or row.get("source_url") or args.default_url or "")
            row.setdefault("source_url", row.get("page_url") or args.default_url or "")
            if insert_comment(conn, row):
                inserted += 1
            seen += 1
    conn.commit()
    print(f"导入 {seen} 条，新增 {inserted} 条")


def build_search_query(args: argparse.Namespace) -> Tuple[str, List[Any]]:
    clauses = ["1=1"]
    params: List[Any] = []
    if args.platform:
        clauses.append("platform IN (%s)" % ",".join("?" for _ in args.platform))
        params.extend(args.platform)
    if args.source:
        clauses.append("source_name IN (%s)" % ",".join("?" for _ in args.source))
        params.extend(args.source)
    if args.rating_band:
        clauses.append("rating_band IN (%s)" % ",".join("?" for _ in args.rating_band))
        params.extend(args.rating_band)
    if args.min_rating is not None:
        clauses.append("rating >= ?")
        params.append(args.min_rating)
    if args.max_rating is not None:
        clauses.append("rating <= ?")
        params.append(args.max_rating)
    if args.min_length is not None:
        clauses.append("content_length >= ?")
        params.append(args.min_length)
    if args.max_length is not None:
        clauses.append("content_length <= ?")
        params.append(args.max_length)
    if args.start_date:
        clauses.append("created_at >= ?")
        params.append(parse_date(args.start_date))
    if args.end_date:
        clauses.append("created_at <= ?")
        params.append(parse_date(args.end_date))

    keywords = args.keyword or []
    if keywords and args.keyword_mode == "all":
        for keyword in keywords:
            clauses.append("content LIKE ?")
            params.append(f"%{keyword}%")
    elif keywords:
        clauses.append("(" + " OR ".join("content LIKE ?" for _ in keywords) + ")")
        params.extend(f"%{keyword}%" for keyword in keywords)

    sql = """
    SELECT id, platform, source_name, target, comment_id, author, rating,
           rating_max, rating_band, content, content_length, created_at,
           comment_url, page_url, source_url, crawled_at
    FROM comments
    WHERE {where}
    ORDER BY COALESCE(created_at, crawled_at) DESC, id DESC
    LIMIT ?
    """.format(where=" AND ".join(clauses))
    params.append(args.limit)
    return sql, params


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def print_table(rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        print("没有匹配结果")
        return
    for row in rows:
        content = row["content"]
        if len(content) > 160:
            content = content[:157] + "..."
        print("-" * 88)
        print(f"[{row['id']}] {row['platform']} / {row['source_name']} / {row.get('rating_band') or '-'} / {row.get('created_at') or '-'}")
        print(f"作者：{row.get('author') or '-'}  评分：{row.get('rating') or '-'}")
        print(f"内容：{content}")
        print(f"来源：{row.get('comment_url') or row.get('page_url') or row.get('source_url')}")


def export_rows(rows: Sequence[Dict[str, Any]], export_path: Path) -> None:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = export_path.suffix.lower()
    if suffix == ".jsonl":
        with export_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    elif suffix == ".json":
        export_path.write_text(json.dumps(list(rows), ensure_ascii=False, indent=2), encoding="utf-8")
    elif suffix == ".html":
        body = [
            "<!doctype html><meta charset='utf-8'><title>Comment Search Results</title>",
            "<style>body{font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.5;padding:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;vertical-align:top}th{background:#f3f6fa}</style>",
            "<table><thead><tr><th>ID</th><th>平台</th><th>评分</th><th>时间</th><th>作者</th><th>评论</th><th>可浏览来源</th></tr></thead><tbody>",
        ]
        for row in rows:
            url = row.get("comment_url") or row.get("page_url") or row.get("source_url") or ""
            body.append(
                "<tr>"
                f"<td>{row['id']}</td>"
                f"<td>{html_lib.escape(row.get('platform') or '')}</td>"
                f"<td>{html_lib.escape(str(row.get('rating') or ''))}</td>"
                f"<td>{html_lib.escape(row.get('created_at') or '')}</td>"
                f"<td>{html_lib.escape(row.get('author') or '')}</td>"
                f"<td>{html_lib.escape(row.get('content') or '')}</td>"
                f"<td><a href='{html_lib.escape(url)}'>{html_lib.escape(url)}</a></td>"
                "</tr>"
            )
        body.append("</tbody></table>")
        export_path.write_text("\n".join(body), encoding="utf-8")
    elif suffix == ".xlsx":
        try:
            import pandas as pd
        except Exception as exc:
            raise SystemExit("导出 xlsx 需要 pandas/openpyxl。可改用 .csv/.jsonl/.html。") from exc
        pd.DataFrame(list(rows)).to_excel(export_path, index=False)
    else:
        with export_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
            writer.writeheader()
            writer.writerows(rows)
    print(f"已导出：{export_path}")


def search_command(args: argparse.Namespace) -> None:
    conn = connect_db(Path(args.db))
    sql, params = build_search_query(args)
    rows = rows_to_dicts(conn.execute(sql, params).fetchall())
    print_table(rows)
    if args.export:
        export_rows(rows, Path(args.export))


def stats_command(args: argparse.Namespace) -> None:
    conn = connect_db(Path(args.db))
    rows = conn.execute(
        """
        SELECT platform, source_name, rating_band, COUNT(*) AS count,
               MIN(created_at) AS min_time, MAX(created_at) AS max_time
        FROM comments
        GROUP BY platform, source_name, rating_band
        ORDER BY platform, source_name, rating_band
        """
    ).fetchall()
    for row in rows:
        print(
            f"{row['platform']} / {row['source_name']} / {row['rating_band'] or '-'}: "
            f"{row['count']} 条，时间 {row['min_time'] or '-'} -> {row['max_time'] or '-'}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="可溯源评论抓取、归档、检索工具")
    parser.add_argument("--db", default="comments.db", help="SQLite 数据库路径，默认 comments.db")
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="按配置抓取 HTML/JSON 评论")
    crawl.add_argument("--config", required=True, help="抓取配置 JSON")
    crawl.add_argument("--source", action="append", help="只抓指定 source.name，可重复传入")
    crawl.add_argument("--max-pages", type=int, help="覆盖配置里的最大页数")
    crawl.add_argument("--snapshot-dir", help="保存原始 HTML/JSON 快照的目录")
    crawl.add_argument("--user-agent", help="自定义 User-Agent")
    crawl.add_argument("--ignore-robots", action="store_true", help="忽略 robots.txt；仅在有授权时使用")
    crawl.set_defaults(func=crawl_command)

    imp = sub.add_parser("import-jsonl", help="导入已整理好的 JSONL 评论")
    imp.add_argument("--file", required=True)
    imp.add_argument("--platform")
    imp.add_argument("--source-name")
    imp.add_argument("--default-url", help="导入数据缺少 URL 时使用的默认来源")
    imp.set_defaults(func=import_jsonl_command)

    search = sub.add_parser("search", help="检索评论")
    search.add_argument("--platform", action="append", help="平台过滤，可重复传入")
    search.add_argument("--source", action="append", help="source_name 过滤，可重复传入")
    search.add_argument("--keyword", action="append", help="关键词，可重复传入")
    search.add_argument("--keyword-mode", choices=["any", "all"], default="any", help="多关键词匹配方式")
    search.add_argument("--min-length", type=int, help="最小字数")
    search.add_argument("--max-length", type=int, help="最大字数")
    search.add_argument("--start-date", help="起始时间，如 2026-05-01")
    search.add_argument("--end-date", help="结束时间，如 2026-05-24")
    search.add_argument("--rating-band", action="append", choices=["high", "middle", "low"], help="评分段：high/middle/low")
    search.add_argument("--min-rating", type=float)
    search.add_argument("--max-rating", type=float)
    search.add_argument("--limit", type=int, default=50)
    search.add_argument("--export", help="导出路径，支持 .csv/.json/.jsonl/.html/.xlsx")
    search.set_defaults(func=search_command)

    stats = sub.add_parser("stats", help="查看数据库统计")
    stats.set_defaults(func=stats_command)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
