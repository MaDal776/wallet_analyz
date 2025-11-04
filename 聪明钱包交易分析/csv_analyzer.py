import argparse
import csv
from collections import defaultdict
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_DOWN, getcontext
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from datetime import datetime

getcontext().prec = 28


@dataclass
class SlugStats:
    count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    buy_usdc: Decimal = Decimal("0")
    sell_usdc: Decimal = Decimal("0")

    invested_usdc: Decimal = Decimal("0")
    realized_usdc: Decimal = Decimal("0")

    unique_trade_keys: Set[Tuple[str, Decimal]] = field(default_factory=set)

    buy_size: Decimal = Decimal("0")
    sell_size: Decimal = Decimal("0")
    buy_price_total: Decimal = Decimal("0")
    sell_price_total: Decimal = Decimal("0")

    def register_trade(self, side: str, price: Decimal) -> bool:
        key = (side, price)
        if key in self.unique_trade_keys:
            return False
        self.unique_trade_keys.add(key)
        self.count += 1
        return True

    def update(self, side: str, usdc_size: Decimal, size: Decimal, price: Decimal) -> None:
        if side == "BUY":
            self.buy_count += 1
            self.buy_usdc += usdc_size
            self.invested_usdc += usdc_size
            self.buy_size += size
            self.buy_price_total += price * size
        elif side == "SELL":
            self.sell_count += 1
            self.sell_usdc += usdc_size
            self.realized_usdc += usdc_size
            self.sell_size += size
            self.sell_price_total += price * size

    @property
    def profit(self) -> Decimal:
        return self.sell_usdc - self.buy_usdc

    @property
    def roi(self) -> Optional[Decimal]:
        if self.invested_usdc == 0:
            return None
        return (self.realized_usdc - self.invested_usdc) / self.invested_usdc

    @property
    def avg_buy_price(self) -> Optional[Decimal]:
        if self.buy_size == 0:
            return None
        return self.buy_price_total / self.buy_size

    @property
    def avg_sell_price(self) -> Optional[Decimal]:
        if self.sell_size == 0:
            return None
        return self.sell_price_total / self.sell_size

    @property
    def avg_buy_amount(self) -> Optional[Decimal]:
        if self.buy_count == 0:
            return None
        return self.buy_usdc / Decimal(self.buy_count)

    @property
    def total_volume(self) -> Decimal:
        return self.buy_usdc + self.sell_usdc

    @property
    def net_position(self) -> Decimal:
        return self.sell_size - self.buy_size


@dataclass
class GlobalStats:
    total_trades: int = 0
    total_buy_trades: int = 0
    total_sell_trades: int = 0
    total_buy_usdc: Decimal = Decimal("0")
    total_sell_usdc: Decimal = Decimal("0")
    total_redeem_trades: int = 0

    @property
    def net_profit(self) -> Decimal:
        return self.total_sell_usdc - self.total_buy_usdc

    @property
    def roi(self) -> Optional[Decimal]:
        if self.total_buy_usdc == 0:
            return None
        return self.net_profit / self.total_buy_usdc

    @property
    def avg_profit_per_trade(self) -> Optional[Decimal]:
        if self.total_trades == 0:
            return None
        return self.net_profit / Decimal(self.total_trades)

    @property
    def redeem_ratio(self) -> Optional[Decimal]:
        if self.total_trades == 0:
            return None
        return Decimal(self.total_redeem_trades) / Decimal(self.total_trades)


@dataclass
class DailyStats:
    date_str: str
    trade_count: int = 0
    buy_trades: int = 0
    sell_trades: int = 0
    buy_usdc: Decimal = Decimal("0")
    sell_usdc: Decimal = Decimal("0")

    @property
    def profit(self) -> Decimal:
        return self.sell_usdc - self.buy_usdc


@dataclass
class HourlyStats:
    hour: int
    trade_count: int = 0
    buy_trades: int = 0
    sell_trades: int = 0


@dataclass(frozen=True)
class MarketCategory:
    token: str = "UNKNOWN"
    duration: str = "UNKNOWN"
    settlement: str = "UNKNOWN"


