from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from src.config import AppConfig, DOMAIN_OPTIONS, USER_AGENT

TIME_RANGE_YEARS: dict[str, int | None] = {
    "全部时间": None,
    "今年最新 (2026)": 0,
    "近 1 年": 1,
    "近 3 年": 3,
    "近 5 年": 5,
}


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    doi_clean = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi_clean.startswith(prefix):
            doi_clean = doi_clean[len(prefix):]
    return doi_clean.strip()


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:80]


def reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for pos in positions:
                words[pos] = word
    if not words:
        return ""
    return " ".join(words[i] for i in sorted(words.keys()))


def _detect_preprint_status(
    source_name: str,
    work_type: str | None = None,
    venue: str | None = None,
    doi: str = "",
    arxiv_id: str | None = None,
) -> tuple[bool, str]:
    venue_lower = (venue or "").lower()
    type_lower = (work_type or "").lower()
    if "arxiv" in venue_lower or arxiv_id or doi.startswith("10.48550/arxiv"):
        return True, "预印本·arXiv"
    if "biorxiv" in venue_lower or doi.startswith("10.1101/"):
        return True, "预印本·bioRxiv/medRxiv"
    if "medrxiv" in venue_lower:
        return True, "预印本·medRxiv"
    if type_lower == "preprint" or "preprint" in venue_lower:
        return True, f"预印本·{source_name}"
    return False, f"正式发表·{venue}" if venue else "正式发表"


def fetch_openalex_works(
    query: str,
    domain: str,
    config: AppConfig,
    limit: int = 25,
    time_range: str = "全部时间",
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "search": query,
        "per-page": limit,
        "select": (
            "id,doi,title,publication_year,publication_date,type,cited_by_count,"
            "authorships,primary_location,open_access,abstract_inverted_index,ids,"
            "referenced_works,related_works"
        ),
    }

    filters: list[str] = []
    concept_id = DOMAIN_OPTIONS.get(domain, {}).get("openalex_concept")
    if concept_id:
        filters.append(f"concepts.id:{concept_id}")
    years_back = TIME_RANGE_YEARS.get(time_range)
    if years_back is not None:
        start_year = datetime.now(timezone.utc).year - years_back
        filters.append(f"publication_year:>={start_year}")
    if filters:
        params["filter"] = ",".join(filters)

    if config.openalex_api_key:
        params["api_key"] = config.openalex_api_key

    resp = requests.get(
        "https://api.openalex.org/works",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=config.request_timeout,
    )
    resp.raise_for_status()
    items = resp.json().get("results", [])

    papers: list[dict[str, Any]] = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        doi = normalize_doi(item.get("doi"))
        ids = item.get("ids") or {}
        oa_url = (item.get("open_access") or {}).get("oa_url")
        primary_loc = item.get("primary_location") or {}
        source_obj = primary_loc.get("source") or {}
        venue = source_obj.get("display_name") or ""
        landing_url = primary_loc.get("landing_page_url") or (
            f"https://doi.org/{doi}" if doi else item.get("id", "")
        )

        authors: list[str] = []
        institutions: list[str] = []
        for a in (item.get("authorships") or [])[:6]:
            a_name = (a.get("author") or {}).get("display_name")
            if a_name:
                authors.append(a_name)
            for inst in a.get("institutions") or []:
                inst_name = inst.get("display_name")
                cc = inst.get("country_code")
                if inst_name:
                    label = f"{inst_name} ({cc})" if cc else inst_name
                    if label not in institutions:
                        institutions.append(label)

        is_preprint, badge = _detect_preprint_status(
            source_name="OpenAlex",
            work_type=item.get("type"),
            venue=venue,
            doi=doi,
        )

        papers.append(
            {
                "uid": doi or f"oa:{item.get('id', title[:32])}",
                "title": title,
                "authors": authors[:5],
                "institutions": institutions[:4],
                "pub_date": item.get("publication_date") or str(item.get("publication_year") or ""),
                "year": item.get("publication_year"),
                "citation_count": item.get("cited_by_count") or 0,
                "doi": doi,
                "s2_paper_id": None,
                "arxiv_id": None,
                "url": landing_url,
                "pdf_url": oa_url or "",
                "venue": venue,
                "abstract": reconstruct_openalex_abstract(item.get("abstract_inverted_index")),
                "tldr": "",
                "is_preprint": is_preprint,
                "source_badge": badge,
                "providers": ["OpenAlex"],
                "openalex_id": item.get("id") or ids.get("openalex"),
                "related_works": [w.split("/")[-1] for w in (item.get("related_works") or [])[:8]],
                "referenced_works": [w.split("/")[-1] for w in (item.get("referenced_works") or [])[:8]],
            }
        )
    return papers


