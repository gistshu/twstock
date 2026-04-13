from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import re
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlparse

from twstock_mvp.data import (
    DataFetchError,
    DatasetBundle,
    StockDayResponse,
    current_report_date,
    fetch_bwibbu_by_date,
    fetch_margin_by_date,
    fetch_news_list,
    fetch_recent_stock_history,
    load_sample_bwibbu_by_date,
    load_sample_recent_stock_history,
    load_sample_datasets,
    load_live_datasets,
)
from twstock_mvp.watchlist import WatchlistRow, build_watchlist, build_watchlist_index


ETF_TOP_HOLDINGS: dict[str, list[tuple[str, float]]] = {
    "0050": [("2330", 57.0), ("2317", 5.2), ("2454", 4.6), ("2881", 3.2), ("2308", 2.9)],
    "0056": [("2881", 4.8), ("2882", 4.5), ("2603", 4.1), ("1301", 3.7), ("2317", 3.5)],
    "00878": [("2881", 4.9), ("2882", 4.6), ("2603", 3.9), ("1301", 3.6), ("2317", 3.4)],
}


def format_value(value: float, suffix: str = "") -> str:
    if not value:
        return "-"
    return f"{value:.2f}{suffix}"


def format_int(value: float) -> str:
    if not value:
        return "-"
    return f"{value:,.0f}"


def score_class(score: int) -> str:
    if score >= 70:
        return "bullish"
    if score >= 40:
        return "neutral"
    return "bearish"


def normalize_codes(raw_codes: list[str], fallback_codes: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in raw_codes:
        for code in item.replace("，", ",").split(","):
            value = code.strip()
            if value and value not in cleaned:
                cleaned.append(value)
    return cleaned or fallback_codes


def parse_codes_cookie(raw_cookie: str) -> list[str]:
    if not raw_cookie:
        return []
    cookie = SimpleCookie()
    try:
        cookie.load(raw_cookie)
    except Exception:
        return []
    morsel = cookie.get("watch_codes")
    if morsel is None:
        return []
    return normalize_codes([unquote_plus(morsel.value)], [])


def build_codes_cookie(codes: list[str]) -> str:
    return f"watch_codes={quote_plus(','.join(codes))}; Path=/; Max-Age=2592000; SameSite=Lax"


def build_query(source: str, codes: list[str], selected_code: str = "") -> str:
    code_param = f"&code={quote_plus(selected_code)}" if selected_code else ""
    return f"/?source={quote_plus(source)}&codes={quote_plus(','.join(codes))}{code_param}"


def to_number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").strip())
    except ValueError:
        return None


def latest_price_and_volume(history: StockDayResponse | None) -> tuple[float, float]:
    if history is None:
        return 0.0, 0.0
    for record in reversed(history.records):
        close = to_number(record.close_price)
        volume = to_number(record.volume)
        if close is not None:
            return close, volume or 0.0
    return 0.0, 0.0


def latest_price_volume_date(history: StockDayResponse | None) -> tuple[str, float, float]:
    if history is None:
        return "-", 0.0, 0.0
    for record in reversed(history.records):
        close = to_number(record.close_price)
        volume = to_number(record.volume)
        if close is not None:
            return record.date, close, volume or 0.0
    return "-", 0.0, 0.0


def day_of_month(date_text: str) -> str:
    cleaned = date_text.strip().replace("-", "/")
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) >= 3 and parts[-1].isdigit():
        return f"{int(parts[-1]):02d}"
    match = re.search(r"(\d{2})$", cleaned)
    if match:
        return match.group(1)
    return "--"


def price_volume_pairs(history: StockDayResponse | None, limit: int) -> list[tuple[str, float, float]]:
    if history is None:
        return []
    pairs: list[tuple[str, float, float]] = []
    for record in history.records[-limit:]:
        close = to_number(record.close_price)
        volume = to_number(record.volume)
        if close is None:
            continue
        pairs.append((record.date, close, volume or 0.0))
    return pairs


def render_7day_price_volume(history: StockDayResponse | None) -> str:
    pairs = price_volume_pairs(history, limit=7)
    if not pairs:
        return '<span class="tiny-note">資料不足</span>'

    chips: list[str] = []
    for index in range(len(pairs)):
        date, close, volume = pairs[index]
        prev_close = pairs[index - 1][1] if index > 0 else close
        prev_volume = pairs[index - 1][2] if index > 0 else volume
        delta = close - prev_close if index > 0 else 0.0
        pct = (delta / prev_close * 100) if prev_close and index > 0 else 0.0
        css = "up" if delta > 0 else "down" if delta < 0 else "flat"
        vol_css = "up" if volume > prev_volume else "down" if volume < prev_volume else "flat"
        chips.append(
            f'<span class="pv-chip {css}" title="{escape(date)}">'
            f'<small>{day_of_month(date)}</small>'
            f'<b>價 {close:.2f}</b>'
            f'<i>{delta:+.2f} ({pct:+.2f}%)</i>'
            f'<em class="{vol_css}">量 {volume/1000:.1f}K</em>'
            f"</span>"
        )
    return '<div class="pv-strip">' + "".join(chips) + "</div>"


def margin_row_code(row: dict[str, str]) -> str:
    for key in ("股票代號", "證券代號", "Code"):
        value = row.get(key, "").strip()
        if value:
            return value
    return ""


def margin_today_value(row: dict[str, str], margin: bool) -> float:
    keys = ("今日融資餘額", "融資今日餘額", "融資餘額") if margin else ("今日融券餘額", "融券今日餘額", "融券餘額")
    for key in keys:
        value = row.get(key, "")
        parsed = to_number(value)
        if parsed is not None:
            return parsed
    return 0.0