@dataclass
class MonthlyMarketStats:
    month: str
    category: MarketCategory
    trade_count: int = 0
    buy_usdc: Decimal = field(default_factory=lambda: Decimal("0"))
    sell_usdc: Decimal = field(default_factory=lambda: Decimal("0"))
    invested_usdc: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_usdc: Decimal = field(default_factory=lambda: Decimal("0"))
    redeem_count: int = 0

    @property
    def profit(self) -> Decimal:
        return self.sell_usdc - self.buy_usdc

    @property
    def roi(self) -> Optional[Decimal]:
        if self.invested_usdc == 0:
            return None
        return (self.realized_usdc - self.invested_usdc) / self.invested_usdc

    @property
    def redeem_ratio(self) -> Optional[Decimal]:
        if self.trade_count == 0:
            return None
        return Decimal(self.redeem_count) / Decimal(self.trade_count)


@dataclass
class AggregateResult:
    slug_stats: Dict[str, SlugStats]
    global_stats: GlobalStats
    daily_stats: Dict[str, DailyStats]
    hourly_stats: Dict[int, HourlyStats]
    monthly_stats: Dict[Tuple[str, MarketCategory], MonthlyMarketStats]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="聚合 CSV 交易数据，输出交易频率与利润榜"
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("./data"),
        help="CSV 文件所在目录，默认 ./data"
    )
    parser.add_argument(
        "--pattern",
        default="*.csv",
        help="匹配 CSV 文件的 glob 模式，默认 *.csv"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="利润榜输出条数，默认 10"
    )
    parser.add_argument(
        "--daily-top",
        type=int,
        default=5,
        help="每日盈亏榜展示条数，默认 5"
    )
    parser.add_argument(
        "--market-top",
        type=int,
        default=10,
        help="市场集中度与净头寸榜展示条数，默认 10"
    )
    parser.add_argument(
        "--monthly-limit",
        type=int,
        default=10,
        help="每月市场类型统计展示条数，默认 10"
    )
    parser.add_argument(
        "--roi-top",
        type=int,
        default=10,
        help="ROI 榜展示条数，默认 10"
    )
    return parser.parse_args()


def collect_csv_paths(directory: Path, pattern: str) -> List[Path]:
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"目录不存在: {directory}")
    return sorted(p for p in directory.glob(pattern) if p.is_file())


def safe_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal("0")


TOKEN_KEYWORDS = {
    "BTC": ("btc", "bitcoin"),
    "ETH": ("eth", "ethereum"),
    "SOL": ("sol",),
    "XRP": ("xrp",),
    "ADA": ("ada",),
    "DOGE": ("doge",),
}

SETTLEMENT_KEYWORDS = {
    "UPDOWN": ("updown",),
    "UP-OR-DOWN": ("up-or-down",),
    "UP-OR-DOWN-LONG": ("up-or-down-long",),
    "CLASSIC": ("classic",),
}


def parse_market_category(slug: str) -> MarketCategory:
    lowered = slug.lower()

    token = "OTHER"
    for key, variants in TOKEN_KEYWORDS.items():
        if any(variant in lowered for variant in variants):
            token = key
            break

    settlement = "UNKNOWN"
    duration = "UNKNOWN"

    if "updown" in lowered:
        settlement = "UPDOWN"
        duration = "15M"
    elif "up-or-down" in lowered:
        settlement = "UP-OR-DOWN"
        duration = "1H"
    else:
        duration_match = re.search(r"(\d+)(m|h|d)", lowered)
        duration = duration_match.group(0).upper() if duration_match else "UNKNOWN"
        for key, variants in SETTLEMENT_KEYWORDS.items():
            if any(variant in lowered for variant in variants):
                settlement = key
                break

    return MarketCategory(token=token, duration=duration, settlement=settlement)


