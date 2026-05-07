"""네이버 뉴스 검색 OpenAPI - 도시별 개발사업·기업유치 신호 수집.

각 도시에 대해 키워드 셋(``DEV_KEYWORDS``)과 결합한 쿼리로 검색.
공식 API가 아니라 보조 신호이므로:
- 제목 또는 본문 일부(``description``)에 도시명 + 키워드가 모두 포함된 기사만 채택
- 매칭된 키워드는 ``keyword_hits`` 에 콤마 구분으로 저장
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


# 부동산 시장과 직접 관련 있는 대형 개발·교통·기업유치 키워드.
# 단순 소규모 사업이나 개인 재건축은 포함하지 않도록 구체적 키워드만 사용.
DEV_KEYWORDS: list[str] = [
    # 교통 인프라
    "GTX",
    "지하철",
    "경전철",
    "도시철도",
    "KTX",
    "트램",
    # 대규모 개발
    "산업단지",
    "신도시",
    "택지지구",
    "공공주택지구",
    "혁신도시",
    "스마트시티",
    "도시개발",
    # 기업 유치
    "기업유치",
    "본사이전",
    "투자유치",
    "R&D센터",
    "데이터센터",
]

# 뉴스가 부동산 시장 관련임을 확인하는 추가 키워드 (아래 중 1개 이상 있어야 함)
_REALESTATE_CONTEXT: list[str] = [
    "아파트", "주택", "부동산", "분양", "주거", "단지",
    "착공", "준공", "공사", "건설", "개발", "입주",
]


def fetch_dev_news_recent(months: int = 12) -> list[dict]:
    """모든 도시 × 키워드 조합으로 검색 → 도시별 결과 합집합 반환.

    Returns 행 스키마::

        city_code, published_at, title, url, source, keyword_hits
    """
    if not (NAVER_CLIENT_ID and NAVER_CLIENT_SECRET):
        log.warning(
            "NAVER_CLIENT_ID/SECRET 가 비어있어 개발사업 뉴스 수집을 건너뜁니다."
        )
        return []

    cutoff = datetime.now().astimezone() - timedelta(days=months * 31)
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    out: list[dict] = []
    seen_urls: set[str] = set()

    for city in cities_module.CITIES:
        for kw in DEV_KEYWORDS:
            query = f"{city.name} {kw}"
            try:
                resp = requests.get(
                    NAVER_NEWS_URL,
                    params={"query": query, "display": 30, "sort": "date"},
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
                desc = _strip_tags(it.get("description", ""))
                blob = f"{title} {desc}"

                # 1) 도시명이 제목 또는 본문에 실제 포함되어야
                if city.name not in blob:
                    continue

                # 2) 검색 키워드가 포함되어야
                hits = [k for k in DEV_KEYWORDS if k in blob]
                if kw not in hits:
                    continue

                # 3) 부동산 시장 관련 맥락어가 하나 이상 있어야
                #    (교통·기업유치 뉴스도 주택 수요에 영향을 주는 내용이어야 함)
                if not any(ctx in blob for ctx in _REALESTATE_CONTEXT):
                    # 교통·대형개발 키워드는 맥락어 없어도 허용
                    _INFRA_KW = {"GTX", "지하철", "경전철", "도시철도", "KTX", "트램",
                                  "신도시", "택지지구", "혁신도시"}
                    if kw not in _INFRA_KW:
                        continue

                # 4) 제목이 너무 짧으면 노이즈 제거
                if len(title) < 10:
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
                        "keyword_hits": ",".join(hits),
                    }
                )
    return out


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s or "").replace("&quot;", '"').replace("&amp;", "&")


def _parse_pubdate(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
