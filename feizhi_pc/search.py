# -*- coding: utf-8 -*-
"""联网搜索 —— 给绯栀一个真能查资料的入口。

★ 2026-10-25 重要更正：以前这里爬 Bing/DuckDuckGo 的 HTML，是次优方案。
  DeepSeek 官方已经上线 **Search / Fetch API**（自研搜索引擎），
  文档：https://api-docs.deepseek.com/zh-cn/guides/search/

      POST https://api.deepseek.com/v1/tools/search   5 元 / 1000 次
      POST https://api.deepseek.com/v1/tools/fetch    5 元 / 1000 次

  它比爬 HTML 好在：返回结构化的 `summary`（600~800 字，官方注明"适用于给模型
  阅读"）、`date`（发布时间，时效问题全靠它）、`authority`（权威性 0~4）、
  `rerank_score`（质量分 0~3，≥1.5 为优质），还支持 `lang:` / `after:` / `site:`
  等搜索语法。实测查"杭州明天天气"直接返回"明天多云，17℃～24℃"。

所以现在的顺序是：
    1. DeepSeek Search API（主路径，需 DEEPSEEK_API_KEY / llm_config.json 里的 key）
    2. Bing HTML 爬虫（兜底：无 key、余额不足、限速、接口异常时）
    3. DuckDuckGo Lite（最后的备源，国内网络常超时，只留 6 秒耐心）

设计取舍：
  * **每轮最多 1 次搜索**，且同一句话 5 分钟内复用结果 —— 一次搜索 0.005 元，
    但更重要的是别让一条回复等太久。
  * **失败静默返回空**，让上层退回"按人格回一句"，绝不让搜索把回复卡死。
  * 只取文本不抓正文（`need_content=False`）；真需要正文时才走 Fetch。
"""
from __future__ import annotations

import html
import logging
import re
import ssl
import threading
import time
import urllib.parse
from pathlib import Path
from urllib.request import Request, urlopen

import requests

LOG = logging.getLogger("feizhi_pc.search")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 爬虫兜底路径的耐心值（API 路径有自己的超时）
TIMEOUT = 6
FETCH_TIMEOUT = 15

DS_BASE = "https://api.deepseek.com"
DS_SEARCH = DS_BASE + "/v1/tools/search"
DS_FETCH = DS_BASE + "/v1/tools/fetch"
DS_TIMEOUT = 25

_BING = "https://www.bing.com/search?q={q}&form=QBLH"
_DDG = "https://lite.duckduckgo.com/lite/?q={q}"
_CTX = ssl.create_default_context()

CACHE_TTL = 300.0        # 秒
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_LOCK = threading.Lock()

_CONFIG_FILE = Path(r"<PROJECT_ROOT>\feizhi_pc\llm_config.json")
_ENV_FILE = Path(r"D:\Hermes\.env")
_key_cache: dict = {"ts": 0.0, "key": ""}


# ---------------------------------------------------------------- key 解析
def _api_key() -> str:
    """取 DeepSeek key：先看 llm_config.json（她自己的配置），再回退 .env。

    成功解析后缓存 5 分钟，避免每条消息都读盘。
    """
    now = time.time()
    if _key_cache["key"] and now - _key_cache["ts"] < 300:
        return _key_cache["key"]
    key = ""
    try:
        import json
        cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        key = ((cfg.get("providers") or {}).get("deepseek") or {}).get("api_key", "") or ""
    except Exception:  # noqa: BLE001
        key = ""
    if not key:
        try:
            for line in _ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
        except OSError:
            key = ""
    _key_cache.update(ts=now, key=key)
    return key


