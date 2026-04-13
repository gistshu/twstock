from __future__ import annotations

from dataclasses import dataclass

from twstock_mvp.normalize import StockSnapshot


POSITIVE_KEYWORDS = ("通過", "增加", "成長", "創新高", "擴產", "增資")
NEGATIVE_KEYWORDS = ("下滑", "衰退", "虧損", "處分", "重大損失", "違約")


@dataclass
class TrendResult:
    score: int
    label: str
    reasons: list[str]
    breakdown: list[tuple[int, str]]


def classify_score(score: int) -> str:
    if score >= 70:
        return "偏多觀察"
    if score >= 40:
        return "中性整理"
    return "偏空風險"


def score_snapshot(snapshot: StockSnapshot) -> TrendResult:
    score = 50
    reasons: list[str] = []
    breakdown: list[tuple[int, str]] = []

    def apply(delta: int, reason: str, add_reason: bool = True) -> None:
        nonlocal score
        score += delta
        breakdown.append((delta, reason))
        if add_reason:
            reasons.append(reason)

    if snapshot.closing_price and snapshot.monthly_average_price:
        if snapshot.closing_price > snapshot.monthly_average_price:
            apply(+20, "股價站上月均價")
        elif snapshot.closing_price < snapshot.monthly_average_price:
            apply(-20, "股價跌破月均價")

    if snapshot.buy_volume_5m and snapshot.sell_volume_5m:
        if snapshot.buy_volume_5m > snapshot.sell_volume_5m and snapshot.closing_price >= snapshot.monthly_average_price:
            apply(+10, "短線委買量強於委賣量")
        elif snapshot.sell_volume_5m > snapshot.buy_volume_5m and snapshot.closing_price < snapshot.monthly_average_price:
            apply(-10, "短線賣壓偏重")

    if 0 < snapshot.pe_ratio <= 15:
        apply(+10, "本益比處於合理偏低區間")
    elif snapshot.pe_ratio >= 25:
        apply(-10, "本益比偏高")

    if snapshot.dividend_yield >= 4:
        apply(+10, "殖利率具吸引力")

    if snapshot.pb_ratio >= 3:
        apply(-10, "股價淨值比偏高")

    margin_delta = snapshot.margin_balance_today - snapshot.margin_balance_yesterday
    if margin_delta > 0 and snapshot.closing_price < snapshot.monthly_average_price:
        apply(-15, "融資增加但股價未同步轉強")

    short_delta = snapshot.short_balance_today - snapshot.short_balance_yesterday
    if short_delta > 0 and snapshot.closing_price > snapshot.monthly_average_price:
        apply(+10, "融券增加但股價仍強")

    if snapshot.abnormal_promotion:
        apply(-25, "列入異常推介名單")

    for message in snapshot.material_messages:
        if any(keyword in message for keyword in POSITIVE_KEYWORDS):
            apply(+15, "重大訊息偏正向")
            break
        if any(keyword in message for keyword in NEGATIVE_KEYWORDS):
            apply(-20, "重大訊息偏負向")
            break

    score = max(0, min(100, score))
    if not reasons:
        reasons.append("目前訊號有限，建議持續觀察")
        breakdown.append((0, "目前訊號有限，建議持續觀察"))
    return TrendResult(score=score, label=classify_score(score), reasons=reasons[:4], breakdown=breakdown)
