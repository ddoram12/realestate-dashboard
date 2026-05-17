"""네이버 뉴스 검색 OpenAPI - 도시별 부동산 수요 신호 수집.

4개 카테고리 × 도시별로 검색:
  - 기업유치   : 기업·공장·R&D 센터 유치, 본사 이전, 투자
  - 인구/세대   : 인구 증가, 세대수 증가, 전입 증가
  - 교통개발   : 신규 철도·도로 개설, 역 신설
  - 개발사업   : 신도시·산업단지·혁신도시·택지지구
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests

from config import cities as cities_module
from config.settings import (
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_NEWS_URL,
)

log = logging.getLogger(__name__)


# ── 카테고리별 검색 키워드 ──────────────────────────────────────
# key   : keyword_hits 에 저장될 카테고리명 (앱 화면과 일치)
# value : 검색 쿼리에 사용할 키워드 목록
#         각 키워드마다 "{도시명} {키워드}" 쿼리를 1건 실행
SEARCH_GROUPS: dict[str, list[str]] = {
    "기업유치": [
        "기업유치",
        "투자유치",
        "본사이전",
        "공장설립",
        "R&D센터",
        "데이터센터",
    ],
    "인구증가": [
        "인구 증가",
        "세대수 증가",
        "인구 유입",
        "전입 증가",
    ],
    "교통개발": [
        "GTX",
        "지하철 개통",
        "경전철",
        "KTX",
        "트램",
        "철도 개통",
        "신규 도로",
        "도로 개설",
        "고속도로 개통",
    ],
    "개발사업": [
        "신도시",
        "산업단지",
        "혁신도시",
        "택지지구",
        "공공주택지구",
        "스마트시티",
    ],
}

# 전체 키워드 플랫 목록 (blob 매칭용)
ALL_KEYWORDS: list[str] = [kw for kws in SEARCH_GROUPS.values() for kw in kws]


def _city_variants(name: str) -> list[str]:
    """'수원시' → ['수원시', '수원'] 처럼 단축 변형 반환."""
    variants = [name]
    for suffix in ("특별시", "광역시", "특별자치시", "특별자치도", "시", "군", "구"):
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            short = name[: -len(suffix)]
            if short not in variants:
                variants.append(short)
            break
    return variants


def fetch_dev_news_recent(months: int = 12) -> list[dict]:
    """모든 도시 × 카테고리 쿼리로 검색 → 도시별 결과 반환.

    Returns 행 스키마::
        city_code, published_at, title, url, source, keyword_hits
    """
    if not (NAVER_CLIENT_ID and NAVER_CLIENT_SECRET):
        log.warning("NAVER_CLIENT_ID/SECRET 가 비어있어 뉴스 수집을 건너뜁니다.")
        return []

    cutoff = datetime.now().astimezone() - timedelta(days=months * 31)
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    out: list[dict] = []
    seen_urls: set[str] = set()

    for city in cities_module.CITIES:
        variants = _city_variants(city.name)

        for category, keywords in SEARCH_GROUPS.items():
            for kw in keywords:
                # 도시 단축명 + 키워드로 검색 (예: "수원 GTX")
                query = f"{variants[-1]} {kw}"
                try:
                    resp = requests.get(
                        NAVER_NEWS_URL,
                        params={"query": query, "display": 20, "sort": "date"},
                        headers=headers,
                        timeout=15,
                    )
                    resp.raise_for_status()
                    items = resp.json().get("items", [])
                except (requests.RequestException, ValueError) as e:
                    log.warning("네이버 뉴스 호출 실패 [%s/%s]: %s", city.name, kw, e)
                    continue

                for it in items:
                    url = it.get("originallink") or it.get("link") or ""
                    if not url or url in seen_urls:
                        continue

                    title = _strip_tags(it.get("title", ""))
                    desc  = _strip_tags(it.get("description", ""))
                    blob  = f"{title} {desc}"

                    # ① 도시명(또는 단축명) 중 하나가 기사에 포함되어야
                    if not any(v in blob for v in variants):
                        continue

                    # ② 검색한 키워드가 실제 기사 내용에 포함되어야
                    hits = [k for k in ALL_KEYWORDS if k in blob]
                    if not hits:
                        continue

                    # ③ 제목이 너무 짧으면 노이즈 제거
                    if len(title) < 8:
                        continue

                    pub = _parse_pubdate(it.get("pubDate"))
                    if not pub or pub < cutoff:
                        continue

                    seen_urls.add(url)
                    out.append(
                        {
                            "city_code": city.code,
                            "published_at": pub.isoformat(),
                            "title": title,
                            "url": url,
                            "source": "naver_news",
                            "keyword_hits": category + "," + ",".join(hits),
                        }
                    )

    return out


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s or "").replace("&quot;", '"').replace("&amp;", "&").strip()


def _parse_pubdate(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
