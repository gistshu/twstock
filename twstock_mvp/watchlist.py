from __future__ import annotations

from dataclasses import dataclass

from twstock_mvp.data import DatasetBundle
from twstock_mvp.normalize import StockSnapshot, build_snapshot_map
from twstock_mvp.scoring import TrendResult, score_snapshot


@dataclass
class WatchlistRow:
    snapshot: StockSnapshot
    trend: TrendResult


def build_watchlist(bundle: DatasetBundle, watchlist_codes: list[str]) -> list[WatchlistRow]:
    snapshot_map = build_snapshot_map(
        valuation_rows=bundle.valuation,
        day_avg_rows=bundle.day_avg,
        material_rows=bundle.material_info,
        abnormal_rows=bundle.abnormal_promotion,
        margin_rows=bundle.margin,
        intraday_rows=bundle.intraday,
    )

    rows: list[WatchlistRow] = []
    for code in watchlist_codes:
        snapshot = snapshot_map.get(code)
        if snapshot is None:
            snapshot = StockSnapshot(code=code, name="資料不足")
        rows.append(WatchlistRow(snapshot=snapshot, trend=score_snapshot(snapshot)))

    rows.sort(key=lambda row: row.trend.score, reverse=True)
    return rows


def build_watchlist_index(rows: list[WatchlistRow]) -> dict[str, WatchlistRow]:
    return {row.snapshot.code: row for row in rows}