def generate_sample_margin_series(today: float, yesterday: float, short_today: float, short_yesterday: float) -> list[tuple[str, float, float]]:
    margin_delta = today - yesterday
    short_delta = short_today - short_yesterday
    series: list[tuple[str, float, float]] = []
    now = datetime.now()
    baseline_margin = max(today - margin_delta * 3.5, 0.0)
    baseline_short = max(short_today - short_delta * 3.5, 0.0)
    for idx in range(7):
        date = (now - timedelta(days=6 - idx)).strftime("%m/%d")
        wobble = ((idx % 3) - 1) * 0.25
        margin_value = max(baseline_margin + margin_delta * idx + margin_delta * wobble, 0.0)
        short_value = max(baseline_short + short_delta * idx - short_delta * wobble, 0.0)
        series.append((date, margin_value, short_value))
    return series


def load_margin_series(source: str, rows: list[WatchlistRow], codes: list[str]) -> tuple[dict[str, list[tuple[str, float, float]]], str]:
    series_map: dict[str, list[tuple[str, float, float]]] = {code: [] for code in codes}

    if source == "sample":
        index = build_watchlist_index(rows)
        for code in codes:
            row = index.get(code)
            if row is None:
                continue
            snapshot = row.snapshot
            series_map[code] = generate_sample_margin_series(
                today=snapshot.margin_balance_today,
                yesterday=snapshot.margin_balance_yesterday,
                short_today=snapshot.short_balance_today,
                short_yesterday=snapshot.short_balance_yesterday,
            )
        return series_map, ""

    errors: list[str] = []
    for offset in range(16):
        date = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
        try:
            day_rows = fetch_margin_by_date(date)
        except DataFetchError:
            continue

        day_by_code: dict[str, tuple[float, float]] = {}
        for day_row in day_rows:
            code = margin_row_code(day_row)
            if not code or code not in series_map:
                continue
            day_by_code[code] = (
                margin_today_value(day_row, margin=True),
                margin_today_value(day_row, margin=False),
            )

        for code in codes:
            value_pair = day_by_code.get(code)
            if value_pair is None or len(series_map[code]) >= 7:
                continue
            series_map[code].append((date[4:6] + "/" + date[6:8], value_pair[0], value_pair[1]))

        if all(len(series_map[code]) >= 7 for code in codes):
            break

    for code in codes:
        if series_map[code]:
            latest_first = series_map[code][:7]
            series_map[code] = list(reversed(latest_first))

    incomplete = [code for code, data in series_map.items() if len(data) < 2]
    if incomplete:
        errors.append(f"融資融券近 7 日資料不足: {','.join(incomplete[:4])}")

    if not any(series_map.values()):
        errors.append("Live 融資融券資料無法完整取得，欄位以 -- 顯示")

    return series_map, "；".join(errors)


def render_7day_margin_short(series: list[tuple[str, float, float]]) -> str:
    if len(series) < 2:
        return '<span class="tiny-note">資料不足</span>'

    chips: list[str] = []
    for index in range(1, len(series)):
        date, margin, short = series[index]
        _, prev_margin, prev_short = series[index - 1]
        margin_delta = margin - prev_margin
        short_delta = short - prev_short
        margin_css = "up" if margin_delta > 0 else "down" if margin_delta < 0 else "flat"
        short_css = "up" if short_delta > 0 else "down" if short_delta < 0 else "flat"
        chips.append(
            f'<span class="ms-chip" title="{escape(date)}">'
            f'<b class="{margin_css}">資 {margin_delta:+.0f}</b>'
            f'<em class="{short_css}">券 {short_delta:+.0f}</em>'
            f"</span>"
        )
    return '<div class="ms-strip">' + "".join(chips) + "</div>"


def growth_estimate(row: WatchlistRow, history: StockDayResponse | None) -> float:
    pairs = price_volume_pairs(history, limit=7)
    if len(pairs) >= 2 and pairs[0][1]:
        seven_day_pct = (pairs[-1][1] - pairs[0][1]) / pairs[0][1] * 100
    else:
        seven_day_pct = 0.0
    estimate = (row.trend.score - 50) * 0.28 + seven_day_pct * 0.6
    return max(-20.0, min(20.0, estimate))


def pick_news_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key, "").strip()
        if value:
            return value
    return ""


def parse_news_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None

    date_part = text.split(" ")[0].replace("-", "/")
    chunks = [chunk for chunk in date_part.split("/") if chunk]
    if len(chunks) < 3:
        digits = re.sub(r"[^\d]", "", text)
        if len(digits) >= 8:
            try:
                return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
            except ValueError:
                return None
        return None

    try:
        year = int(chunks[0])
        month = int(chunks[1])
        day = int(chunks[2])
    except ValueError:
        return None

    if year < 1911:
        year += 1911
    try:
        return date(year, month, day)
    except ValueError:
        return None


def load_stock_news(source: str, code: str, fallback_messages: list[str]) -> tuple[list[tuple[str, str, str]], str]:
    if not code:
        return [], ""

    if source == "sample":
        sample_rows = [(f"示範資料 #{idx + 1}", message, "") for idx, message in enumerate(fallback_messages[:8])]
        return sample_rows, ""

    try:
        rows = fetch_news_list(stock_no=code, page=1)
        news_items: list[tuple[str, str, str]] = []
        today = datetime.now().date()
        cutoff = today - timedelta(days=2)
        for row in rows:
            date_text = pick_news_value(row, "發言日期", "Date", "date", "發表日期", "公告日期")
            title = pick_news_value(row, "標題", "title", "主旨", "摘要", "Headline")
            link = pick_news_value(row, "連結", "link", "url", "Url")
            parsed_date = parse_news_date(date_text)
            if parsed_date is not None and parsed_date < cutoff:
                continue
            if title:
                news_items.append((date_text or "最新", title, link))
            if len(news_items) >= 8:
                break
        if news_items:
            return news_items, ""
        raise DataFetchError("news/newsList 近三天查無資料")
    except Exception as exc:
        if fallback_messages:
            sample_rows = [(f"重大訊息 #{idx + 1}", message, "") for idx, message in enumerate(fallback_messages[:8])]
            return sample_rows, f"新聞 API 讀取失敗，改用重大訊息。原因: {exc}"
        return [], f"新聞 API 讀取失敗。原因: {exc}"