# ---------------------------------------------------------------- 主路径
def _ds_search(query: str, limit: int) -> list[dict]:
    key = _api_key()
    if not key:
        LOG.info("没有 DeepSeek key，跳过 Search API")
        return []
    payload = {
        "query": query[:128],
        "count": max(1, min(limit, 10)),
        "need_content": False,
    }
    r = requests.post(DS_SEARCH,
                      headers={"Authorization": "Bearer " + key,
                               "Content-Type": "application/json"},
                      json=payload, timeout=DS_TIMEOUT)
    if r.status_code != 200:
        # 402 余额不足 / 429 限速 / 5xx —— 都不重试，直接让上层走兜底
        LOG.warning("Search API HTTP %s: %s", r.status_code, r.text[:140])
        return []
    rows = []
    for it in (r.json().get("results") or []):
        rows.append({
            "title": it.get("title") or "",
            "url": it.get("url") or "",
            "snippet": it.get("snippet") or "",
            # summary 是 600~800 字的长摘要，正是"给模型读"的那份
            "summary": it.get("summary") or "",
            "date": (it.get("date") or "")[:10],
            "authority": it.get("authority"),
            "score": it.get("rerank_score"),
            "source": "ds",
        })
    return rows


# ---------------------------------------------------------------- 兜底爬虫
def _get(url: str, referer: str = "", timeout: int = TIMEOUT) -> str:
    headers = {"User-Agent": UA,
               "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
               "Accept": "text/html,application/xhtml+xml"}
    if referer:
        headers["Referer"] = referer
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout, context=_CTX) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(html.unescape(s).split())


_AGE = re.compile(r"(\d+\s*(?:分钟|小时|天|周|个月|年)之?前|"
                  r"\d{4}年\d{1,2}月\d{1,2}日|昨天|前天|今天)")
_NOISE = ("点击进入", "广告", "登录", "注册", "下载APP", "版权所有")


def _extract_age(text: str) -> str:
    m = _AGE.search(text or "")
    return m.group(1) if m else ""


def _bing(query: str, limit: int) -> list[dict]:
    page = _get(_BING.format(q=urllib.parse.quote_plus(query)),
                referer="https://www.bing.com/")
    out: list[dict] = []
    for m in re.finditer(r'<li class="b_algo".*?</li>', page, re.S):
        block = m.group(0)
        hm = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not hm:
            continue
        pm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        snippet = _strip_tags(pm.group(1)) if pm else ""
        if any(n in snippet for n in _NOISE) and len(snippet) < 20:
            continue
        out.append({
            "title": _strip_tags(hm.group(2)),
            "snippet": snippet,
            "summary": "",
            "url": html.unescape(hm.group(1)),
            "date": _extract_age(block),
            "authority": None,
            "score": None,
            "source": "bing",
        })
        if len(out) >= limit:
            break
    return out


def _ddg(query: str, limit: int) -> list[dict]:
    page = _get(_DDG.format(q=urllib.parse.quote_plus(query)))
    out: list[dict] = []
    for m in re.finditer(
            r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            r'.*?<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
            page, re.S):
        url, title, snippet = m.group(1), _strip_tags(m.group(2)), _strip_tags(m.group(3))
        if not title:
            continue
        out.append({"title": title, "snippet": snippet, "summary": "",
                    "url": html.unescape(url), "date": _extract_age(snippet),
                    "authority": None, "score": None, "source": "ddg"})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- 对外接口
def web_search(query: str, limit: int = 4, use_cache: bool = True) -> list[dict]:
    """联网搜一条，返回 [{title, snippet, summary, url, date, authority, score, source}]。

    源顺序：DeepSeek Search API → Bing → DuckDuckGo。
    """
    query = (query or "").strip()
    if not query:
        return []
    ck = "%s|%d" % (query, limit)
    if use_cache:
        with _LOCK:
            hit = _CACHE.get(ck)
        if hit and time.time() - hit[0] < CACHE_TTL:
            LOG.debug("搜索缓存命中: %s", query[:24])
            return hit[1]

    sources = (
        ("deepseek", _ds_search),
        ("bing", _bing),
        ("ddg", _ddg),
    )
    for name, fn in sources:
        try:
            rows = fn(query, limit)
            if rows:
                good = [r for r in rows if (r.get("score") is None or r["score"] >= 1.0)]
                rows = good or rows
                LOG.info("搜索命中 %d 条（%s）: %s", len(rows), name, query[:30])
                with _LOCK:
                    _CACHE[ck] = (time.time(), rows)
                    if len(_CACHE) > 200:
                        for k in list(_CACHE)[:100]:
                            _CACHE.pop(k, None)
                return rows
            LOG.info("%s 无结果，换下一个源: %s", name, query[:30])
        except Exception as exc:  # noqa: BLE001
            LOG.warning("%s 搜索失败: %s", name, exc)
    return []