def aggregate_slug_stats(csv_paths: Iterable[Path]) -> AggregateResult:
    slug_stats: Dict[str, SlugStats] = defaultdict(SlugStats)
    daily_stats: Dict[str, DailyStats] = {}
    hourly_stats: Dict[int, HourlyStats] = {hour: HourlyStats(hour) for hour in range(24)}
    global_stats = GlobalStats()
    monthly_stats: Dict[Tuple[str, MarketCategory], MonthlyMarketStats] = {}

    global_seen: Set[Tuple[str, str, Decimal]] = set()
    daily_seen: Dict[str, Set[Tuple[str, str, Decimal]]] = defaultdict(set)
    hourly_seen: Dict[int, Set[Tuple[str, str, Decimal]]] = defaultdict(set)
    monthly_seen: Dict[Tuple[str, MarketCategory], Set[Tuple[str, str, Decimal]]] = defaultdict(set)

    for path in csv_paths:
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            expected_fields = {"slug", "type", "side", "size", "usdcSize", "price", "cst_time"}
            if not expected_fields.issubset(reader.fieldnames or []):
                raise ValueError(f"文件 {path} 缺少必要字段: {expected_fields - set(reader.fieldnames or [])}")
            for row in reader:
                slug = row.get("slug", "").strip()
                if not slug:
                    continue

                side = row.get("side", "").strip().upper()
                trade_type = row.get("type", "").strip().upper()
                size = safe_decimal(row.get("size", "0"))
                if trade_type == "REDEEM":
                    side = "SELL"
                    price = Decimal("1")
                    usdc_size = size
                else:
                    price = safe_decimal(row.get("price", "0"))
                    usdc_size = safe_decimal(row.get("usdcSize", "0"))

                price_key = price
                unique_key = (slug, side, price_key)
                is_new_global = False
                if unique_key not in global_seen:
                    global_seen.add(unique_key)
                    global_stats.total_trades += 1
                    is_new_global = True
                if trade_type == "REDEEM" and is_new_global:
                    global_stats.total_redeem_trades += 1
                if side == "BUY":
                    global_stats.total_buy_trades += 1
                    global_stats.total_buy_usdc += usdc_size
                elif side == "SELL":
                    global_stats.total_sell_trades += 1
                    global_stats.total_sell_usdc += usdc_size

                cst_time = row.get("cst_time", "").strip()
                if cst_time:
                    try:
                        dt = datetime.strptime(cst_time, "%Y-%m-%d %H:%M:%S")
                        date_key = dt.strftime("%Y-%m-%d")
                        month_key = dt.strftime("%Y-%m")
                        day_stats = daily_stats.setdefault(date_key, DailyStats(date_key))
                        if unique_key not in daily_seen[date_key]:
                            daily_seen[date_key].add(unique_key)
                            day_stats.trade_count += 1
                        if side == "BUY":
                            day_stats.buy_trades += 1
                            day_stats.buy_usdc += usdc_size
                        elif side == "SELL":
                            day_stats.sell_trades += 1
                            day_stats.sell_usdc += usdc_size

                        hour_stats = hourly_stats.get(dt.hour)
                        if hour_stats is not None:
                            if unique_key not in hourly_seen[dt.hour]:
                                hourly_seen[dt.hour].add(unique_key)
                                hour_stats.trade_count += 1
                            if side == "BUY":
                                hour_stats.buy_trades += 1
                            elif side == "SELL":
                                hour_stats.sell_trades += 1

                        category = parse_market_category(slug)
                        key = (month_key, category)
                        month_stats = monthly_stats.setdefault(key, MonthlyMarketStats(month_key, category))
                        is_new_monthly = False
                        if unique_key not in monthly_seen[key]:
                            monthly_seen[key].add(unique_key)
                            month_stats.trade_count += 1
                            is_new_monthly = True
                        if side == "BUY":
                            month_stats.buy_usdc += usdc_size
                            month_stats.invested_usdc += usdc_size
                        elif side == "SELL":
                            month_stats.sell_usdc += usdc_size
                            month_stats.realized_usdc += usdc_size
                            if trade_type == "REDEEM" and is_new_monthly:
                                month_stats.redeem_count += 1
                    except ValueError:
                        pass

                slug_stats[slug].register_trade(side, price_key)
                slug_stats[slug].update(side, usdc_size, size, price)

    return AggregateResult(
        slug_stats=dict(slug_stats),
        global_stats=global_stats,
        daily_stats=daily_stats,
        hourly_stats=hourly_stats,
        monthly_stats=monthly_stats,
    )


