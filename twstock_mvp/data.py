from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib import error, parse, request

from twstock_mvp.sample_data import (
    SAMPLE_BWIBBU,
    SAMPLE_DAY_AVG,
    SAMPLE_INDUSTRY,
    SAMPLE_MATERIAL,
    SAMPLE_MARGIN,
    SAMPLE_MI_INDEX,
    SAMPLE_MI_5MINS_HIST,
    SAMPLE_MI_5MINS,
    SAMPLE_PROMOTION,
    SAMPLE_BWIBBU_D,
    SAMPLE_STOCK_DAY,
)

BASE_URL = "https://openapi.twse.com.tw/v1"
REPORT_BASE_URL = "https://www.twse.com.tw"


class DataFetchError(RuntimeError):
    """Raised when a TWSE endpoint cannot be fetched."""


@dataclass
class DatasetBundle:
    valuation: list[dict[str, Any]]
    day_avg: list[dict[str, Any]]
    industry_info: list[dict[str, Any]]
    material_info: list[dict[str, Any]]
    abnormal_promotion: list[dict[str, Any]]
    margin: list[dict[str, Any]]
    market_index: list[dict[str, Any]]
    market_hist: list[dict[str, Any]]
    intraday: list[dict[str, Any]]


@dataclass
class StockDayRecord:
    date: str
    volume: str
    turnover: str
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    price_change: str
    transactions: str


@dataclass
class StockDayResponse:
    stock_no: str
    date: str
    title: str
    fields: list[str]
    records: list[StockDayRecord]
    notes: list[str]


@dataclass
class ValuationByDateResponse:
    date: str
    fields: list[str]
    rows: list[dict[str, str]]


def fetch_any_json(url: str, timeout: int = 15) -> Any:
    req = request.Request(url, headers={"User-Agent": "twstock-mvp/0.1"})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except error.URLError as exc:
        raise DataFetchError(f"Unable to fetch {url}: {exc}") from exc

    return json.loads(payload)


def fetch_json(endpoint: str, timeout: int = 15) -> list[dict[str, Any]]:
    url = f"{BASE_URL}{endpoint}"
    data = fetch_any_json(url, timeout=timeout)
    if not isinstance(data, list):
        raise DataFetchError(f"Unexpected response shape from {url}")
    return data


def build_stock_day_url(stock_no: str, date: str) -> str:
    query = parse.urlencode(
        {
            "response": "json",
            "date": date,
            "stockNo": stock_no,
        }
    )
    return f"{REPORT_BASE_URL}/exchangeReport/STOCK_DAY?{query}"


def build_bwibbu_date_url(date: str, select_type: str = "ALL") -> str:
    query = parse.urlencode(
        {
            "response": "json",
            "date": date,
            "selectType": select_type,
        }
    )
    return f"{REPORT_BASE_URL}/exchangeReport/BWIBBU_d?{query}"


def build_margin_date_url(date: str, select_type: str = "ALL") -> str:
    query = parse.urlencode(
        {
            "response": "json",
            "date": date,
            "selectType": select_type,
        }
    )
    return f"{REPORT_BASE_URL}/exchangeReport/MI_MARGN?{query}"


def build_news_list_url(stock_no: str, page: int = 1) -> str:
    query = parse.urlencode(
        {
            "response": "json",
            "stockNo": stock_no,
            "page": page,
        }
    )
    return f"{REPORT_BASE_URL}/news/newsList?{query}"


def fetch_stock_day(stock_no: str, date: str, timeout: int = 15) -> StockDayResponse:
    url = build_stock_day_url(stock_no=stock_no, date=date)
    payload = fetch_any_json(url, timeout=timeout)
    if not isinstance(payload, dict):
        raise DataFetchError(f"Unexpected response shape from {url}")

    stat = str(payload.get("stat", ""))
    if stat and stat != "OK":
        raise DataFetchError(f"TWSE STOCK_DAY returned stat={stat} for {stock_no} {date}")

    data_rows = payload.get("data", [])
    if not isinstance(data_rows, list):
        raise DataFetchError(f"Unexpected STOCK_DAY data rows from {url}")

    records: list[StockDayRecord] = []
    for row in data_rows:
        if not isinstance(row, list):
            continue
        padded = row + [""] * (9 - len(row))
        records.append(
            StockDayRecord(
                date=str(padded[0]),
                volume=str(padded[1]),
                turnover=str(padded[2]),
                open_price=str(padded[3]),
                high_price=str(padded[4]),
                low_price=str(padded[5]),
                close_price=str(padded[6]),
                price_change=str(padded[7]),
                transactions=str(padded[8]),
            )
        )

    return StockDayResponse(
        stock_no=stock_no,
        date=date,
        title=str(payload.get("title", "")),
        fields=[str(field) for field in payload.get("fields", []) if field is not None],
        records=records,
        notes=[str(note) for note in payload.get("notes", []) if note is not None],
    )