def fetch_semantic_scholar_works(
    query: str,
    domain: str,
    config: AppConfig,
    limit: int = 25,
    time_range: str = "全部时间",
) -> list[dict[str, Any]]:
    headers = {"User-Agent": USER_AGENT}
    if config.semantic_scholar_api_key:
        headers["x-api-key"] = config.semantic_scholar_api_key

    params: dict[str, Any] = {
        "query": query,
        "limit": limit,
        "fields": (
            "paperId,title,abstract,year,publicationDate,citationCount,"
            "authors,venue,publicationTypes,externalIds,openAccessPdf,url,tldr"
        ),
    }
    s2_field = DOMAIN_OPTIONS.get(domain, {}).get("s2_fields")
    if s2_field:
        params["fieldsOfStudy"] = s2_field

    years_back = TIME_RANGE_YEARS.get(time_range)
    if years_back is not None:
        cur_y = datetime.now(timezone.utc).year
        params["year"] = f"{cur_y - years_back}-{cur_y}"

    resp = requests.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params=params,
        headers=headers,
        timeout=config.request_timeout,
    )
    resp.raise_for_status()
    items = resp.json().get("data", [])

    papers: list[dict[str, Any]] = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        ext_ids = item.get("externalIds") or {}
        doi = normalize_doi(ext_ids.get("DOI"))
        arxiv_id = ext_ids.get("ArXiv")
        venue = item.get("venue") or ""
        pub_types = item.get("publicationTypes") or []
        work_type = "preprint" if "Preprint" in pub_types or arxiv_id else ""

        is_preprint, badge = _detect_preprint_status(
            source_name="S2",
            work_type=work_type,
            venue=venue,
            doi=doi,
            arxiv_id=arxiv_id,
        )

        authors = [a.get("name", "") for a in (item.get("authors") or [])[:5] if a.get("name")]
        tldr_obj = item.get("tldr") or {}
        oa_pdf = (item.get("openAccessPdf") or {}).get("url") or ""

        papers.append(
            {
                "uid": doi or f"s2:{item.get('paperId')}",
                "title": title,
                "authors": authors,
                "institutions": [],
                "pub_date": item.get("publicationDate") or str(item.get("year") or ""),
                "year": item.get("year"),
                "citation_count": item.get("citationCount") or 0,
                "doi": doi,
                "s2_paper_id": item.get("paperId"),
                "arxiv_id": arxiv_id,
                "url": item.get("url") or (f"https://doi.org/{doi}" if doi else ""),
                "pdf_url": oa_pdf or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""),
                "venue": venue,
                "abstract": item.get("abstract") or "",
                "tldr": tldr_obj.get("text") or "",
                "is_preprint": is_preprint,
                "source_badge": badge,
                "providers": ["Semantic Scholar"],
                "openalex_id": None,
                "related_works": [],
                "referenced_works": [],
            }
        )
    return papers


def _enrich_via_s2_batch(papers: list[dict[str, Any]], config: AppConfig) -> None:
    lookup_ids: list[str] = []
    index_map: dict[str, int] = {}

    for idx, p in enumerate(papers):
        if p.get("tldr") and p.get("s2_paper_id"):
            continue
        ident = None
        if p.get("s2_paper_id"):
            ident = p["s2_paper_id"]
        elif p.get("doi"):
            ident = f"DOI:{p['doi']}"
        elif p.get("arxiv_id"):
            ident = f"ARXIV:{p['arxiv_id']}"
        if ident and ident not in index_map:
            index_map[ident] = idx
            lookup_ids.append(ident)

    if not lookup_ids:
        return

    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if config.semantic_scholar_api_key:
        headers["x-api-key"] = config.semantic_scholar_api_key

    chunk = lookup_ids[:40]
    resp = requests.post(
        "https://api.semanticscholar.org/graph/v1/paper/batch",
        params={"fields": "paperId,citationCount,tldr,openAccessPdf,externalIds"},
        json={"ids": chunk},
        headers=headers,
        timeout=config.request_timeout,
    )
    if resp.status_code != 200:
        return
    for req_id, data in zip(chunk, resp.json()):
        if not isinstance(data, dict):
            continue
        target = papers[index_map[req_id]]
        if not target.get("s2_paper_id") and data.get("paperId"):
            target["s2_paper_id"] = data["paperId"]
        if data.get("citationCount") is not None:
            target["citation_count"] = max(target.get("citation_count") or 0, data["citationCount"])
        if not target.get("tldr") and isinstance(data.get("tldr"), dict):
            target["tldr"] = data["tldr"].get("text") or ""
        if not target.get("pdf_url") and isinstance(data.get("openAccessPdf"), dict):
            target["pdf_url"] = data["openAccessPdf"].get("url") or ""