def format_decimal(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    quantized = value.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    return f"{quantized.normalize():f}"


def format_decimal_percent(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    percent = (value * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return f"{percent} %"


def print_global_summary(stats: GlobalStats) -> None:
    print("=== 全局统计 ===")
    print(f"总交易次数: {stats.total_trades}")
    print(f"买入次数: {stats.total_buy_trades}, 买入金额: {format_decimal(stats.total_buy_usdc)}")
    print(f"卖出次数: {stats.total_sell_trades}, 卖出金额: {format_decimal(stats.total_sell_usdc)}")
    print(f"整体利润: {format_decimal(stats.net_profit)}")
    roi = stats.roi
    if roi is not None:
        print(f"整体 ROI: {format_decimal_percent(roi)}")
    avg_profit = stats.avg_profit_per_trade
    if avg_profit is not None:
        print(f"单笔平均利润: {format_decimal(avg_profit)}")
    redeem_ratio = stats.redeem_ratio
    print(
        f"REDEEM 次数: {stats.total_redeem_trades}"
        + (f"，占比: {format_decimal_percent(redeem_ratio)}" if redeem_ratio is not None else "")
    )


def print_daily_summary(daily_stats: Dict[str, DailyStats], top_n: int) -> None:
    if not daily_stats:
        print("未找到每日统计数据")
        return

    print("\n=== 每日盈亏概览 ===")
    total_days = len(daily_stats)
    total_buy = sum(day.buy_usdc for day in daily_stats.values())
    total_sell = sum(day.sell_usdc for day in daily_stats.values())
    total_profit = sum(day.profit for day in daily_stats.values())
    print(f"覆盖天数: {total_days}")
    print(f"累计买入: {format_decimal(total_buy)}, 累计卖出: {format_decimal(total_sell)}, 总利润: {format_decimal(total_profit)}")

    def _print_days(title: str, items: List[DailyStats]) -> None:
        print(f"\n{title}")
        header = f"{'日期':<12}  {'交易数':>6}  {'买入金额':>15}  {'卖出金额':>15}  {'利润':>15}"
        print(header)
        print("-" * len(header))
        for day in items:
            print(
                f"{day.date_str:<12}  {day.trade_count:>6}  "
                f"{format_decimal(day.buy_usdc):>15}  {format_decimal(day.sell_usdc):>15}  {format_decimal(day.profit):>15}"
            )

    sorted_by_profit = sorted(daily_stats.values(), key=lambda d: d.profit, reverse=True)[:top_n]
    _print_days("盈利最高的日子:", sorted_by_profit)

    sorted_by_loss = sorted(daily_stats.values(), key=lambda d: d.profit)[:top_n]
    _print_days("亏损最大的日子:", sorted_by_loss)


def print_market_concentration(slug_stats: Dict[str, SlugStats], top_n: int) -> None:
    if not slug_stats:
        return

    print("\n=== 市场成交额集中度 ===")
    total_volume = sum(slug.total_volume for slug in slug_stats.values())
    if total_volume == 0:
        print("无成交额数据")
        return

    sorted_by_volume = sorted(
        slug_stats.items(),
        key=lambda item: item[1].total_volume,
        reverse=True
    )[:top_n]

    header = f"{'排名':>4}  {'slug':<60}  {'成交额':>15}  {'占比':>10}  {'ROI':>12}"
    print(header)
    print("-" * len(header))
    for idx, (slug, stats) in enumerate(sorted_by_volume, start=1):
        ratio = (stats.total_volume / total_volume * Decimal("100")).quantize(Decimal("0.01"))
        roi = stats.roi
        roi_str = format_decimal_percent(roi)
        print(
            f"{idx:>4}  {slug:<60}  {format_decimal(stats.total_volume):>15}  {ratio:>9}%  {roi_str:>12}"
        )

    print("\n=== 净头寸最大的市场 ===")
    sorted_by_position = sorted(
        slug_stats.items(),
        key=lambda item: abs(item[1].net_position),
        reverse=True
    )[:top_n]
    header_pos = f"{'排名':>4}  {'slug':<60}  {'净头寸(SELL-BUY)':>20}"
    print(header_pos)
    print("-" * len(header_pos))
    for idx, (slug, stats) in enumerate(sorted_by_position, start=1):
        print(f"{idx:>4}  {slug:<60}  {format_decimal(stats.net_position):>20}")


def print_hourly_distribution(hourly_stats: Dict[int, HourlyStats]) -> None:
    if not hourly_stats:
        return

    print("\n=== 交易时段分布 (CST) ===")
    total_trades = sum(stat.trade_count for stat in hourly_stats.values())
    if total_trades == 0:
        print("无时段数据")
        return

    header = f"{'小时':>4}  {'交易数':>6}  {'买入数':>6}  {'卖出数':>6}  {'占比':>8}"
    print(header)
    print("-" * len(header))
    for hour in range(24):
        stat = hourly_stats.get(hour) or HourlyStats(hour)
        ratio = Decimal(stat.trade_count) / Decimal(total_trades) * Decimal("100") if total_trades else Decimal("0")
        ratio = ratio.quantize(Decimal("0.01"))
        print(
            f"{hour:>4}  {stat.trade_count:>6}  {stat.buy_trades:>6}  {stat.sell_trades:>6}  {ratio:>7}%"
        )


def print_monthly_market_summary(
    monthly_stats: Dict[Tuple[str, MarketCategory], MonthlyMarketStats],
    limit: int,
) -> None:
    if not monthly_stats:
        print("\n未找到任何月度市场类型统计")
        return

    print("\n=== 按月市场类型获利统计 ===")
    grouped: Dict[str, List[MonthlyMarketStats]] = defaultdict(list)
    for (month, _), stats in monthly_stats.items():
        if stats.profit > 0:
            grouped[month].append(stats)

    if not grouped:
        print("无盈利市场类型记录")
        return

    for month in sorted(grouped.keys()):
        entries = grouped[month]
        entries.sort(key=lambda s: s.profit, reverse=True)
        print(f"\n[{month}]")
        header = (
            f"{'排名':>4}  {'币种':<6}  {'时间频率':<10}  {'结算类型':<15}  "
            f"{'交易数':>6}  {'买入金额':>15}  {'卖出金额':>15}  {'利润':>15}  {'ROI':>12}  {'REDEEM次数':>10}  {'REDEEM占比':>12}"
        )
        print(header)
        print("-" * len(header))
        for idx, stat in enumerate(entries[:limit], start=1):
            roi = stat.roi
            roi_str = format_decimal_percent(roi)
            redeem_ratio = stat.redeem_ratio
            redeem_ratio_str = format_decimal_percent(redeem_ratio)
            print(
                f"{idx:>4}  {stat.category.token:<6}  {stat.category.duration:<10}  {stat.category.settlement:<15}  "
                f"{stat.trade_count:>6}  {format_decimal(stat.buy_usdc):>15}  "
                f"{format_decimal(stat.sell_usdc):>15}  {format_decimal(stat.profit):>15}  "
                f"{roi_str:>12}  {stat.redeem_count:>10}  {redeem_ratio_str:>12}"
            )


def print_roi_leaderboard(stats: Dict[str, SlugStats], top_n: int) -> None:
    if not stats:
        return

    roi_candidates = [item for item in stats.items() if item[1].roi is not None]
    if not roi_candidates:
        print("\n无可用 ROI 数据")
        return

    print("\n=== ROI 榜 ===")
    roi_candidates.sort(key=lambda item: item[1].roi, reverse=True)
    header = (
        f"{'排名':>4}  {'slug':<60}  {'ROI':>12}  {'利润':>15}  "
        f"{'买入金额':>15}  {'卖出金额':>15}  {'交易次数':>6}"
    )
    print(header)
    print("-" * len(header))
    for idx, (slug, slug_stats) in enumerate(roi_candidates[:top_n], start=1):
        print(
            f"{idx:>4}  {slug:<60}  {format_decimal_percent(slug_stats.roi):>12}  "
            f"{format_decimal(slug_stats.profit):>15}  {format_decimal(slug_stats.buy_usdc):>15}  "
            f"{format_decimal(slug_stats.sell_usdc):>15}  {slug_stats.count:>6}"
        )


def print_summary(stats: Dict[str, SlugStats], top_n: int) -> None:
    if not stats:
        print("未找到任何 slug 数据")
        return

    total_markets = len(stats)
    print(f"共找到 {total_markets} 个市场 (slug)")

    top_frequency_slug = max(stats.items(), key=lambda item: item[1].count)
    freq_slug, freq_stats = top_frequency_slug
    print("\n交易频率最高的 slug:")
    print(f"  slug: {freq_slug}")
    print(f"  交易次数: {freq_stats.count}")
    print(f"  买入次数: {freq_stats.buy_count}, 买入金额: {format_decimal(freq_stats.buy_usdc)}")
    print(f"  卖出次数: {freq_stats.sell_count}, 卖出金额: {format_decimal(freq_stats.sell_usdc)}")
    print(f"  ROI: {format_decimal_percent(freq_stats.roi)}")

    print("\n利润最高的前 {} 个 slug:".format(top_n))
    sorted_by_profit = sorted(
        stats.items(),
        key=lambda item: item[1].profit,
        reverse=True
    )[:top_n]
    if not sorted_by_profit:
        print("  无利润数据")
        return

    header = (
        f"{'排名':>4}  {'slug':<60}  {'利润':>15}  {'ROI':>12}  {'买入金额':>15}  "
        f"{'卖出金额':>15}  {'均价(BUY)':>15}  {'均价(SELL)':>15}  "
        f"{'单笔买入均额':>15}  {'交易次数':>6}"
    )
    print(header)
    print("-" * len(header))
    for idx, (slug, slug_stats) in enumerate(sorted_by_profit, start=1):
        print(
            f"{idx:>4}  "
            f"{slug:<60}  "
            f"{format_decimal(slug_stats.profit):>15}  "
            f"{format_decimal_percent(slug_stats.roi):>12}  "
            f"{format_decimal(slug_stats.buy_usdc):>15}  "
            f"{format_decimal(slug_stats.sell_usdc):>15}  "
            f"{format_decimal(slug_stats.avg_buy_price):>15}  "
            f"{format_decimal(slug_stats.avg_sell_price):>15}  "
            f"{format_decimal(slug_stats.avg_buy_amount):>15}  "
            f"{slug_stats.count:>6}"
        )

    sorted_by_loss = sorted(
        stats.items(),
        key=lambda item: item[1].profit
    )[:top_n]
    print("\n亏损最大的前 {} 个 slug:".format(top_n))
    print(header)
    print("-" * len(header))
    for idx, (slug, slug_stats) in enumerate(sorted_by_loss, start=1):
        print(
            f"{idx:>4}  "
            f"{slug:<60}  "
            f"{format_decimal(slug_stats.profit):>15}  "
            f"{format_decimal_percent(slug_stats.roi):>12}  "
            f"{format_decimal(slug_stats.buy_usdc):>15}  "
            f"{format_decimal(slug_stats.sell_usdc):>15}  "
            f"{format_decimal(slug_stats.avg_buy_price):>15}  "
            f"{format_decimal(slug_stats.avg_sell_price):>15}  "
            f"{slug_stats.count:>6}"
        )


def main() -> None:
    args = parse_args()
    csv_paths = collect_csv_paths(args.directory, args.pattern)
    if not csv_paths:
        print(f"目录 {args.directory} 中未找到匹配 {args.pattern} 的 CSV 文件")
        return

    result = aggregate_slug_stats(csv_paths)
    print_global_summary(result.global_stats)
    print_daily_summary(result.daily_stats, args.daily_top)
    print_monthly_market_summary(result.monthly_stats, args.monthly_limit)
    print_market_concentration(result.slug_stats, args.market_top)
    print_hourly_distribution(result.hourly_stats)
    print_roi_leaderboard(result.slug_stats, args.roi_top)
    print_summary(result.slug_stats, args.top)


if __name__ == "__main__":
    main()
