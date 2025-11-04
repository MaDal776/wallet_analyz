from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Iterable, List, Optional

from decimal import Decimal

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from ..schemas import AnalysisRequest, AnalysisResponse
from csv_analyzer import (  # type: ignore import-not-found
    AggregateResult,
    aggregate_slug_stats,
    format_decimal,
    format_decimal_percent,
)
from wallet_analyzer import WalletAnalyzer  # type: ignore import-not-found


UTC = timezone.utc
CST = timezone(timedelta(hours=8))


def daterange(start: datetime, end: datetime) -> Iterable[datetime]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _to_timestamp_cst(day: datetime) -> Dict[str, object]:
    start_cst = datetime.combine(day.date(), datetime.min.time(), tzinfo=CST)
    end_cst = start_cst + timedelta(days=1)
    return {
        "start_ts": int(start_cst.astimezone(UTC).timestamp()),
        "end_ts": int(end_cst.astimezone(UTC).timestamp()),
        "date_tag": day.strftime("%Y%m%d"),
    }


def _decimal_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format_decimal(value)


def _percent_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format_decimal_percent(value)


def run_analysis(payload: AnalysisRequest) -> AnalysisResponse:
    start_day = datetime.combine(payload.start_date, datetime.min.time(), tzinfo=CST)
    end_day = datetime.combine(payload.end_date, datetime.min.time(), tzinfo=CST)
    if end_day < start_day:
        raise ValueError("结束日期不能早于起始日期")

    analyzer = WalletAnalyzer(payload.address)

    with TemporaryDirectory() as tmp_dir:
        csv_paths: List[Path] = []
        for day in daterange(start_day, end_day):
            info = _to_timestamp_cst(day)
            trades = analyzer.fetch_trades_for_day(
                info["start_ts"],
                info["end_ts"],
                max_workers=payload.max_workers,
                record_types=("TRADE", "REDEEM"),
            )
            if not trades:
                continue
            filename = Path(tmp_dir) / f"{info['date_tag']}_{payload.address[:5]}.csv"
            saved = analyzer.save_trades_to_csv(trades, str(filename))
            if saved:
                csv_paths.append(Path(saved))

        if not csv_paths:
            raise ValueError("指定时间范围内没有交易数据")

        aggregate: AggregateResult = aggregate_slug_stats(csv_paths)

    metadata = {
        "address": payload.address,
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
    }

    global_stats = aggregate.global_stats
    daily_stats = aggregate.daily_stats
    hourly_stats = aggregate.hourly_stats
    slug_stats = aggregate.slug_stats
    monthly_stats = aggregate.monthly_stats

    daily_records = sorted(daily_stats.values(), key=lambda d: d.date_str)
    top_profit_days = sorted(daily_stats.values(), key=lambda d: d.profit, reverse=True)[:5]
    top_loss_days = sorted(daily_stats.values(), key=lambda d: d.profit)[:5]

    total_hourly_trades = sum(stat.trade_count for stat in hourly_stats.values())
    total_hourly_trades_decimal = Decimal(total_hourly_trades)

    top_volume = sorted(
        slug_stats.items(), key=lambda item: item[1].total_volume, reverse=True
    )[:10]
    top_position = sorted(
        slug_stats.items(), key=lambda item: abs(item[1].net_position), reverse=True
    )[:10]
    total_volume_sum = sum((stats.total_volume for _, stats in top_volume), Decimal("0"))

    monthly_group: Dict[str, List] = defaultdict(list)
    for stats in monthly_stats.values():
        monthly_group[stats.month].append(stats)

    monthly_records: List[Dict[str, object]] = []
    for month in sorted(monthly_group.keys()):
        entries = sorted(monthly_group[month], key=lambda s: s.profit, reverse=True)
        for idx, stat in enumerate(entries, start=1):
            monthly_records.append(
                {
                    "month": month,
                    "ranking": idx,
                    "token": stat.category.token,
                    "duration": stat.category.duration,
                    "settlement": stat.category.settlement,
                    "trade_count": stat.trade_count,
                    "buy_usdc": format_decimal(stat.buy_usdc),
                    "sell_usdc": format_decimal(stat.sell_usdc),
                    "profit": format_decimal(stat.profit),
                    "roi": format_decimal_percent(stat.roi),
                    "redeem_count": stat.redeem_count,
                    "redeem_ratio": format_decimal_percent(stat.redeem_ratio),
                }
            )

    roi_leaderboard = sorted(
        ((slug, stat) for slug, stat in slug_stats.items() if stat.roi is not None),
        key=lambda item: item[1].roi,
        reverse=True,
    )[:10]

    profit_leaderboard = sorted(
        slug_stats.items(), key=lambda item: item[1].profit, reverse=True
    )[:10]

    loss_leaderboard = sorted(
        slug_stats.items(), key=lambda item: item[1].profit
    )[:10]

    response = AnalysisResponse(
        metadata=metadata,
        global_summary={
            "total_trades": global_stats.total_trades,
            "total_buy_trades": global_stats.total_buy_trades,
            "total_sell_trades": global_stats.total_sell_trades,
            "total_buy_usdc": format_decimal(global_stats.total_buy_usdc),
            "total_sell_usdc": format_decimal(global_stats.total_sell_usdc),
            "net_profit": format_decimal(global_stats.net_profit),
            "roi": _percent_str(global_stats.roi),
            "avg_profit_per_trade": _decimal_str(global_stats.avg_profit_per_trade),
            "total_redeem_trades": global_stats.total_redeem_trades,
            "redeem_ratio": _percent_str(global_stats.redeem_ratio),
        },
        daily_summary={
            "total_days": len(daily_records),
            "total_buy": format_decimal(sum((d.buy_usdc for d in daily_records), Decimal("0"))),
            "total_sell": format_decimal(sum((d.sell_usdc for d in daily_records), Decimal("0"))),
            "total_profit": format_decimal(sum((d.profit for d in daily_records), Decimal("0"))),
            "top_profitable_days": [
                {
                    "date": record.date_str,
                    "trade_count": record.trade_count,
                    "buy_usdc": format_decimal(record.buy_usdc),
                    "sell_usdc": format_decimal(record.sell_usdc),
                    "profit": format_decimal(record.profit),
                }
                for record in top_profit_days
            ],
            "top_loss_days": [
                {
                    "date": record.date_str,
                    "trade_count": record.trade_count,
                    "buy_usdc": format_decimal(record.buy_usdc),
                    "sell_usdc": format_decimal(record.sell_usdc),
                    "profit": format_decimal(record.profit),
                }
                for record in top_loss_days
            ],
        },
        hourly_distribution=[
            {
                "hour": hour,
                "trade_count": stat.trade_count,
                "buy_trades": stat.buy_trades,
                "sell_trades": stat.sell_trades,
                "ratio": _percent_str(
                    (Decimal(stat.trade_count) / total_hourly_trades_decimal)
                    if total_hourly_trades
                    else None
                ),
            }
            for hour, stat in sorted(hourly_stats.items())
        ],
        market_concentration={
            "top_by_volume": [
                {
                    "ranking": idx + 1,
                    "slug": slug,
                    "total_volume": format_decimal(stats.total_volume),
                    "ratio": _percent_str(
                        (stats.total_volume / total_volume_sum) if total_volume_sum else None
                    ),
                }
                for idx, (slug, stats) in enumerate(top_volume)
            ],
            "top_by_net_position": [
                {
                    "ranking": idx + 1,
                    "slug": slug,
                    "net_position": format_decimal(stats.net_position),
                }
                for idx, (slug, stats) in enumerate(top_position)
            ],
        },
        monthly_market=monthly_records,
        roi_leaderboard=[
            {
                "ranking": idx + 1,
                "slug": slug,
                "profit": format_decimal(stats.profit),
                "roi": _percent_str(stats.roi),
                "buy_usdc": format_decimal(stats.buy_usdc),
                "sell_usdc": format_decimal(stats.sell_usdc),
                "avg_buy_price": format_decimal(stats.avg_buy_price),
                "avg_sell_price": format_decimal(stats.avg_sell_price),
                "avg_buy_amount": format_decimal(stats.avg_buy_amount),
                "trade_count": stats.count,
            }
            for idx, (slug, stats) in enumerate(roi_leaderboard)
        ],
        profit_leaderboard=[
            {
                "ranking": idx + 1,
                "slug": slug,
                "profit": format_decimal(stats.profit),
                "roi": _percent_str(stats.roi),
                "buy_usdc": format_decimal(stats.buy_usdc),
                "sell_usdc": format_decimal(stats.sell_usdc),
                "avg_buy_price": format_decimal(stats.avg_buy_price),
                "avg_sell_price": format_decimal(stats.avg_sell_price),
                "avg_buy_amount": format_decimal(stats.avg_buy_amount),
                "trade_count": stats.count,
            }
            for idx, (slug, stats) in enumerate(profit_leaderboard)
        ],
        loss_leaderboard=[
            {
                "ranking": idx + 1,
                "slug": slug,
                "profit": format_decimal(stats.profit),
                "roi": _percent_str(stats.roi),
                "buy_usdc": format_decimal(stats.buy_usdc),
                "sell_usdc": format_decimal(stats.sell_usdc),
                "avg_buy_price": format_decimal(stats.avg_buy_price),
                "avg_sell_price": format_decimal(stats.avg_sell_price),
                "avg_buy_amount": format_decimal(stats.avg_buy_amount),
                "trade_count": stats.count,
            }
            for idx, (slug, stats) in enumerate(loss_leaderboard)
        ],
    )

    return response