def search_academic_papers(
    query: str,
    domain: str,
    config: AppConfig,
    time_range: str = "全部时间",
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    oa_results: list[dict[str, Any]] = []
    s2_results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(fetch_openalex_works, query, domain, config, 25, time_range): "OpenAlex",
            pool.submit(fetch_semantic_scholar_works, query, domain, config, 25, time_range): "Semantic Scholar",
        }
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                res = fut.result()
                if src == "OpenAlex":
                    oa_results = res
                else:
                    s2_results = res
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else ""
                if src == "Semantic Scholar" and code == 429:
                    warnings.append(
                        "Semantic Scholar 公共接口当前限流（429），已自动保留 OpenAlex 结果；可在左侧栏填入 S2 API Key 解除限流。"
                    )
                else:
                    warnings.append(f"部分数据源暂不可用：{src} 检索异常（HTTP {code}）")
            except Exception as exc:
                warnings.append(f"部分数据源暂不可用：{src} 检索异常（{type(exc).__name__}）")

    merged: list[dict[str, Any]] = []
    doi_index: dict[str, int] = {}
    title_index: dict[str, int] = {}

    for paper in s2_results + oa_results:
        doi = paper.get("doi") or ""
        t_norm = normalize_title(paper.get("title"))

        match_idx = None
        if doi and doi in doi_index:
            match_idx = doi_index[doi]
        elif t_norm and t_norm in title_index:
            match_idx = title_index[t_norm]

        if match_idx is None:
            idx = len(merged)
            merged.append(paper)
            if doi:
                doi_index[doi] = idx
            if t_norm:
                title_index[t_norm] = idx
        else:
            existing = merged[match_idx]
            existing["citation_count"] = max(existing.get("citation_count") or 0, paper.get("citation_count") or 0)
            if not existing.get("abstract") and paper.get("abstract"):
                existing["abstract"] = paper["abstract"]
            if not existing.get("tldr") and paper.get("tldr"):
                existing["tldr"] = paper["tldr"]
            if not existing.get("pdf_url") and paper.get("pdf_url"):
                existing["pdf_url"] = paper["pdf_url"]
            if not existing.get("institutions") and paper.get("institutions"):
                existing["institutions"] = paper["institutions"]
            if not existing.get("s2_paper_id") and paper.get("s2_paper_id"):
                existing["s2_paper_id"] = paper["s2_paper_id"]
            if not existing.get("openalex_id") and paper.get("openalex_id"):
                existing["openalex_id"] = paper["openalex_id"]
            if not existing.get("related_works") and paper.get("related_works"):
                existing["related_works"] = paper["related_works"]
            if not existing.get("referenced_works") and paper.get("referenced_works"):
                existing["referenced_works"] = paper["referenced_works"]
            if not existing.get("doi") and doi:
                existing["doi"] = doi
                doi_index[doi] = match_idx
            for prov in paper.get("providers", []):
                if prov not in existing["providers"]:
                    existing["providers"].append(prov)
            if paper.get("is_preprint") and not existing.get("is_preprint"):
                existing["is_preprint"] = True
                existing["source_badge"] = paper["source_badge"]

    try:
        _enrich_via_s2_batch(merged, config)
    except Exception:
        pass

    merged.sort(
        key=lambda x: (1 if x.get("is_preprint") else 0, x.get("year") or 0, x.get("citation_count") or 0),
        reverse=True,
    )
    return merged[:40], warnings