def moving_average(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = []
    for idx in range(len(values)):
        if idx + 1 < window:
            result.append(None)
            continue
        chunk = values[idx + 1 - window : idx + 1]
        result.append(sum(chunk) / window)
    return result


def render_30day_chart(history: StockDayResponse | None, title: str) -> str:
    pairs = price_volume_pairs(history, limit=30)
    if len(pairs) < 2:
        return '<div class="empty-panel">30 天技術線資料不足</div>'

    prices = [item[1] for item in pairs]
    volumes = [item[2] for item in pairs]
    ma5 = moving_average(prices, 5)
    ma20 = moving_average(prices, 20)

    width = 860
    height = 340
    left = 36
    right = width - 12
    top = 14
    mid = 232
    bottom = height - 26

    low_price = min(prices)
    high_price = max(prices)
    axis_low = float(int(low_price))
    axis_high = float(int(high_price) if float(int(high_price)) == high_price else int(high_price) + 1)
    if axis_high <= axis_low:
        axis_high = axis_low + 1
    price_span = max(axis_high - axis_low, 1.0)
    max_volume = max(max(volumes), 1.0)
    min_volume = min(volumes)

    def point_x(index: int) -> float:
        return left + (right - left) * index / max(len(prices) - 1, 1)

    def price_y(value: float) -> float:
        return mid - ((value - axis_low) / price_span) * (mid - top)

    def volume_y(value: float) -> float:
        return bottom - (value / max_volume) * (bottom - mid - 6)

    close_points: list[str] = []
    ma5_points: list[str] = []
    ma20_points: list[str] = []
    volume_rects: list[str] = []
    hover_points: list[str] = []

    bar_width = max((right - left) / max(len(prices), 1) * 0.58, 3.0)
    price_ticks = list(range(int(axis_low), int(axis_high) + 1))
    if len(price_ticks) > 28:
        step = max((len(price_ticks) // 14), 1)
        price_ticks = [tick for index, tick in enumerate(price_ticks) if index % step == 0 or tick in {int(axis_low), int(axis_high)}]
    date_tick_indices = sorted({0, len(pairs) // 4, len(pairs) // 2, (len(pairs) * 3) // 4, len(pairs) - 1})

    for idx, (date, close, volume) in enumerate(pairs):
        x = point_x(idx)
        y = price_y(close)
        close_points.append(f"{x:.2f},{y:.2f}")

        if ma5[idx] is not None:
            ma5_points.append(f"{x:.2f},{price_y(ma5[idx] or 0.0):.2f}")
        if ma20[idx] is not None:
            ma20_points.append(f"{x:.2f},{price_y(ma20[idx] or 0.0):.2f}")

        bar_top = volume_y(volume)
        color = "#00d06f"
        if idx > 0:
            prev_close = pairs[idx - 1][1]
            if close > prev_close:
                color = "#ff2a4f"
            elif close < prev_close:
                color = "#00d06f"
            else:
                color = "#9ea4ba"
        volume_rects.append(
            f'<rect x="{x - bar_width/2:.2f}" y="{bar_top:.2f}" width="{bar_width:.2f}" height="{bottom - bar_top:.2f}" fill="{color}" opacity="0.55" />'
        )
        hover_points.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6.2" fill="transparent" stroke="transparent">'
            f"<title>{escape(date)} 收盤 {close:.2f}</title>"
            f"</circle>"
        )

    return f"""
    <div class="chart-wrap">
      <div class="block-title">{escape(title)} 30 天技術線 + 成交量</div>
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="30 天技術線與成交量圖" style="width:100%;height:auto;display:block;">
        {''.join(f'<line x1="{left}" y1="{price_y(float(tick)):.2f}" x2="{right}" y2="{price_y(float(tick)):.2f}" stroke="#1f2638" stroke-width="1" />' for tick in price_ticks)}
        {''.join(f'<text x="4" y="{price_y(float(tick)) + 3:.2f}" fill="#8f98b2" font-size="11">{tick}</text>' for tick in price_ticks)}
        <line x1="{left}" y1="{mid}" x2="{right}" y2="{mid}" stroke="#2a3040" stroke-width="1" />
        <line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#2a3040" stroke-width="1" />
        {''.join(volume_rects)}
        <polyline points="{' '.join(close_points)}" fill="none" stroke="#ffd24a" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
        <polyline points="{' '.join(ma5_points)}" fill="none" stroke="#00d06f" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        <polyline points="{' '.join(ma20_points)}" fill="none" stroke="#55a6ff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        {''.join(hover_points)}
        <text x="{left}" y="{top + 2}" fill="#8f98b2" font-size="12">高 {high_price:.2f}</text>
        <text x="{left}" y="{mid - 4}" fill="#8f98b2" font-size="12">低 {low_price:.2f}</text>
        <text x="{right - 190}" y="{mid + 14}" fill="#8f98b2" font-size="12">量 最大 {max_volume/1000:.1f}K</text>
        <text x="{right - 190}" y="{mid + 30}" fill="#8f98b2" font-size="12">量 最小 {min_volume/1000:.1f}K</text>
        {''.join(f'<text x="{point_x(idx):.2f}" y="{bottom + 14}" fill="#8f98b2" font-size="11" text-anchor="middle">{escape(pairs[idx][0])}</text>' for idx in date_tick_indices)}
      </svg>
      <div class="legend-row">
        <span><i class="l close"></i>收盤價</span>
        <span><i class="l ma5"></i>5MA</span>
        <span><i class="l ma20"></i>20MA</span>
        <span><i class="l vol"></i>成交量</span>
      </div>
    </div>
    """


def pick_row_value(row: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key, "")).strip()
        if value and value != "None":
            return value
    return ""


def build_market_summary(bundle: DatasetBundle) -> tuple[str, float, float, str]:
    preferred_names = ("發行量加權股價指數", "寶島股價指數", "加權股價指數")
    preferred_row: dict[str, object] | None = None
    fallback_row: dict[str, object] | None = None

    for row in bundle.market_index:
        name = pick_row_value(row, "指數", "IndexName", "名稱", "Name")
        if not name:
            continue
        if fallback_row is None:
            fallback_row = row
        if any(target in name for target in preferred_names):
            preferred_row = row
            break

    target_row = preferred_row or fallback_row
    if target_row is not None:
        name = pick_row_value(target_row, "指數", "IndexName", "名稱", "Name")
        index_value = to_number(
            pick_row_value(target_row, "收盤指數", "最新指數", "指數", "指數值", "價格指數")
        )
        pct_value = to_number(pick_row_value(target_row, "漲跌百分比(%)", "漲跌百分比", "報酬率(%)"))
        delta_sign = pick_row_value(target_row, "漲跌")
        delta_raw = to_number(pick_row_value(target_row, "漲跌點數", "漲跌價差", "漲跌"))
        if delta_raw is not None and delta_sign == "-":
            delta_raw = -abs(delta_raw)
        market_name = name or "大盤指數"
        return market_name, index_value or 0.0, pct_value or 0.0, f"{(delta_raw or 0.0):+.2f}"

    for row in bundle.intraday:
        code = pick_row_value(row, "股票代號", "證券代號", "Code")
        name = pick_row_value(row, "股票名稱", "證券名稱", "Name")
        if code not in {"TAIEX", "TSE", "INDEX"} and "加權" not in name:
            continue
        index_value = to_number(
            pick_row_value(row, "發行量加權股價指數", "加權指數", "成交指數", "最新指數", "指數")
        )
        pct_value = to_number(pick_row_value(row, "漲跌百分比(%)", "漲跌百分比", "漲跌幅(%)"))
        delta_value = to_number(pick_row_value(row, "漲跌點數", "漲跌價差", "漲跌"))
        market_name = name or "大盤加權指數"
        return market_name, index_value or 0.0, pct_value or 0.0, f"{delta_value:+.2f}" if delta_value else "-"
    return "大盤加權指數", 0.0, 0.0, "-"


def build_market_hist_pairs(bundle: DatasetBundle) -> list[tuple[str, float]]:
    preferred_names = ("發行量加權股價指數", "寶島股價指數", "加權股價指數")
    pairs: list[tuple[str, float]] = []

    for row in bundle.market_hist:
        name = pick_row_value(row, "Name", "指數", "IndexName", "名稱")
        if name and not any(target in name for target in preferred_names):
            continue
        date_text = pick_row_value(row, "Date", "日期", "date")
        close_val = to_number(pick_row_value(row, "ClosingIndex", "收盤指數", "指數", "最新指數"))
        if not date_text or close_val is None:
            continue
        pairs.append((date_text, close_val))

    pairs.sort(key=lambda item: item[0])
    dedup: dict[str, float] = {}
    for date_text, close_val in pairs:
        dedup[date_text] = close_val
    sorted_pairs = sorted(dedup.items(), key=lambda item: item[0])
    return sorted_pairs[-7:]


def render_7day_market_index(bundle: DatasetBundle) -> str:
    pairs = build_market_hist_pairs(bundle)
    if not pairs:
        return '<span class="tiny-note">大盤近 7 日資料不足</span>'

    chips: list[str] = []
    for idx, (date_text, close_val) in enumerate(pairs):
        prev_close = pairs[idx - 1][1] if idx > 0 else close_val
        delta = close_val - prev_close if idx > 0 else 0.0
        css = "up" if delta > 0 else "down" if delta < 0 else "flat"
        chips.append(
            f'<span class="pv-chip {css}" title="{escape(date_text)}">'
            f'<small>{day_of_month(date_text)}</small>'
            f'<b>指 {close_val:.2f}</b>'
            f'<i>{delta:+.2f}</i>'
            f'<em>較前日</em>'
            f"</span>"
        )
    return '<div class="pv-strip">' + "".join(chips) + "</div>"


def render_score_breakdown(row: WatchlistRow) -> str:
    snapshot = row.snapshot
    base_score = 50
    running_score = base_score

    calc_lines: list[str] = []
    for idx, (delta, reason) in enumerate(row.trend.breakdown, start=1):
        before_score = running_score
        after_score = before_score + delta
        running_score = after_score
        css = "up" if delta > 0 else "down" if delta < 0 else "flat"
        calc_lines.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{before_score:d}</td>"
            f'<td class="{css}">{delta:+d}</td>'
            f"<td>{after_score:d}</td>"
            f"<td>{escape(reason)}</td>"
            "</tr>"
        )

    final_raw = running_score
    final_capped = max(0, min(100, final_raw))
    clamp_note = ""
    if final_raw != final_capped:
        clamp_note = f"（封頂/封底後 {final_capped}）"

    margin_delta = snapshot.margin_balance_today - snapshot.margin_balance_yesterday
    short_delta = snapshot.short_balance_today - snapshot.short_balance_yesterday
    metric_lines = [
        ("收盤價", f"{snapshot.closing_price:.2f}" if snapshot.closing_price else "-"),
        ("月均價", f"{snapshot.monthly_average_price:.2f}" if snapshot.monthly_average_price else "-"),
        ("委買量(5m)", f"{snapshot.buy_volume_5m:,.0f}" if snapshot.buy_volume_5m else "-"),
        ("委賣量(5m)", f"{snapshot.sell_volume_5m:,.0f}" if snapshot.sell_volume_5m else "-"),
        ("本益比", f"{snapshot.pe_ratio:.2f}" if snapshot.pe_ratio else "-"),
        ("殖利率(%)", f"{snapshot.dividend_yield:.2f}" if snapshot.dividend_yield else "-"),
        ("股價淨值比", f"{snapshot.pb_ratio:.2f}" if snapshot.pb_ratio else "-"),
        ("融資增減", f"{margin_delta:+.0f}"),
        ("融券增減", f"{short_delta:+.0f}"),
        ("重大訊息筆數", str(len(snapshot.material_messages))),
        ("異常推介", "是" if snapshot.abnormal_promotion else "否"),
    ]
    metrics_html = "".join(
        f"<tr><td>{escape(name)}</td><td>{escape(value)}</td></tr>"
        for name, value in metric_lines
    )

    return (
        '<div class="news">'
        '<small>評分完整計算數據</small>'
        f'<div class="tiny-note">基準分: {base_score} / 原始最終分: {final_raw} {clamp_note}</div>'
        '<table class="sub-table"><thead><tr><th>步驟</th><th>前分</th><th>變動</th><th>後分</th><th>規則</th></tr></thead>'
        f'<tbody>{"".join(calc_lines)}</tbody></table>'
        '<div style="height:8px"></div>'
        '<table class="sub-table"><thead><tr><th>輸入數據</th><th>數值</th></tr></thead>'
        f"<tbody>{metrics_html}</tbody></table>"
        "</div>"
    )


def build_market_index(bundle: DatasetBundle) -> dict[str, dict[str, object]]:
    market: dict[str, dict[str, object]] = {}

    def get_entry(code: str) -> dict[str, object]:
        if code not in market:
            market[code] = {"code": code, "name": "", "industry": "", "price": 0.0, "volume": 0.0}
        return market[code]

    for row in bundle.day_avg:
        code = pick_row_value(row, "Code", "股票代號", "證券代號")
        if not code:
            continue
        entry = get_entry(code)
        name = pick_row_value(row, "Name", "股票名稱", "證券名稱")
        if name:
            entry["name"] = name
        industry = pick_row_value(row, "產業別", "Industry")
        if industry:
            entry["industry"] = industry
        close_price = to_number(pick_row_value(row, "ClosingPrice", "收盤價"))
        if close_price is not None:
            entry["price"] = close_price

    for row in bundle.industry_info:
        code = pick_row_value(row, "公司代號", "股票代號", "證券代號", "Code")
        if not code:
            continue
        entry = get_entry(code)
        name = pick_row_value(row, "公司簡稱", "股票名稱", "證券名稱", "Name")
        if name:
            entry["name"] = name
        industry = pick_row_value(row, "產業別", "industry", "Industry")
        if industry:
            entry["industry"] = industry

    for row in bundle.intraday:
        code = pick_row_value(row, "股票代號", "證券代號", "Code")
        if not code:
            continue
        entry = get_entry(code)
        buy_qty = to_number(pick_row_value(row, "累積委託買進數量", "買進委託量", "累積買進委託數量")) or 0.0
        sell_qty = to_number(pick_row_value(row, "累積委託賣出數量", "賣出委託量", "累積賣出委託數量")) or 0.0
        entry["volume"] = max(buy_qty + sell_qty, 0.0)

    return market


def is_etf_stock(code: str, industry: str) -> bool:
    if code.startswith("00"):
        return True
    upper = industry.upper()
    return "ETF" in upper or "指數股票" in industry


def build_related_market_stocks(
    selected_code: str,
    bundle: DatasetBundle,
) -> tuple[list[tuple[str, str, float, float, str]], str]:
    market = build_market_index(bundle)
    selected = market.get(selected_code)
    if selected is None:
        return [], "查無所選股票的市場資料"

    selected_industry = str(selected.get("industry", "")).strip()
    if is_etf_stock(selected_code, selected_industry):
        holdings = ETF_TOP_HOLDINGS.get(selected_code, [])
        items: list[tuple[str, str, float, float, str]] = []
        for code, weight in holdings:
            entry = market.get(code)
            if entry is None:
                continue
            items.append(
                (
                    code,
                    str(entry.get("name", "")) or code,
                    float(entry.get("price", 0.0)),
                    float(entry.get("volume", 0.0)),
                    f"權重 {weight:.1f}%",
                )
            )
            if len(items) >= 5:
                break
        return items, "ETF: 前五大成分股（依權重）"

    candidates: list[tuple[float, str, str, float, float]] = []
    for code, entry in market.items():
        if code == selected_code:
            continue
        industry = str(entry.get("industry", "")).strip()
        if selected_industry and industry != selected_industry:
            continue
        if is_etf_stock(code, industry):
            continue
        price = float(entry.get("price", 0.0))
        volume = float(entry.get("volume", 0.0))
        if price <= 0:
            continue
        # 同產業內以流動性為主，成交活躍者優先
        sort_key = volume if volume > 0 else -price
        candidates.append((sort_key, code, str(entry.get("name", "")) or code, price, volume))

    candidates.sort(key=lambda item: item[0], reverse=True)
    top5 = [(code, name, price, volume, selected_industry or "同市場活躍股") for _, code, name, price, volume in candidates[:5]]
    return top5, (f"同產業: {selected_industry}（流動性前五）" if selected_industry else "同市場活躍股前五")


def render_layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #06080f;
      --panel: #0f1320;
      --panel-2: #121a2c;
      --line: #2a3040;
      --ink: #e8ecff;
      --muted: #8f98b2;
      --up: #ff2a4f;
      --down: #00d06f;
      --flat: #9ea4ba;
      --accent: #ffd24a;
      --accent-2: #55a6ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 12%, rgba(40, 56, 102, 0.28), transparent 34%),
        radial-gradient(circle at 85% 5%, rgba(124, 36, 66, 0.20), transparent 28%),
        var(--bg);
      font-family: "Noto Sans TC", "PingFang TC", sans-serif;
      font-size: 16px;
      min-height: 100vh;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .shell {{ width: 100%; max-width: none; margin: 0; padding: 0; }}
    .toolbar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      background: #0b1020;
      border: 1px solid var(--line);
      padding: 10px;
      margin: 0 0 8px;
      border-radius: 0;
    }}
    .toolbar input {{
      flex: 1;
      min-width: 260px;
      border: 1px solid #343b4e;
      background: #090d18;
      color: var(--ink);
      border-radius: 7px;
      padding: 8px 10px;
      font: inherit;
    }}
    .btn {{
      border: 1px solid #39425c;
      background: #12192d;
      color: var(--ink);
      border-radius: 7px;
      padding: 8px 12px;
      font-weight: 700;
      cursor: pointer;
    }}
    .btn.live {{ border-color: #346f4a; }}
    .btn.sample {{ border-color: #6c5c26; }}
    .status {{ color: var(--muted); font-size: 14px; margin-left: auto; }}
    .panel {{
      border: 1px solid var(--line);
      background: linear-gradient(180deg, var(--panel-2), var(--panel));
      border-radius: 0;
      overflow: hidden;
    }}
    .top-half {{ height: 50vh; min-height: 300px; }}
    .bottom-half {{
      margin-top: 8px;
      display: grid;
      grid-template-columns: 1.65fr 1fr 1fr;
      gap: 10px;
      height: calc(50vh - 18px);
      min-height: 280px;
    }}
    .panel-head {{
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      color: #c7d1ef;
      font-size: 15px;
      background: #10182d;
      font-weight: 700;
      letter-spacing: 0.04em;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .table-scroll {{ overflow: auto; max-height: calc(50vh - 44px); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #1e2537; text-align: left; vertical-align: top; }}
    th {{ color: #9fa8c8; font-weight: 700; position: sticky; top: 0; background: #121a30; z-index: 2; font-size: 13px; }}
    tr.active {{ background: rgba(64, 101, 175, 0.24); }}
    .market-row {{ background: rgba(89, 103, 144, 0.25); }}
    tr:hover {{ background: rgba(59, 74, 116, 0.20); }}
    .code {{ color: #d7e0ff; font-weight: 800; }}
    .name {{ color: var(--muted); }}
    .score.badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-weight: 800;
      font-size: 12px;
      border: 1px solid transparent;
      white-space: nowrap;
    }}
    .badge.bullish {{ color: var(--up); border-color: rgba(255, 42, 79, 0.5); }}
    .badge.neutral {{ color: var(--accent); border-color: rgba(255, 210, 74, 0.5); }}
    .badge.bearish {{ color: var(--down); border-color: rgba(0, 208, 111, 0.5); }}
    .up {{ color: var(--up); }}
    .down {{ color: var(--down); }}
    .flat {{ color: var(--flat); }}
    .pv-strip, .ms-strip {{ display: flex; gap: 4px; flex-wrap: wrap; min-width: 220px; }}
    .pv-chip, .ms-chip {{
      border: 1px solid #2e3548;
      border-radius: 6px;
      padding: 3px 5px;
      display: inline-flex;
      flex-direction: column;
      line-height: 1.2;
      background: #0b1020;
    }}
    .pv-chip b, .ms-chip b {{ font-size: 12px; font-weight: 800; }}
    .pv-chip small {{
      font-size: 11px;
      color: #9fa8c8;
      line-height: 1;
      margin-bottom: 2px;
    }}
    .pv-chip i {{
      font-size: 11px;
      font-style: normal;
      line-height: 1.2;
      margin-top: 1px;
    }}
    .pv-chip em, .ms-chip em {{ font-size: 11px; font-style: normal; }}
    .tiny-note {{ color: var(--muted); font-size: 12px; }}
    .panel-body {{ padding: 10px; height: calc(100% - 36px); overflow: auto; }}
    .news-list {{ display: grid; gap: 8px; }}
    .news {{ border: 1px solid #2b3246; border-radius: 8px; background: #0b1020; padding: 10px; font-size: 15px; line-height: 1.45; }}
    .news small {{ color: var(--muted); display: block; margin-bottom: 4px; }}
    .chart-wrap {{ height: 100%; display: flex; flex-direction: column; }}
    .block-title {{ font-size: 15px; color: #c7d1ef; margin-bottom: 8px; }}
    .legend-row {{ display: flex; gap: 10px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin-top: 8px; }}
    .legend-row span {{ display: inline-flex; align-items: center; gap: 6px; }}
    .l {{ display: inline-block; width: 18px; border-top: 2px solid #fff; }}
    .l.close {{ border-top-color: #ffd24a; }}
    .l.ma5 {{ border-top-color: #00d06f; }}
    .l.ma20 {{ border-top-color: #55a6ff; }}
    .l.vol {{ border-top-color: #ff2a4f; }}
    .empty-panel {{ color: var(--muted); font-size: 13px; padding: 16px; }}
    .sub-table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    .sub-table th, .sub-table td {{ border-bottom: 1px solid #222a3c; padding: 7px; }}
    .warn {{
      margin-top: 8px;
      border: 1px solid rgba(255, 42, 79, 0.38);
      background: rgba(95, 23, 40, 0.36);
      color: #ffc7d3;
      border-radius: 8px;
      padding: 8px;
      font-size: 12px;
      line-height: 1.4;
    }}
    .help-toggle {{
      margin-left: 4px;
      width: 18px;
      height: 18px;
      border-radius: 999px;
      border: 1px solid #4a5473;
      background: #141e36;
      color: #c9d8ff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 12px;
      font-weight: 700;
      line-height: 1;
    }}
    .help-wrap {{
      position: relative;
      display: inline-flex;
      align-items: center;
    }}
    .help-wrap summary {{
      list-style: none;
    }}
    .help-wrap summary::-webkit-details-marker {{
      display: none;
    }}
    .help-panel {{
      position: absolute;
      top: 26px;
      left: 0;
      z-index: 5;
      width: min(520px, 85vw);
      background: #0b1020;
      border: 1px solid #3f4a69;
      border-radius: 8px;
      padding: 10px;
      color: #dce4ff;
      font-size: 12px;
      line-height: 1.45;
      display: none;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.38);
    }}
    .help-wrap[open] .help-panel {{
      display: block;
    }}
    @media (max-width: 1200px) {{
      .top-half {{ height: auto; min-height: 340px; }}
      .table-scroll {{ max-height: none; }}
      .bottom-half {{ grid-template-columns: 1fr; height: auto; }}
      .bottom-half .panel {{ min-height: 320px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">{body}</main>
</body>
</html>"""


def render_dashboard(
    rows: list[WatchlistRow],
    source: str,
    bundle: DatasetBundle,
    codes: list[str],
    selected_code: str,
    histories: dict[str, StockDayResponse | None],
    margin_series_map: dict[str, list[tuple[str, float, float]]],
    stock_news: list[tuple[str, str, str]],
    valuation_row: dict[str, str] | None,
    valuation_date: str = "",
    valuation_error: str = "",
    news_error: str = "",
    error_message: str = "",
) -> str:
    index = build_watchlist_index(rows)
    selected = index.get(selected_code) if selected_code else None
    if selected is None and rows:
        selected = rows[0]
        selected_code = selected.snapshot.code

    source_label = "TWSE Live" if source == "live" else "離線示範"

    top_rows: list[str] = []
    market_name, market_index, market_pct, market_delta = build_market_summary(bundle)
    market_cls = "up" if market_pct > 0 else "down" if market_pct < 0 else "flat"
    top_rows.append(
        f"""
        <tr class="market-row">
          <td><span class="code">大盤</span><br><span class="name">{escape(market_name)}</span></td>
          <td><span class="score badge neutral">市場</span></td>
          <td>{format_value(market_index)}<br><span class="tiny-note">即時</span></td>
          <td class="{market_cls}">{market_pct:+.2f}%<br><span class="tiny-note">{escape(market_delta)} 點</span></td>
          <td>{render_7day_market_index(bundle)}</td>
          <td><span class="tiny-note">融資融券僅適用個股</span></td>
        </tr>
        """
    )
    for row in rows:
        snapshot = row.snapshot
        trend = row.trend
        history = histories.get(snapshot.code)
        growth = growth_estimate(row, history)
        growth_cls = "up" if growth > 0 else "down" if growth < 0 else "flat"
        latest_date, latest_price, _ = latest_price_volume_date(history)
        active_cls = "active" if snapshot.code == selected_code else ""
        top_rows.append(
            f"""
            <tr class="{active_cls}">
              <td>
                <a href="{build_query(source, codes, snapshot.code)}">
                  <span class="code">{escape(snapshot.code)}</span><br>
                  <span class="name">{escape(snapshot.name or '-')}</span>
                </a>
              </td>
              <td><span class="score badge {score_class(trend.score)}">{trend.score} / {escape(trend.label)}</span></td>
              <td>{latest_price:.2f}<br><span class="tiny-note">{escape(latest_date)}</span></td>
              <td class="{growth_cls}">{growth:+.2f}%</td>
              <td>{render_7day_price_volume(history)}</td>
              <td>{render_7day_margin_short(margin_series_map.get(snapshot.code, []))}</td>
            </tr>
            """
        )

    news_items: list[str] = []
    if selected is not None:
        if valuation_row is not None:
            pe = pick_news_value(valuation_row, "本益比", "PEratio") or "-"
            dy = pick_news_value(valuation_row, "殖利率(%)", "殖利率", "DividendYield") or "-"
            pb = pick_news_value(valuation_row, "股價淨值比", "PBratio") or "-"
            val_date = valuation_date or pick_news_value(valuation_row, "日期") or "最新可用日"
            news_items.append(
                f'<div class="news"><small>BWIBBU_d 估值（{escape(val_date)}）</small>本益比: {escape(pe)} / 殖利率: {escape(dy)}% / 股價淨值比: {escape(pb)}</div>'
            )
        if valuation_error:
            news_items.append(f'<div class="news"><small>估值資料提醒</small>{escape(valuation_error)}</div>')

        for date_text, title, link in stock_news:
            headline = f'<a href="{escape(link)}" target="_blank" rel="noopener noreferrer">{escape(title)}</a>' if link else escape(title)
            news_items.append(f'<div class="news"><small>{escape(date_text)}</small>{headline}</div>')
        if not news_items:
            news_items.append('<div class="news"><small>資料提醒</small>目前查無此股票新聞。</div>')
        if news_error:
            news_items.append(f'<div class="news"><small>資料來源提醒</small>{escape(news_error)}</div>')
        news_items.append(
            f'<div class="news"><small>模型解讀</small>趨勢分數 {selected.trend.score}，目前判定為 {escape(selected.trend.label)}。關鍵原因: {escape("、".join(selected.trend.reasons))}</div>'
        )
        news_items.append(render_score_breakdown(selected))

    related_rows, related_caption = build_related_market_stocks(selected_code, bundle) if selected is not None else ([], "關聯資料不足")

    related_table = "".join(
        f"""
        <tr>
          <td>{escape(code)} {escape(name or '-')}</td>
          <td>{price:.2f}</td>
          <td>{volume/1000:.1f}K</td>
          <td>{escape(note)}</td>
        </tr>
        """
        for code, name, price, volume, note in related_rows
    )

    selected_chart = render_30day_chart(
        histories.get(selected_code),
        f"{selected.snapshot.code} {selected.snapshot.name}" if selected else "所選股票",
    )

    body = f"""
    <section class="toolbar">
      <form method="get" action="/" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;width:100%;">
        <input type="text" name="codes" value="{escape(','.join(codes))}" placeholder="輸入股票代號，例如 2330,2603,0050">
        <input type="hidden" name="code" value="{escape(selected_code)}">
        <button class="btn sample" type="submit" name="source" value="sample">示範資料</button>
        <button class="btn live" type="submit" name="source" value="live">TWSE Live</button>
        <span class="status">資料來源: {escape(source_label)} | 版面: 上半 1 區，下半 3 區</span>
      </form>
    </section>

    <section class="panel top-half">
      <div class="panel-head">
        自選股總覽: 代號 / 名稱 / 評分 / 最新價 / 成長預估 / 近 7 日股價與成交量 / 近 7 日融資融券增減
        <details class="help-wrap">
          <summary class="help-toggle">?</summary>
          <span class="help-panel">
            融資增加且股價走強: 多方槓桿與趨勢一致，可續抱但要設停利。<br>
            融資增加但股價走弱: 追價籌碼偏重，建議降低槓桿與部位。<br>
            融券增加且股價走弱: 空方壓力加重，建議保守觀望。<br>
            融券增加但股價走強: 可能有軋空機會，可分批進場並控管風險。<br>
            原則: 融資融券僅是籌碼訊號，請搭配技術線與基本面一起判讀。<br>
            資料來源: TWSE `/exchangeReport/MI_MARGN`
          </span>
        </details>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>股票</th>
              <th>評分</th>
              <th>最新價(日期)</th>
              <th>成長預估</th>
              <th>近 7 日股價與量</th>
              <th>近 7 日融資融券增減</th>
            </tr>
          </thead>
          <tbody>
            {''.join(top_rows) if top_rows else '<tr><td colspan="6" class="empty-panel">目前沒有可顯示的股票資料</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>

    <section class="bottom-half">
      <section class="panel">
        <div class="panel-head">左區: 所選股票 30 天技術線圖（含成交量）</div>
        <div class="panel-body">{selected_chart}</div>
      </section>

      <section class="panel">
        <div class="panel-head">中區: 所選股票相關新聞</div>
        <div class="panel-body">
          <div class="news-list">{''.join(news_items)}</div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">右區: 關聯股票前五大（最新價格與成交量）</div>
        <div class="panel-body">
          <table class="sub-table">
            <thead>
              <tr><th>股票</th><th>最新價</th><th>最新量</th><th>關聯依據</th></tr>
            </thead>
            <tbody>
              {related_table if related_table else '<tr><td colspan="4" class="empty-panel">關聯股票資料不足</td></tr>'}
            </tbody>
          </table>
          <div class="tiny-note" style="margin-top:8px;">{escape(related_caption)}</div>
        </div>
      </section>
    </section>

    {f'<div class="warn">{escape(error_message)}</div>' if error_message else ''}
    """
    return render_layout("TW Stock Dashboard", body)


def load_rows(source: str, codes: list[str]) -> tuple[list[WatchlistRow], DatasetBundle, str]:
    try:
        bundle = load_sample_datasets() if source == "sample" else load_live_datasets()
        return build_watchlist(bundle, codes), bundle, ""
    except DataFetchError as exc:
        if source == "live":
            bundle = load_sample_datasets()
            rows = build_watchlist(bundle, codes)
            return rows, bundle, f"Live 資料讀取失敗，已改用示範資料。原因: {exc}"
        return [], load_sample_datasets(), str(exc)


def load_history(source: str, code: str) -> tuple[StockDayResponse | None, str]:
    if not code:
        return None, ""

    try:
        if source == "sample":
            return load_sample_recent_stock_history(code, months=3), ""
        return fetch_recent_stock_history(code, months=3), ""
    except DataFetchError as exc:
        if source == "live":
            try:
                return load_sample_recent_stock_history(code, months=3), f"Live 歷史資料讀取失敗，已改用示範資料。原因: {exc}"
            except DataFetchError:
                return None, str(exc)
        return None, str(exc)


def load_histories(source: str, codes: list[str]) -> tuple[dict[str, StockDayResponse | None], str]:
    histories: dict[str, StockDayResponse | None] = {}
    errors: list[str] = []
    for code in codes:
        history, error = load_history(source, code)
        histories[code] = history
        if error:
            errors.append(f"{code}: {error}")
    return histories, "；".join(errors[:3])


def load_valuation(source: str, code: str) -> tuple[dict[str, str] | None, str, str]:
    if not code:
        return None, "", ""
    try:
        if source == "sample":
            response = load_sample_bwibbu_by_date(current_report_date())
        else:
            response = None
            for offset in range(7):
                date = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
                try:
                    response = fetch_bwibbu_by_date(date)
                    break
                except DataFetchError:
                    continue
            if response is None:
                raise DataFetchError("BWIBBU_d 近 7 日皆無可用資料")
        for row in response.rows:
            if row.get("股票代號", "") == code or row.get("證券代號", "") == code:
                return row, "", response.date
        raise DataFetchError(f"BWIBBU_d 查無 {code} 在 {response.date} 的資料")
    except DataFetchError as exc:
        if source == "live":
            sample_response = load_sample_bwibbu_by_date(current_report_date())
            for row in sample_response.rows:
                if row.get("股票代號", "") == code or row.get("證券代號", "") == code:
                    return row, f"Live 估值資料讀取失敗，已改用示範資料。原因: {exc}", sample_response.date
        return None, str(exc), ""


def make_handler(default_codes: list[str], default_source: str):

    class StockHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            source = query.get("source", [default_source])[0]
            if source not in {"sample", "live"}:
                source = default_source

            cookie_codes = parse_codes_cookie(self.headers.get("Cookie", ""))
            codes = normalize_codes(query.get("codes", []), cookie_codes or default_codes)
            selected_code = query.get("code", [""])[0].strip()

            rows, bundle, error_message = load_rows(source, codes)
            effective_source = "sample" if error_message and source == "live" else source
            histories, history_error = load_histories(effective_source, codes)
            margin_series_map, margin_error = load_margin_series(effective_source, rows, codes)
            row_index = build_watchlist_index(rows)
            active_code = selected_code or (rows[0].snapshot.code if rows else "")
            selected_row = row_index.get(active_code)
            stock_news, news_error = load_stock_news(
                effective_source,
                active_code,
                selected_row.snapshot.material_messages if selected_row else [],
            )
            valuation_row, valuation_error, valuation_date = load_valuation(effective_source, active_code)

            if parsed.path in {"/", "/stock"}:
                merged_error = "；".join(filter(None, [error_message, history_error, margin_error]))
                self.respond(
                    render_dashboard(
                        rows=rows,
                        source=effective_source,
                        bundle=bundle,
                        codes=codes,
                        selected_code=selected_code,
                        histories=histories,
                        margin_series_map=margin_series_map,
                        stock_news=stock_news,
                        valuation_row=valuation_row,
                        valuation_date=valuation_date,
                        valuation_error=valuation_error,
                        news_error=news_error,
                        error_message=merged_error,
                    ),
                    extra_headers={"Set-Cookie": build_codes_cookie(codes)},
                )
                return

            self.respond(
                render_layout(
                    "Not Found",
                    '<section class="panel"><div class="panel-head">404</div><div class="panel-body">找不到頁面。<p><a class="btn" href="/">回到首頁</a></p></div></section>',
                ),
                status=404,
            )

        def log_message(self, format: str, *args) -> None:
            return

        def respond(self, body: str, status: int = 200, extra_headers: dict[str, str] | None = None) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            if extra_headers:
                for key, value in extra_headers.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

    return StockHandler


def run_server(default_codes: list[str], default_source: str, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(default_codes, default_source))
    print(f"Web UI 已啟動: http://{host}:{port}")
    server.serve_forever()
