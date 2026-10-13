"""도시별 종합 분석 보고서 PDF 생성 모듈.

ReportLab을 사용하여 한글 폰트(HYGothic-Medium) 기반의
수요, 공급, 현 상황, 결론 종합 분석 PDF를 생성합니다.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

# ReportLab 라이브러리 가용 여부 확인
HAS_REPORTLAB = False
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        HRFlowable,
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    # 한글 CID 폰트 등록
    FONT_NAME = "HYGothic-Medium"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
    except Exception:
        FONT_NAME = "Helvetica"
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def _fmt_rate(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.2f}%"


def _fmt_num(v: int | float | None) -> str:
    if v is None:
        return "—"
    return f"{int(v):,}세대" if isinstance(v, (int, float)) else str(v)


def generate_city_pdf(
    city_obj: Any,
    sig: dict | None,
    pop_data: list[dict],
    news_data: list[dict],
    unsold_data: list[dict],
    supply_data: list[dict],
    sub_data: list[dict],
    price_data: list[dict],
) -> bytes:
    """도시의 수요, 공급, 현상황, 결론을 포함하는 종합 PDF 바이너리 반환."""
    if not HAS_REPORTLAB:
        # reportlab 이 설치되지 않았거나 설치 중일 때 None 반환
        return b""

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "PDFTitle",
        fontName=FONT_NAME,
        fontSize=20,
        leading=26,
        textColor=colors.HexColor("#1A252F"),
        alignment=0,
    )
    
    h1_style = ParagraphStyle(
        "PDFH1",
        fontName=FONT_NAME,
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#2C3E50"),
        spaceBefore=10,
        spaceAfter=4,
    )

    body_style = ParagraphStyle(
        "PDFBody",
        fontName=FONT_NAME,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#333333"),
    )

    small_style = ParagraphStyle(
        "PDFSmall",
        fontName=FONT_NAME,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#7F8C8D"),
    )

    tbl_header_style = ParagraphStyle(
        "PDFTblHeader",
        fontName=FONT_NAME,
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=1,
    )

    tbl_cell_style = ParagraphStyle(
        "PDFTblCell",
        fontName=FONT_NAME,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#2C3E50"),
        alignment=1,
    )

    tbl_cell_left = ParagraphStyle(
        "PDFTblCellLeft",
        fontName=FONT_NAME,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#2C3E50"),
        alignment=0,
    )

    story = []

    # ── 1. 헤더 & 종합 판정 요약 ─────────────────────────────────
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    header_tbl_data = [
        [
            Paragraph(f"<b>{city_obj.sido} {city_obj.name} 부동산 종합 분석 보고서</b>", title_style),
            Paragraph(f"발행일시: {now_str}<br/>인구수: {city_obj.population:,}명", small_style),
        ]
    ]
    t_head = Table(header_tbl_data, colWidths=[120 * mm, 60 * mm])
    t_head.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    story.append(t_head)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2980B9"), spaceAfter=5 * mm))

    # 종합 판정 결과 배지 & 테이블
    score = int(sig.get("total_score", 0)) if sig else 0
    is_hot = bool(sig.get("is_hotspot", 0)) if sig else False
    status_label = "🔥 활황 예상 지역 (적극 검토)" if is_hot else ("👀 유망 관찰 지역" if score >= 2 else "❄️ 관망/주의 지역")
    status_color = colors.HexColor("#E74C3C") if is_hot else (colors.HexColor("#F39C12") if score >= 2 else colors.HexColor("#7F8C8D"))

    summary_box_data = [
        [
            Paragraph(f"<b>종합 투자 판정: <font color='{status_color.hexval()}'>{status_label}</font> (신호 충족 {score} / 4개)</b>", h1_style),
        ],
        [
            Paragraph(
                f"• 수요 증가: {'✅ 충족' if sig and sig.get('demand_up') else '❌ 미충족'}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                f"• 미분양 감소: {'✅ 충족' if sig and sig.get('unsold_down') else '❌ 미충족'}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                f"• 청약 경쟁 활발: {'✅ 충족' if sig and sig.get('subscription_hot') else '❌ 미충족'}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                f"• 가격 상승(필수): {'✅ 충족' if sig and sig.get('price_up') else '❌ 미충족'}",
                body_style
            )
        ]
    ]
    t_sum = Table(summary_box_data, colWidths=[180 * mm])
    t_sum.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8F9FA")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BDC3C7")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_sum)
    story.append(Spacer(1, 4 * mm))

    # ── 2. [수요 분석] ──────────────────────────────────────────
    story.append(Paragraph("<b>1. 수요 분석 (인구·세대수 및 개발 호재)</b>", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#BDC3C7"), spaceAfter=3 * mm))
    
    # 최근 6개월 인구·세대수 표
    pop_sorted = sorted(pop_data, key=lambda x: x.get("ym", ""), reverse=True)[:6]
    if pop_sorted:
        p_rows = [[
            Paragraph("연월", tbl_header_style),
            Paragraph("인구수(명)", tbl_header_style),
            Paragraph("세대수", tbl_header_style),
            Paragraph("전년비 증감률", tbl_header_style)
        ]]
        detail = sig.get("detail", {}) if sig else {}
        hh_growth = detail.get("household_growth")
        for i, r in enumerate(pop_sorted):
            growth_str = _fmt_rate(hh_growth) if i == 0 else "—"
            p_rows.append([
                Paragraph(f"{r['ym'][:4]}.{r['ym'][4:]}", tbl_cell_style),
                Paragraph(f"{r.get('population', 0):,}명" if r.get('population') else "—", tbl_cell_style),
                Paragraph(f"{r.get('households', 0):,}세대" if r.get('households') else "—", tbl_cell_style),
                Paragraph(growth_str, tbl_cell_style),
            ])
        t_pop = Table(p_rows, colWidths=[40 * mm, 45 * mm, 45 * mm, 50 * mm])
        t_pop.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#34495E")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E0E0E0")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#FDFDFD")]),
            ('PADDING', (0,0), (-1,-1), 3.5),
        ]))
        story.append(t_pop)
    else:
        story.append(Paragraph("수집된 인구/세대수 데이터가 없습니다.", body_style))

    story.append(Spacer(1, 2 * mm))

    # 주요 개발 뉴스 (최대 4건)
    if news_data:
        story.append(Paragraph("<b>주요 개발 및 기업유치 뉴스 (최근 12개월)</b>", body_style))
        for n in news_data[:4]:
            pub = (n.get("published_at") or "")[:10]
            title = n.get("title", "").replace("<b>", "").replace("</b>", "").replace("&quot;", "\"")
            cat = (n.get("keyword_hits") or "개발사업").split(",")[0]
            story.append(Paragraph(f"• <b>[{cat}]</b> {title} <font color='#7F8C8D'>({pub})</font>", small_style))
    story.append(Spacer(1, 4 * mm))

    # ── 3. [공급 분석] ──────────────────────────────────────────
    story.append(Paragraph("<b>2. 공급 분석 (미분양 현황 및 향후 입주물량)</b>", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#BDC3C7"), spaceAfter=3 * mm))

    # 미분양 최근 6개월 표
    unsold_sorted = sorted(unsold_data, key=lambda x: x.get("ym", ""), reverse=True)[:6]
    if unsold_sorted:
        u_rows = [[
            Paragraph("연월", tbl_header_style),
            Paragraph("미분양 합계", tbl_header_style),
            Paragraph("준공후 미분양", tbl_header_style),
            Paragraph("추세 평가", tbl_header_style)
        ]]
        u_slope = detail.get("unsold_slope") if sig else None
        slope_str = f"월평균 {u_slope:+.1f}세대" if u_slope is not None else "—"
        for i, r in enumerate(unsold_sorted):
            total_u = r.get("before_completion") or 0
            after_u = r.get("after_completion")
            after_str = f"{after_u:,}호" if after_u is not None else "—"
            u_rows.append([
                Paragraph(f"{r['ym'][:4]}.{r['ym'][4:]}", tbl_cell_style),
                Paragraph(f"{total_u:,}호", tbl_cell_style),
                Paragraph(after_str, tbl_cell_style),
                Paragraph(slope_str if i == 0 else "—", tbl_cell_style),
            ])
        t_unsold = Table(u_rows, colWidths=[40 * mm, 45 * mm, 45 * mm, 50 * mm])
        t_unsold.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E67E22")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E0E0E0")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#FDFDFD")]),
            ('PADDING', (0,0), (-1,-1), 3.5),
        ]))
        story.append(t_unsold)
    else:
        story.append(Paragraph("수집된 미분양 주택 통계 데이터가 없습니다.", body_style))

    story.append(Spacer(1, 2 * mm))

    # 연도별 공급 실적/예정 물량
    if supply_data:
        s_rows = [[
            Paragraph("연도", tbl_header_style),
            Paragraph("준공 실적(세대)", tbl_header_style),
            Paragraph("입주 예정(세대)", tbl_header_style),
            Paragraph("총 합계(세대)", tbl_header_style)
        ]]
        for r in sorted(supply_data, key=lambda x: x.get("year", 0)):
            c_u = r.get("completed_units") or 0
            p_u = r.get("planned_units") or 0
            s_rows.append([
                Paragraph(f"{r['year']}년", tbl_cell_style),
                Paragraph(f"{c_u:,}", tbl_cell_style),
                Paragraph(f"{p_u:,}", tbl_cell_style),
                Paragraph(f"{c_u + p_u:,}", tbl_cell_style),
            ])
        t_sup = Table(s_rows, colWidths=[40 * mm, 45 * mm, 45 * mm, 50 * mm])
        t_sup.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2980B9")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E0E0E0")),
            ('PADDING', (0,0), (-1,-1), 3.5),
        ]))
        story.append(t_sup)
    else:
        story.append(Paragraph("💡 최근 분석 기간 내 한국부동산원 청약홈에 등록된 신규 분양/입주물량이 없는 지역입니다 (공급 0세대).", body_style))

    story.append(Spacer(1, 4 * mm))

    # ── 4. [현 상황 분석] ────────────────────────────────────────
    story.append(Paragraph("<b>3. 현 상황 분석 (청약 경쟁률 및 가격지수 동향)</b>", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#BDC3C7"), spaceAfter=3 * mm))

    # 최근 청약 단지 (최대 3건)
    if sub_data:
        sub_rows = [[
            Paragraph("공고일", tbl_header_style),
            Paragraph("단지명", tbl_header_style),
            Paragraph("공급세대", tbl_header_style),
            Paragraph("경쟁률", tbl_header_style)
        ]]
        for r in sorted(sub_data, key=lambda x: x.get("announce_date", ""), reverse=True)[:3]:
            rate = r.get("competition_rate")
            rate_str = f"{rate:.2f} : 1" if rate is not None else "—"
            sub_rows.append([
                Paragraph(str(r.get("announce_date", "")), tbl_cell_style),
                Paragraph(str(r.get("complex_name", "")), tbl_cell_left),
                Paragraph(f"{r.get('supply_units', 0):,}세대", tbl_cell_style),
                Paragraph(rate_str, tbl_cell_style),
            ])
        t_sub = Table(sub_rows, colWidths=[35 * mm, 80 * mm, 30 * mm, 35 * mm])
        t_sub.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#27AE60")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E0E0E0")),
            ('PADDING', (0,0), (-1,-1), 3.5),
        ]))
        story.append(t_sub)
    else:
        story.append(Paragraph("💡 최근 6개월 내 진행된 아파트 청약 접수 건이 없습니다.", body_style))

    story.append(Spacer(1, 2 * mm))

    # 최근 6개월 가격지수
    price_sorted = sorted(price_data, key=lambda x: x.get("ym", ""), reverse=True)[:6]
    if price_sorted:
        pr_rows = [[
            Paragraph("연월", tbl_header_style),
            Paragraph("매매가격지수", tbl_header_style),
            Paragraph("전세가격지수", tbl_header_style),
            Paragraph("전년동기대비(매매)", tbl_header_style)
        ]]
        sale_yoy = detail.get("sale_yoy") if sig else None
        for i, r in enumerate(price_sorted):
            s_idx = r.get("sale_index")
            j_idx = r.get("jeonse_index")
            pr_rows.append([
                Paragraph(f"{r['ym'][:4]}.{r['ym'][4:]}", tbl_cell_style),
                Paragraph(f"{s_idx:.2f}" if s_idx else "—", tbl_cell_style),
                Paragraph(f"{j_idx:.2f}" if j_idx else "—", tbl_cell_style),
                Paragraph(_fmt_rate(sale_yoy) if i == 0 else "—", tbl_cell_style),
            ])
        t_pr = Table(pr_rows, colWidths=[40 * mm, 45 * mm, 45 * mm, 50 * mm])
        t_pr.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#C0392B")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E0E0E0")),
            ('PADDING', (0,0), (-1,-1), 3.5),
        ]))
        story.append(t_pr)
    else:
        story.append(Paragraph("수집된 가격지수 통계가 없습니다.", body_style))

    story.append(Spacer(1, 4 * mm))

    # ── 5. [결론 및 원천 근거] ────────────────────────────────────
    story.append(Paragraph("<b>4. 종합 투자 판정 및 데이터 원천 안내</b>", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#BDC3C7"), spaceAfter=3 * mm))
    
    conclusion_text = (
        f"<b>{city_obj.name}</b> 지역은 4대 핵심 투자 신호 중 <b>{score}개 신호를 충족</b>하고 있습니다. "
        f"가격 상승 지속성 및 미분양 소진 추이를 바탕으로 시장 타이밍을 검토하시기 바랍니다.<br/><br/>"
        f"<b>공식 공공데이터 출처 안내:</b><br/>"
        f"• 인구/세대수: 통계청 KOSIS 행정안전부 주민등록인구통계 (DT_1B040A3, DT_1B040B3)<br/>"
        f"• 미분양/가격지수: 국토교통부 · 한국부동산원 부동산통계정보시스템 R-One (T237973129847263, A_2024_00045)<br/>"
        f"• 공급/청약경쟁률: 한국부동산원 청약홈 공공데이터포털 OpenAPI"
    )
    t_concl = Table([[Paragraph(conclusion_text, body_style)]], colWidths=[180 * mm])
    t_concl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F4F6F6")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BDC3C7")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_concl)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