def fetch_bwibbu_by_date(date: str, select_type: str = "ALL", timeout: int = 15) -> ValuationByDateResponse:
    url = build_bwibbu_date_url(date=date, select_type=select_type)
    payload = fetch_any_json(url, timeout=timeout)
    if not isinstance(payload, dict):
        raise DataFetchError(f"Unexpected response shape from {url}")

    stat = str(payload.get("stat", ""))
    if stat and stat != "OK":
        raise DataFetchError(f"TWSE BWIBBU_d returned stat={stat} for {date}")

    fields = [str(field) for field in payload.get("fields", []) if field is not None]
    data_rows = payload.get("data", [])
    if not isinstance(data_rows, list):
        raise DataFetchError(f"Unexpected BWIBBU_d data rows from {url}")

    rows: list[dict[str, str]] = []
    for row in data_rows:
        if not isinstance(row, list):
            continue
        row_dict: dict[str, str] = {}
        for index, field in enumerate(fields):
            row_dict[field] = str(row[index]) if index < len(row) else ""
        rows.append(row_dict)

    return ValuationByDateResponse(date=date, fields=fields, rows=rows)


def fetch_margin_by_date(date: str, select_type: str = "ALL", timeout: int = 15) -> list[dict[str, str]]:
    url = build_margin_date_url(date=date, select_type=select_type)
    payload = fetch_any_json(url, timeout=timeout)
    if not isinstance(payload, dict):
        raise DataFetchError(f"Unexpected response shape from {url}")

    stat = str(payload.get("stat", ""))
    if stat and stat != "OK":
        raise DataFetchError(f"TWSE MI_MARGN returned stat={stat} for {date}")

    fields = [str(field) for field in payload.get("fields", []) if field is not None]
    data_rows = payload.get("data", [])
    if not isinstance(data_rows, list):
        raise DataFetchError(f"Unexpected MI_MARGN data rows from {url}")

    rows: list[dict[str, str]] = []
    for row in data_rows:
        if not isinstance(row, list):
            continue
        row_dict: dict[str, str] = {}
        for index, field in enumerate(fields):
            row_dict[field] = str(row[index]) if index < len(row) else ""
        rows.append(row_dict)
    return rows