def format_for_llm(rows: list[dict], max_len: int = 1200) -> str:
    """把搜索结果压成给 LLM 看的短文本。

    优先用 Search API 的 `summary`（600~800 字长摘要，信息密度高），
    没有时退回 `snippet`。带上发布日期，让模型能判断"这是不是最新的"。
    """
    if not rows:
        return ""
    lines = []
    for i, r in enumerate(rows, 1):
        body = (r.get("summary") or r.get("snippet") or "").strip()
        body = " ".join(body.split())
        head = "%d. %s" % (i, r.get("title", ""))
        if r.get("date"):
            head += "（%s）" % r["date"]
        lines.append(head + "：" + body[:400])
    return "\n".join(lines)[:max_len]


def fetch_page(url: str, max_chars: int = 2000) -> str:
    """抓一个网页的正文（Markdown 文本）。走 Fetch API，失败退回本地抓取。"""
    key = _api_key()
    if key:
        try:
            r = requests.post(DS_FETCH,
                              headers={"Authorization": "Bearer " + key,
                                       "Content-Type": "application/json"},
                              json={"url": url}, timeout=DS_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                return (data.get("content") or "")[:max_chars]
            LOG.warning("Fetch API HTTP %s: %s", r.status_code, r.text[:120])
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Fetch API 异常: %s", exc)

    try:
        raw = _get(url, timeout=FETCH_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("抓取失败 %s: %s", url[:60], exc)
        return ""
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    return _strip_tags(raw)[:max_chars]


# ---------------------------------------------------------------- 要不要搜
# 需要"先查再答"的信号（粗筛，宁可多查一次；用不用由模型自己判断）
SEARCH_HINTS = (
    "天气", "气温", "下雨", "新闻", "多少钱", "价格", "几号", "什么时候", "几点",
    "上映", "比赛", "比分", "股价", "汇率", "是谁", "查一下", "搜一下", "帮我查",
    "查查", "怎么样", "为什么", "最新", "最近", "今天", "明天", "后天", "现在",
    "票房", "销量", "发布", "出了吗", "开了吗", "营业", "几点开门", "限行", "热搜",
)

# 口语词，搜索时去掉能显著提高命中率
_FILLER = re.compile(
    r"(你说|那个|就是|帮我|能不能|可不可以|你知道|我想知道|告诉|一下|"
    r"[啊呀呢吗吧嘛哦噢诶哈〜~，,。？?！!、…\s]+)")


def build_query(text: str, limit: int = 60) -> str:
    """把口语问题压成搜索词（不进 LLM，省一次调用）。

    「你说那个流浪地球3到底什么时候上映啊」→「流浪地球3到底什么时候上映」
    """
    t = _FILLER.sub(" ", text or "")
    t = " ".join(t.split())
    return t[:limit] or (text or "")[:limit]


def needs_search(text: str) -> bool:
    """这句话要不要联网查。命中任意信号词即查（决策权仍交给 LLM）。"""
    t = text or ""
    if len(t) > 400:          # 长贴/小说片段不查
        return False
    return any(k in t for k in SEARCH_HINTS)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    q = sys.argv[1] if len(sys.argv) > 1 else "杭州明天天气"
    print("needs_search:", needs_search(q))
    print("build_query :", build_query(q))
    rows = web_search(build_query(q), limit=4)
    if not rows:
        print("(无结果)")
    for r in rows:
        print("- [%s] %s  %s  score=%s auth=%s"
              % (r["source"], r["title"][:50], r.get("date") or "",
                 r.get("score"), r.get("authority")))
        print("   ", (r.get("summary") or r.get("snippet") or "")[:120])
    print()
    print("--- format_for_llm ---")
    print(format_for_llm(rows))