def fetch_active_institutions_for_topic(query: str, config: AppConfig) -> list[dict[str, Any]]:
    """利用 OpenAlex 统计近 2 年某方向最活跃的高校/实验室，辅助科研追踪与求职套磁。"""
    params: dict[str, Any] = {
        "search": query,
        "filter": f"publication_year:>={datetime.now(timezone.utc).year - 2}",
        "per-page": 40,
        "select": "authorships",
    }
    if config.openalex_api_key:
        params["api_key"] = config.openalex_api_key

    resp = requests.get(
        "https://api.openalex.org/works",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=config.request_timeout,
    )
    resp.raise_for_status()
    counts: Counter[str] = Counter()
    for work in resp.json().get("results", []):
        seen_in_work: set[str] = set()
        for a in work.get("authorships") or []:
            for inst in a.get("institutions") or []:
                name = inst.get("display_name")
                cc = inst.get("country_code")
                if name:
                    label = f"{name} ({cc})" if cc else name
                    if label not in seen_in_work:
                        counts[label] += 1
                        seen_in_work.add(label)
    return [{"机构 / 实验室": k, "近期相关论文数": v} for k, v in counts.most_common(12)]


def _resolve_openalex_work(paper: dict[str, Any], config: AppConfig) -> dict[str, Any] | None:
    headers = {"User-Agent": USER_AGENT}
    params: dict[str, Any] = {"select": "id,related_works,referenced_works"}
    if config.openalex_api_key:
        params["api_key"] = config.openalex_api_key

    oa_id = (paper.get("openalex_id") or "").split("/")[-1]
    if oa_id.startswith("W"):
        resp = requests.get(
            f"https://api.openalex.org/works/{oa_id}",
            params=params,
            headers=headers,
            timeout=config.request_timeout,
        )
        if resp.status_code == 200:
            return resp.json()
    if paper.get("doi"):
        resp = requests.get(
            f"https://api.openalex.org/works/https://doi.org/{paper['doi']}",
            params=params,
            headers=headers,
            timeout=config.request_timeout,
        )
        if resp.status_code == 200:
            return resp.json()
    return None


def _batch_fetch_openalex_by_ids(short_ids: list[str], config: AppConfig) -> list[dict[str, Any]]:
    if not short_ids:
        return []
    ids_filter = "|".join(short_ids[:8])
    params: dict[str, Any] = {
        "filter": f"openalex:{ids_filter}",
        "per-page": 8,
        "select": "id,doi,title,publication_year,cited_by_count,primary_location",
    }
    if config.openalex_api_key:
        params["api_key"] = config.openalex_api_key
    resp = requests.get(
        "https://api.openalex.org/works",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=config.request_timeout,
    )
    if resp.status_code != 200:
        return []
    out = []
    for w in resp.json().get("results", []):
        loc = w.get("primary_location") or {}
        url = loc.get("landing_page_url") or w.get("doi") or w.get("id", "")
        out.append(
            {
                "title": w.get("title") or "Untitled",
                "year": w.get("publication_year") or "",
                "citationCount": w.get("cited_by_count") or 0,
                "url": url,
            }
        )
    return out


def fetch_similar_papers(paper: dict[str, Any], config: AppConfig, limit: int = 5) -> list[dict[str, Any]]:
    """优先使用 OpenAlex related_works（免限流），未命中再回退 Semantic Scholar。"""
    related_ids = paper.get("related_works") or []
    if not related_ids:
        oa_work = _resolve_openalex_work(paper, config)
        if oa_work:
            related_ids = [w.split("/")[-1] for w in (oa_work.get("related_works") or [])[:limit]]
    if related_ids:
        res = _batch_fetch_openalex_by_ids(related_ids[:limit], config)
        if res:
            return res

    ident = paper.get("s2_paper_id") or (f"DOI:{paper['doi']}" if paper.get("doi") else None)
    if not ident:
        return []
    headers = {"User-Agent": USER_AGENT}
    if config.semantic_scholar_api_key:
        headers["x-api-key"] = config.semantic_scholar_api_key
    resp = requests.get(
        f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{urllib.parse.quote(ident)}",
        params={"fields": "title,year,citationCount,venue,url", "limit": limit},
        headers=headers,
        timeout=config.request_timeout,
    )
    resp.raise_for_status()
    return resp.json().get("recommendedPapers", [])