def fetch_news_list(stock_no: str, page: int = 1, timeout: int = 15) -> list[dict[str, str]]:
    url = build_news_list_url(stock_no=stock_no, page=page)
    payload = fetch_any_json(url, timeout=timeout)

    if isinstance(payload, list):
        return [{str(k): str(v) for k, v in item.items()} for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        raise DataFetchError(f"Unexpected response shape from {url}")

    candidates = payload.get("data") or payload.get("dataList") or payload.get("newsList") or []
    if not isinstance(candidates, list):
        raise DataFetchError(f"Unexpected news list rows from {url}")

    rows: list[dict[str, str]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        rows.append({str(k): str(v) for k, v in item.items()})
    return rows


def load_sample_stock_day(stock_no: str, date: str) -> StockDayResponse:
    payload = SAMPLE_STOCK_DAY.get(stock_no)
    if payload is None:
        raise DataFetchError(f"Sample STOCK_DAY data not found for {stock_no}")

    records = [
        StockDayRecord(
            date=str(row[0]),
            volume=str(row[1]),
            turnover=str(row[2]),
            open_price=str(row[3]),
            high_price=str(row[4]),
            low_price=str(row[5]),
            close_price=str(row[6]),
            price_change=str(row[7]),
            transactions=str(row[8]),
        )
        for row in payload["records"]
    ]

    return StockDayResponse(
        stock_no=stock_no,
        date=date,
        title=str(payload["title"]),
        fields=[str(field) for field in payload["fields"]],
        records=records,
        notes=[str(note) for note in payload.get("notes", [])],
    )


def load_sample_bwibbu_by_date(date: str) -> ValuationByDateResponse:
    fields = ["股票代號", "股票名稱", "本益比", "殖利率(%)", "股價淨值比"]
    return ValuationByDateResponse(date=date, fields=fields, rows=[dict(row) for row in SAMPLE_BWIBBU_D])


def current_report_month() -> str:
    return datetime.now().strftime("%Y%m01")


def current_report_date() -> str:
    return datetime.now().strftime("%Y%m%d")


def report_months(count: int) -> list[str]:
    now = datetime.now()
    year = now.year
    month = now.month
    result: list[str] = []
    for _ in range(count):
        result.append(f"{year:04d}{month:02d}01")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    result.reverse()
    return result


def fetch_recent_stock_history(stock_no: str, months: int = 3) -> StockDayResponse:
    merged_records: list[StockDayRecord] = []
    notes: list[str] = []
    title = ""
    fields: list[str] = []
    for report_date in report_months(months):
        monthly = fetch_stock_day(stock_no=stock_no, date=report_date)
        title = monthly.title or title
        fields = monthly.fields or fields
        merged_records.extend(monthly.records)
        notes.extend(monthly.notes)
    return StockDayResponse(
        stock_no=stock_no,
        date=report_months(months)[0],
        title=title,
        fields=fields,
        records=merged_records,
        notes=notes,
    )


def load_sample_recent_stock_history(stock_no: str, months: int = 3) -> StockDayResponse:
    base = load_sample_stock_day(stock_no=stock_no, date=report_months(months)[0])
    records: list[StockDayRecord] = []
    for offset in range(months):
        for record in base.records:
            parts = record.date.split("/")
            if len(parts) == 3:
                roc_year = int(parts[0])
                month = int(parts[1]) - (months - 1 - offset)
                year = roc_year
                while month <= 0:
                    month += 12
                    year -= 1
                new_date = f"{year:03d}/{month:02d}/{parts[2]}"
            else:
                new_date = record.date
            records.append(
                StockDayRecord(
                    date=new_date,
                    volume=record.volume,
                    turnover=record.turnover,
                    open_price=record.open_price,
                    high_price=record.high_price,
                    low_price=record.low_price,
                    close_price=record.close_price,
                    price_change=record.price_change,
                    transactions=record.transactions,
                )
            )

    return StockDayResponse(
        stock_no=base.stock_no,
        date=report_months(months)[0],
        title=f"{base.stock_no} 近 {months} 月示範走勢",
        fields=base.fields,
        records=records,
        notes=base.notes,
    )


def load_live_datasets() -> DatasetBundle:
    return DatasetBundle(
        valuation=fetch_json("/exchangeReport/BWIBBU_ALL"),
        day_avg=fetch_json("/exchangeReport/STOCK_DAY_AVG_ALL"),
        industry_info=fetch_json("/opendata/t187ap03_L"),
        material_info=fetch_json("/opendata/t187ap04_L"),
        abnormal_promotion=fetch_json("/Announcement/BFZFZU_T"),
        margin=fetch_json("/exchangeReport/MI_MARGN"),
        market_index=fetch_json("/exchangeReport/MI_INDEX"),
        market_hist=fetch_json("/indicesReport/MI_5MINS_HIST"),
        intraday=fetch_json("/exchangeReport/MI_5MINS"),
    )


def load_sample_datasets() -> DatasetBundle:
    return DatasetBundle(
        valuation=SAMPLE_BWIBBU,
        day_avg=SAMPLE_DAY_AVG,
        industry_info=SAMPLE_INDUSTRY,
        material_info=SAMPLE_MATERIAL,
        abnormal_promotion=SAMPLE_PROMOTION,
        margin=SAMPLE_MARGIN,
        market_index=SAMPLE_MI_INDEX,
        market_hist=SAMPLE_MI_5MINS_HIST,
        intraday=SAMPLE_MI_5MINS,
    )
