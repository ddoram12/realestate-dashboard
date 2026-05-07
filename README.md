# 전국 부동산 시장 분석 대시보드

인구 10만 이상 전국 도시(약 85개)의 부동산 시장 상황을 4개 지표로 자동 평가하는 Streamlit 대시보드.

---

## 주요 기능

| 항목 | 내용 |
|------|------|
| **수요** | 인구·세대수 증감 추이 (KOSIS), 대규모 개발·기업유치 뉴스 (네이버) |
| **공급** | 최근 1년 미분양 추이(준공 전/후 구분), 최근 3년 공급 실적 + 향후 3년 예정 |
| **현 상황** | 최근 6개월 청약 경쟁률(단지별), 최근 2년 매매·전세 가격지수 |
| **활황 판정** | 4개 신호 중 3개 이상 충족 → 🔥 활황 예상지역 자동 분류 |

---

## 설치 및 실행

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. API 키 설정
```bash
cp .env.example .env
# .env 파일을 열어 각 API 키 입력 (아래 발급 절차 참고)
```

### 3. 데이터 수집
```bash
# 전체 수집 (최초 1회 / 이후 주기적으로)
python scripts/refresh_data.py --all

# 특정 항목만
python scripts/refresh_data.py --population --unsold --price
python scripts/refresh_data.py --score           # 신호 재계산만
```

### 4. 대시보드 실행
```bash
streamlit run app/Home.py
```

---

## API 키 발급 절차

### ① KOSIS (통계청) — 인구·세대수
> 호출 한도 없음 · 자동 승인

1. [https://kosis.kr/openapi/](https://kosis.kr/openapi/) 접속
2. 상단 **회원가입 / 로그인** 후 **"인증키 신청"** 클릭
3. 인증 목적 입력(예: "부동산 시장 분석 연구") → 자동 승인
4. 발급된 **인증키(API Key)** 를 `.env` 의 `KOSIS_API_KEY=` 에 입력
5. **추가 활용 신청** : [주민등록 인구현황 (조직 101 / 통계표 DT_1B040A3)](https://kosis.kr/) — 좌측 통계표 검색에서 "주민등록 인구 시군구" 입력 후 활용 신청

---

### ② 한국부동산원 R-One — 미분양·가격지수·입주예정
> 무료 · 승인 1~3일

1. [https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do](https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do) 접속
2. **회원가입** 후 로그인 → **Open API 목록** → 필요 통계표 활용 신청
3. 필수 신청 통계표:
   - 미분양 주택 현황 (시군구별)
   - 주택가격동향 — 시군구별 매매·전세가격지수
   - 주택공급정보 — 입주예정물량
4. 승인 후 마이페이지에서 **KEY** 확인 → `.env` 의 `REB_API_KEY=` 입력
5. 승인된 **통계표 ID** 가 기본값과 다른 경우 `config/settings.py` 의 `REB_STATS` 딕셔너리 수정

> 💡 R-One 개발가이드: [https://www.reb.or.kr/r-one/portal/openapi/openApiDevPage.do](https://www.reb.or.kr/r-one/portal/openapi/openApiDevPage.do)

---

### ③ 공공데이터포털 — 실거래가·청약경쟁률·입주예정
> 무료 · 자동 승인

1. [https://www.data.go.kr/](https://www.data.go.kr/) 접속 → 회원가입 후 로그인
2. 아래 3개 API 검색 후 각각 **활용 신청** (자동 승인):
   - `국토교통부_아파트매매 실거래가 자료` (ID: 15126469)
   - `한국부동산원_청약홈 청약접수 경쟁률 및 특별공급 신청현황 조회 서비스` (ID: 15098905)
   - `한국부동산원_주택공급정보_입주예정물량정보` (ID: 15111714)
3. 마이페이지 → **일반 인증키(Decoding)** 복사 → `.env` 의 `DATA_GO_KR_API_KEY=` 입력

> ⚠️ URL 인코딩된 키(Encoding key)가 아닌 **Decoding key** 를 사용하세요.

---

### ④ 네이버 검색 API — 개발사업 뉴스 (선택)
> 무료 (일 25,000 호출) · 자동 승인

1. [https://developers.naver.com/apps/](https://developers.naver.com/apps/) 접속 → 로그인
2. **애플리케이션 등록** → 사용 API: **검색** 선택
3. 등록 후 **Client ID** 와 **Client Secret** 확인
4. `.env` 의 `NAVER_CLIENT_ID=` / `NAVER_CLIENT_SECRET=` 에 입력

> 네이버 API 없이도 인구·미분양·청약·가격지수 4개 신호는 모두 동작합니다.

---

## 데이터 갱신 주기 권장

| 데이터 | 권장 주기 | 명령어 |
|--------|---------|--------|
| 인구·세대수 | 월 1회 | `--population` |
| 미분양 | 월 1회 | `--unsold` |
| 가격지수 | 월 1회 | `--price` |
| 입주예정물량 | 분기 1회 | `--supply` |
| 청약 경쟁률 | 주 1회 | `--subscription` |
| 개발사업 뉴스 | 주 1회 | `--news` |
| 신호 재계산 | 위 수집 후 | `--score` |

---

## 디렉토리 구조

```
부동산 시장 분석/
├── app/
│   ├── Home.py                  # 메인 대시보드 (활황 예상지역)
│   ├── utils.py                 # 공통 유틸
│   └── pages/
│       └── 1_도시별_상세.py     # 도시별 4개 탭 상세 분석
├── config/
│   ├── cities.py                # 인구 10만+ 도시 85개 시드
│   └── settings.py              # API 엔드포인트·임계값·기간 설정
├── src/
│   ├── api_clients/             # API 클라이언트 (KOSIS·R-One·MOLIT·청약홈·네이버)
│   ├── analysis/                # 신호 계산 (demand·supply·current·score)
│   └── storage/                 # SQLite 스키마·upsert
├── scripts/
│   └── refresh_data.py          # 데이터 갱신 CLI
└── data/
    └── realestate.db            # SQLite 캐시 (자동 생성)
```

---

## 활황 판정 기준 조정

`config/settings.py` 의 `Thresholds` 클래스 값을 변경하면 됩니다:

```python
class Thresholds:
    HOUSEHOLD_GROWTH_MIN = 0.0    # 세대수 증가 기준 (0 = 양(+)이면 충족)
    DEV_NEWS_MIN_COUNT   = 3      # 개발뉴스 최소 건수
    UNSOLD_TREND_WINDOW_MONTHS = 6
    SUBSCRIPTION_AVG_MIN = 1.0   # 청약 경쟁률 기준
    PRICE_GROWTH_MIN     = 0.0   # 가격 상승 기준
    HOTSPOT_SIGNAL_MIN   = 3     # 활황 판정 최소 신호 수
```

변경 후 `python scripts/refresh_data.py --score` 로 재계산.