def fetch_citation_network(
    paper: dict[str, Any], config: AppConfig, limit: int = 5
) -> dict[str, list[dict[str, Any]]]:
    """优先使用 OpenAlex cites + referenced_works（免限流），未命中再回退 Semantic Scholar。"""
    out: dict[str, list[dict[str, Any]]] = {"citations": [], "references": []}

    oa_id = (paper.get("openalex_id") or "").split("/")[-1]
    ref_ids = paper.get("referenced_works") or []
    if not oa_id.startswith("W") or not ref_ids:
        oa_work = _resolve_openalex_work(paper, config)
        if oa_work:
            oa_id = (oa_work.get("id") or "").split("/")[-1]
            if not ref_ids:
                ref_ids = [w.split("/")[-1] for w in (oa_work.get("referenced_works") or [])[:limit]]

    if oa_id.startswith("W"):
        params: dict[str, Any] = {
            "filter": f"cites:{oa_id}",
            "sort": "publication_date:desc",
            "per-page": limit,
            "select": "id,doi,title,publication_year,cited_by_count,primary_location",
        }
        if config.openalex_api_key:
            params["api_key"] = config.openalex_api_key
        cit_resp = requests.get(
            "https://api.openalex.org/works",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=config.request_timeout,
        )
        if cit_resp.status_code == 200:
            for w in cit_resp.json().get("results", []):
                loc = w.get("primary_location") or {}
                out["citations"].append(
                    {
                        "title": w.get("title") or "Untitled",
                        "year": w.get("publication_year") or "",
                        "citationCount": w.get("cited_by_count") or 0,
                        "url": loc.get("landing_page_url") or w.get("doi") or w.get("id", ""),
                    }
                )
        if ref_ids:
            out["references"] = _batch_fetch_openalex_by_ids(ref_ids[:limit], config)
        if out["citations"] or out["references"]:
            return out

    ident = paper.get("s2_paper_id") or (f"DOI:{paper['doi']}" if paper.get("doi") else None)
    if not ident:
        return out
    headers = {"User-Agent": USER_AGENT}
    if config.semantic_scholar_api_key:
        headers["x-api-key"] = config.semantic_scholar_api_key
    encoded = urllib.parse.quote(ident)

    cit_resp = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/{encoded}/citations",
        params={"fields": "title,year,citationCount,url", "limit": limit},
        headers=headers,
        timeout=config.request_timeout,
    )
    if cit_resp.status_code == 200:
        out["citations"] = [
            x.get("citingPaper", {}) for x in cit_resp.json().get("data", []) if x.get("citingPaper")
        ]
    ref_resp = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/{encoded}/references",
        params={"fields": "title,year,citationCount,url", "limit": limit},
        headers=headers,
        timeout=config.request_timeout,
    )
    if ref_resp.status_code == 200:
        out["references"] = [
            x.get("citedPaper", {}) for x in ref_resp.json().get("data", []) if x.get("citedPaper")
        ]
    return out


def fetch_arxiv_recent(categories: list[str], config: AppConfig, max_results: int = 12) -> list[dict[str, Any]]:
    cat_query = "+OR+".join(f"cat:{c}" for c in categories)
    url = (
        f"https://export.arxiv.org/api/query?search_query={cat_query}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=config.request_timeout)
    resp.raise_for_status()

    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    entries = []
    for entry in root.findall("a:entry", ns):
        title_el = entry.find("a:title", ns)
        id_el = entry.find("a:id", ns)
        pub_el = entry.find("a:published", ns)
        sum_el = entry.find("a:summary", ns)
        authors = [
            a.find("a:name", ns).text
            for a in entry.findall("a:author", ns)[:4]
            if a.find("a:name", ns) is not None and a.find("a:name", ns).text
        ]
        entries.append(
            {
                "title": re.sub(r"\s+", " ", (title_el.text or "")).strip() if title_el is not None else "",
                "url": id_el.text.strip() if id_el is not None and id_el.text else "",
                "published": (pub_el.text or "")[:10] if pub_el is not None else "",
                "summary": re.sub(r"\s+", " ", (sum_el.text or "")).strip()[:280] if sum_el is not None else "",
                "authors": authors,
            }
        )
    return [e for e in entries if e["title"]]


def fetch_biorxiv_recent(
    server: str, config: AppConfig, days: int = 3, max_results: int = 10
) -> list[dict[str, Any]]:
    end_dt = datetime.now(timezone.utc).date()
    start_dt = end_dt - timedelta(days=days)
    url = f"https://api.biorxiv.org/details/{server}/{start_dt.isoformat()}/{end_dt.isoformat()}/0"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=config.request_timeout)
    resp.raise_for_status()
    collection = resp.json().get("collection", [])[:max_results]
    out = []
    for item in collection:
        doi = item.get("doi", "")
        out.append(
            {
                "title": (item.get("title") or "").strip(),
                "url": f"https://doi.org/{doi}" if doi else "",
                "published": item.get("date", ""),
                "summary": (item.get("abstract") or "").strip()[:280],
                "authors": [a.strip() for a in (item.get("authors") or "").split(";")[:4] if a.strip()],
            }
        )
    return [e for e in out if e["title"]]


