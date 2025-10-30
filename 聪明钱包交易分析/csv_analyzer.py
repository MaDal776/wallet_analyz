import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN, getcontext
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from datetime import datetime

getcontext().prec = 28


@dataclass
class SlugStats:
    count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    buy_usdc: Decimal = Decimal("0")
    sell_usdc: Decimal = Decimal("0")

    buy_size: Decimal = Decimal("0")
    sell_size: Decimal = Decimal("0")
    buy_price_total: Decimal = Decimal("0")
    sell_price_total: Decimal = Decimal("0")

    def update(self, side: str, usdc_size: Decimal, size: Decimal, price: Decimal) -> None:
        self.count += 1
        if side == "BUY":
            self.buy_count += 1
            self.buy_usdc += usdc_size
            self.buy_size += size
            self.buy_price_total += price * size
        elif side == "SELL":
            self.sell_count += 1
            self.sell_usdc += usdc_size
            self.sell_size += size
            self.sell_price_total += price * size

    @property
    def profit(self) -> Decimal:
        return self.sell_usdc - self.buy_usdc

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

    @property
    def net_profit(self) -> Decimal:
        return self.total_sell_usdc - self.total_buy_usdc


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


@dataclass
class AggregateResult:
    slug_stats: Dict[str, SlugStats]
    global_stats: GlobalStats
    daily_stats: Dict[str, DailyStats]
    hourly_stats: Dict[int, HourlyStats]


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


def aggregate_slug_stats(csv_paths: Iterable[Path]) -> AggregateResult:
    slug_stats: Dict[str, SlugStats] = defaultdict(SlugStats)
    daily_stats: Dict[str, DailyStats] = {}
    hourly_stats: Dict[int, HourlyStats] = {hour: HourlyStats(hour) for hour in range(24)}
    global_stats = GlobalStats()

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

                global_stats.total_trades += 1
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
                        day_stats = daily_stats.setdefault(date_key, DailyStats(date_key))
                        day_stats.trade_count += 1
                        if side == "BUY":
                            day_stats.buy_trades += 1
                            day_stats.buy_usdc += usdc_size
                        elif side == "SELL":
                            day_stats.sell_trades += 1
                            day_stats.sell_usdc += usdc_size

                        hour_stats = hourly_stats.get(dt.hour)
                        if hour_stats is not None:
                            hour_stats.trade_count += 1
                            if side == "BUY":
                                hour_stats.buy_trades += 1
                            elif side == "SELL":
                                hour_stats.sell_trades += 1
                    except ValueError:
                        pass

                slug_stats[slug].update(side, usdc_size, size, price)

    return AggregateResult(
        slug_stats=dict(slug_stats),
        global_stats=global_stats,
        daily_stats=daily_stats,
        hourly_stats=hourly_stats,
    )


def format_decimal(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    quantized = value.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    return f"{quantized.normalize():f}"


def print_global_summary(stats: GlobalStats) -> None:
    print("=== 全局统计 ===")
    print(f"总交易次数: {stats.total_trades}")
    print(f"买入次数: {stats.total_buy_trades}, 买入金额: {format_decimal(stats.total_buy_usdc)}")
    print(f"卖出次数: {stats.total_sell_trades}, 卖出金额: {format_decimal(stats.total_sell_usdc)}")
    print(f"整体利润: {format_decimal(stats.net_profit)}")


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

    header = f"{'排名':>4}  {'slug':<60}  {'成交额':>15}  {'占比':>10}"
    print(header)
    print("-" * len(header))
    for idx, (slug, stats) in enumerate(sorted_by_volume, start=1):
        ratio = (stats.total_volume / total_volume * Decimal("100")).quantize(Decimal("0.01"))
        print(
            f"{idx:>4}  {slug:<60}  {format_decimal(stats.total_volume):>15}  {ratio:>9}%"
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
        f"{'排名':>4}  {'slug':<60}  {'利润':>15}  {'买入金额':>15}  "
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
    print_market_concentration(result.slug_stats, args.market_top)
    print_hourly_distribution(result.hourly_stats)
    print_summary(result.slug_stats, args.top)


if __name__ == "__main__":
    main()
