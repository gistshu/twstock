from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def pick(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "--"):
        return default
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return default


@dataclass
class StockSnapshot:
    code: str
    name: str = ""
    closing_price: float = 0.0
    monthly_average_price: float = 0.0
    pe_ratio: float = 0.0
    dividend_yield: float = 0.0
    pb_ratio: float = 0.0
    material_messages: list[str] = field(default_factory=list)
    abnormal_promotion: bool = False
    margin_balance_today: float = 0.0
    margin_balance_yesterday: float = 0.0
    short_balance_today: float = 0.0
    short_balance_yesterday: float = 0.0
    buy_volume_5m: float = 0.0
    sell_volume_5m: float = 0.0


def build_snapshot_map(
    valuation_rows: list[dict[str, Any]],
    day_avg_rows: list[dict[str, Any]],
    material_rows: list[dict[str, Any]],
    abnormal_rows: list[dict[str, Any]],
    margin_rows: list[dict[str, Any]],
    intraday_rows: list[dict[str, Any]],
) -> dict[str, StockSnapshot]:
    snapshots: dict[str, StockSnapshot] = {}

    def get_snapshot(code: str, name: str = "") -> StockSnapshot:
        snapshot = snapshots.get(code)
        if snapshot is None:
            snapshot = StockSnapshot(code=code, name=name)
            snapshots[code] = snapshot
        elif name and not snapshot.name:
            snapshot.name = name
        return snapshot

    for row in valuation_rows:
        code = str(pick(row, "Code", "股票代號", "證券代號", default="")).strip()
        if not code:
            continue
        snapshot = get_snapshot(code, str(pick(row, "Name", "股票名稱", "證券名稱", default="")).strip())
        snapshot.pe_ratio = to_float(pick(row, "PEratio", "本益比"))
        snapshot.dividend_yield = to_float(pick(row, "DividendYield", "殖利率(%)", "殖利率"))
        snapshot.pb_ratio = to_float(pick(row, "PBratio", "股價淨值比"))

    for row in day_avg_rows:
        code = str(pick(row, "Code", "股票代號", "證券代號", default="")).strip()
        if not code:
            continue
        snapshot = get_snapshot(code, str(pick(row, "Name", "股票名稱", "證券名稱", default="")).strip())
        snapshot.closing_price = to_float(pick(row, "ClosingPrice", "收盤價"))
        snapshot.monthly_average_price = to_float(pick(row, "MonthlyAveragePrice", "月平均價"))

    for row in material_rows:
        code = str(pick(row, "公司代號", "股票代號", "Code", default="")).strip()
        if not code:
            continue
        snapshot = get_snapshot(code, str(pick(row, "公司簡稱", "股票名稱", "Name", default="")).strip())
        subject = str(pick(row, "主旨", "內容", default="")).strip()
        if subject:
            snapshot.material_messages.append(subject)

    for row in abnormal_rows:
        code = str(pick(row, "股票代號", "證券代號", "Code", default="")).strip()
        if not code:
            continue
        snapshot = get_snapshot(code, str(pick(row, "股票名稱", "Name", default="")).strip())
        snapshot.abnormal_promotion = True

    for row in margin_rows:
        code = str(pick(row, "股票代號", "證券代號", "Code", default="")).strip()
        if not code:
            continue
        snapshot = get_snapshot(code, str(pick(row, "股票名稱", "Name", default="")).strip())
        snapshot.margin_balance_today = to_float(pick(row, "今日融資餘額", "融資今日餘額", "融資餘額"))
        snapshot.margin_balance_yesterday = to_float(pick(row, "昨日融資餘額", "融資前日餘額"))
        snapshot.short_balance_today = to_float(pick(row, "今日融券餘額", "融券今日餘額", "融券餘額"))
        snapshot.short_balance_yesterday = to_float(pick(row, "昨日融券餘額", "融券前日餘額"))

    for row in intraday_rows:
        code = str(pick(row, "股票代號", "證券代號", "Code", default="")).strip()
        if not code:
            continue
        snapshot = get_snapshot(code)
        snapshot.buy_volume_5m = to_float(pick(row, "累積委託買進數量", "買進委託量", "累積買進委託數量"))
        snapshot.sell_volume_5m = to_float(pick(row, "累積委託賣出數量", "賣出委託量", "累積賣出委託數量"))

    return snapshots
