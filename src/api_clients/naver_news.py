"""네이버 뉴스 검색 OpenAPI - 도시별 부동산 수요 신호 수집.

4개 카테고리로 검색:
  - 기업유치   : 기업·공장 유치, 본사 이전, 투자
  - 인구증가   : 인구·세대수 증가, 전입 증가
  - 교통개발   : 신규 철도·도로 개설, 역 신설
  - 개발사업   : 신도시·산업단지·혁신도시·택지지구

설계 원칙:
  - 네이버 검색 결과의 관련도(relevance)를 신뢰 → blob 키워드 매칭 제거
  - 도시명이 제목에 포함되는지 우선 확인 → 노이즈 최소화
  - 카테고리별로 여러 검색어(유의어·다른 표현) 사용 → 누락 최소화
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


# ── 카테고리별 검색 쿼리 목록 ─────────────────────────────────
# 각 항목은 "{도시 단축명} {쿼리}" 로 조합해 검색
SEARCH_GROUPS: dict[str, list[str]] = {
    "기업유치": [
        "기업 유치",
        "기업 이전",
        "투자 유치",
        "공장 설립",
        "본사 이전",
        "R&D센터",
        "데이터센터 건립",
    ],
    "인구증가": [
        "인구 증가",
        "인구 유입",
        "전입 증가",
        "세대수 증가",
        "인구 늘",
    ],
    "교통개발": [
        "GTX",
        "지하철 개통",
        "지하철 신설",
        "경전철",
        "KTX 정차",
        "트램",
        "철도 개통",
        "신규 도로",
        "도로 개설",
        "고속도로 개통",
        "역 신설",
    ],
    "개발사업": [
        "신도시",
        "산업단지",
        "혁신도시",
        "택지지구",
        "공공주택지구",
        "도시개발",
    ],
}


def _city_variants(name: str) -> list[str]:
    """'수원시' → ['수원시', '수원'] 처럼 단축 변형 반환."""
    variants = [name]
    for suffix in ("특별시", "광역시", "특별자치시", "특별자치도", "시", "군", "구"):
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            short = name[: -len(suffix)]
            if short not in variants:
                variants.append(short)
            break
    # 세종특별자치시 → 세종시, 세종 둘 다
    if name == "세종시":
        if "세종" not in variants:
            variants.append("세종")
    return variants


def fetch_dev_news_recent(months: int = 12) -> list[dict]:
    """모든 도시 × 카테고리 쿼리로 검색 → 도시별 결과 반환."""
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
        # 검색 쿼리에는 풀네임(variants[0]) 사용 — 단축명은 노이즈 유발
        search_name = variants[0]

        for category, queries in SEARCH_GROUPS.items():
            for q in queries:
                query = f"{search_name} {q}"
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
                    log.warning("네이버 뉴스 호출 실패 [%s/%s]: %s", city.name, q, e)
                    continue

                for it in items:
                    url = it.get("originallink") or it.get("link") or ""
                    if not url or url in seen_urls:
                        continue

                    title = _strip_tags(it.get("title", ""))
                    desc  = _strip_tags(it.get("description", ""))

                    # ① 제목에 도시명(또는 단축명) 중 하나가 포함되어야
                    #    (본문은 검색 스니펫이라 불완전 — 제목 기준이 더 정확)
                    if not any(v in title for v in variants):
                        # 제목에 없으면 본문(설명)까지 확인
                        if not any(v in desc for v in variants):
                            continue

                    # ② 제목이 너무 짧으면 노이즈
                    if len(title) < 8:
                        continue

                    # ③ 날짜 필터
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
                            # 카테고리를 첫 토큰으로 저장 (앱에서 분류에 사용)
                            "keyword_hits": category,
                        }
                    )

    log.info("네이버 뉴스 수집 완료: 총 %d건", len(out))
    return out


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return (
        _TAG_RE.sub("", s or "")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .strip()
    )


def _parse_pubdate(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