def fetch_daily_frontier(config: AppConfig) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []

    tasks = {
        "arXiv CS 最新预印本": lambda: fetch_arxiv_recent(["cs.AI", "cs.LG", "cs.CL"], config, 10),
        "arXiv 物理最新预印本": lambda: fetch_arxiv_recent(["quant-ph", "cond-mat", "physics.app-ph"], config, 8),
        "bioRxiv 近期生命科学预印本": lambda: fetch_biorxiv_recent("biorxiv", config, days=3, max_results=10),
        "medRxiv 近期医学预印本": lambda: fetch_biorxiv_recent("medrxiv", config, days=3, max_results=8),
    }

    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {pool.submit(fn): label for label, fn in tasks.items()}
        for fut in as_completed(future_map):
            label = future_map[fut]
            try:
                buckets[label] = fut.result()
            except Exception:
                buckets[label] = []
                warnings.append(f"今日前沿部分频道暂不可用：{label}")

    return buckets, warnings


def search_latest_frontier_papers(query: str, config: AppConfig, days: int = 30) -> list[dict[str, Any]]:
    """今日前沿实时检索：按日期倒序拉取 arXiv + OpenAlex 近 N 天最新论文。"""
    results: list[dict[str, Any]] = []
    q_clean = query.strip()
    if not q_clean:
        return results

    # 1) arXiv 按提交日期倒序
    try:
        q_enc = urllib.parse.quote(f"all:{q_clean}")
        url = (
            f"https://export.arxiv.org/api/query?search_query={q_enc}"
            f"&sortBy=submittedDate&sortOrder=descending&max_results=10"
        )
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=config.request_timeout)
        if resp.status_code == 200:
            ns = {"a": "http://www.w3.org/2005/Atom"}
            root = ET.fromstring(resp.text)
            for entry in root.findall("a:entry", ns):
                t_el = entry.find("a:title", ns)
                id_el = entry.find("a:id", ns)
                p_el = entry.find("a:published", ns)
                s_el = entry.find("a:summary", ns)
                authors = [
                    a.find("a:name", ns).text
                    for a in entry.findall("a:author", ns)[:4]
                    if a.find("a:name", ns) is not None and a.find("a:name", ns).text
                ]
                if t_el is not None and t_el.text:
                    results.append(
                        {
                            "source": "arXiv 最新",
                            "title": re.sub(r"\s+", " ", t_el.text).strip(),
                            "url": id_el.text.strip() if id_el is not None and id_el.text else "",
                            "published": (p_el.text or "")[:10] if p_el is not None else "",
                            "authors": authors,
                            "summary": re.sub(r"\s+", " ", (s_el.text or "")).strip()[:260] if s_el is not None else "",
                        }
                    )
    except Exception:
        pass

    # 2) OpenAlex 近 N 天最新发表
    try:
        since_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        params: dict[str, Any] = {
            "search": q_clean,
            "filter": f"from_publication_date:{since_date}",
            "sort": "publication_date:desc",
            "per-page": 10,
            "select": "id,doi,title,publication_date,authorships,primary_location",
        }
        if config.openalex_api_key:
            params["api_key"] = config.openalex_api_key
        oa_resp = requests.get(
            "https://api.openalex.org/works",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=config.request_timeout,
        )
        if oa_resp.status_code == 200:
            for w in oa_resp.json().get("results", []):
                loc = w.get("primary_location") or {}
                authors = [(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])[:4]]
                title = (w.get("title") or "").strip()
                if title:
                    results.append(
                        {
                            "source": "OpenAlex 最新",
                            "title": title,
                            "url": loc.get("landing_page_url") or w.get("doi") or w.get("id", ""),
                            "published": w.get("publication_date") or "",
                            "authors": [a for a in authors if a],
                            "summary": "",
                        }
                    )
    except Exception:
        pass

    results.sort(key=lambda x: x.get("published", ""), reverse=True)
    return results