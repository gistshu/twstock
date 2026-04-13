from __future__ import annotations

import argparse

from twstock_mvp.data import (
    DataFetchError,
    build_stock_day_url,
    fetch_stock_day,
    load_live_datasets,
    load_sample_datasets,
)
from twstock_mvp.watchlist import build_watchlist
from twstock_mvp.web import run_server

DEFAULT_WATCHLIST = ["2330", "2603", "0050"]


def format_price(value: float) -> str:
    if not value:
        return "-"
    return f"{value:.2f}"


def load_bundle(use_sample: bool):
    if use_sample:
        return load_sample_datasets()
    return load_live_datasets()


def render_stock_day(result) -> str:
    lines = []
    lines.append(result.title or f"{result.stock_no} {result.date} STOCK_DAY")
    lines.append("=" * 72)
    lines.append(f"股票代號: {result.stock_no}")
    lines.append(f"查詢日期: {result.date}")
    lines.append(f"欄位: {' | '.join(result.fields) if result.fields else '-'}")
    lines.append("")
    if not result.records:
        lines.append("查無資料")
    else:
        for record in result.records[:10]:
            lines.append(
                f"{record.date} | 開 {record.open_price} 高 {record.high_price} 低 {record.low_price} 收 {record.close_price}"
                f" | 漲跌 {record.price_change} | 量 {record.volume}"
            )
    if result.notes:
        lines.append("")
        lines.append(f"備註: {' / '.join(result.notes)}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TW stock trend watchlist MVP")
    parser.add_argument(
        "--codes",
        nargs="+",
        default=DEFAULT_WATCHLIST,
        help="Stock codes to analyze",
    )
    parser.add_argument(
        "--offline-sample",
        action="store_true",
        help="Use built-in sample data instead of TWSE live APIs",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start a simple web UI instead of CLI output",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Web server host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Web server port",
    )
    parser.add_argument(
        "--stock-day",
        action="store_true",
        help="Test TWSE STOCK_DAY historical daily endpoint",
    )
    parser.add_argument(
        "--stock-no",
        default="2330",
        help="Stock number for --stock-day",
    )
    parser.add_argument(
        "--date",
        default="20250101",
        help="Query date in YYYYMMDD for --stock-day",
    )
    return parser.parse_args()


def render(rows) -> str:
    lines = []
    lines.append("TW Stock Watchlist MVP")
    lines.append("=" * 72)

    for row in rows:
        snapshot = row.snapshot
        trend = row.trend
        lines.append(
            f"{snapshot.code} {snapshot.name or '-'} | 分數 {trend.score:>3} | {trend.label}"
        )
        lines.append(
            "  "
            f"收盤 {format_price(snapshot.closing_price)} / 月均 {format_price(snapshot.monthly_average_price)}"
            f" | 本益比 {format_price(snapshot.pe_ratio)}"
            f" | 殖利率 {format_price(snapshot.dividend_yield)}%"
            f" | 股價淨值比 {format_price(snapshot.pb_ratio)}"
        )
        lines.append(f"  關鍵原因: {'、'.join(trend.reasons)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()

    if args.stock_day:
        try:
            result = fetch_stock_day(stock_no=args.stock_no, date=args.date)
        except DataFetchError as exc:
            print(f"STOCK_DAY 讀取失敗: {exc}")
            print(f"測試 URL: {build_stock_day_url(stock_no=args.stock_no, date=args.date)}")
            return 1

        print(render_stock_day(result))
        return 0

    if args.serve:
        run_server(
            default_codes=args.codes,
            default_source="sample" if args.offline_sample else "live",
            host=args.host,
            port=args.port,
        )
        return 0

    try:
        bundle = load_bundle(args.offline_sample)
    except DataFetchError as exc:
        print(f"Live API 讀取失敗: {exc}")
        print("改用 --offline-sample 可先查看 MVP 分析流程。")
        return 1

    rows = build_watchlist(bundle, args.codes)
    print(render(rows))
    return 0
