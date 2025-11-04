from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator, validator


class AnalysisRequest(BaseModel):
    address: str = Field(..., description="钱包地址")
    start_date: Optional[date] = Field(None, description="起始日期，格式 YYYY-MM-DD（默认当天）")
    end_date: Optional[date] = Field(None, description="结束日期，格式 YYYY-MM-DD（默认为起始日期）")
    max_workers: int = Field(4, ge=1, le=16, description="并行抓取线程数，默认 4")

    @validator("address")
    def validate_address(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("钱包地址不能为空")
        if not trimmed.startswith("0x"):
            raise ValueError("钱包地址格式不正确，应以 0x 开头")
        return trimmed.lower()

    @root_validator(pre=True)
    def default_dates(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        start_date = values.get("start_date")
        end_date = values.get("end_date")
        if start_date is None and end_date is None:
            today = date.today()
            values["start_date"] = today
            values["end_date"] = today
        elif start_date is None:
            values["start_date"] = end_date
        elif end_date is None:
            values["end_date"] = start_date
        return values

    @root_validator
    def check_date_range(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        start_date = values.get("start_date")
        end_date = values.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise ValueError("结束日期不能早于起始日期")
        return values


class GlobalSummary(BaseModel):
    total_trades: int
    total_buy_trades: int
    total_sell_trades: int
    total_buy_usdc: str
    total_sell_usdc: str
    net_profit: str
    roi: Optional[str]
    avg_profit_per_trade: Optional[str]
    total_redeem_trades: int
    redeem_ratio: Optional[str]


class DailyRecord(BaseModel):
    date: str
    trade_count: int
    buy_usdc: str
    sell_usdc: str
    profit: str


class DailySummary(BaseModel):
    total_days: int
    total_buy: str
    total_sell: str
    total_profit: str
    top_profitable_days: List[DailyRecord]
    top_loss_days: List[DailyRecord]


class HourlyRecord(BaseModel):
    hour: int
    trade_count: int
    buy_trades: int
    sell_trades: int
    ratio: str


class MarketVolumeRecord(BaseModel):
    ranking: int
    slug: str
    total_volume: str
    ratio: str


class NetPositionRecord(BaseModel):
    ranking: int
    slug: str
    net_position: str


class MarketConcentration(BaseModel):
    top_by_volume: List[MarketVolumeRecord]
    top_by_net_position: List[NetPositionRecord]


class MonthlyMarketRecord(BaseModel):
    month: str
    ranking: int
    token: str
    duration: str
    settlement: str
    trade_count: int
    buy_usdc: str
    sell_usdc: str
    profit: str
    roi: Optional[str]
    redeem_count: int
    redeem_ratio: Optional[str]


class LeaderboardEntry(BaseModel):
    ranking: int
    slug: str
    profit: Optional[str]
    roi: Optional[str]
    buy_usdc: Optional[str]
    sell_usdc: Optional[str]
    avg_buy_price: Optional[str]
    avg_sell_price: Optional[str]
    avg_buy_amount: Optional[str]
    trade_count: Optional[int]


class AnalysisResponse(BaseModel):
    metadata: Dict[str, Any]
    global_summary: GlobalSummary
    daily_summary: DailySummary
    hourly_distribution: List[HourlyRecord]
    market_concentration: MarketConcentration
    monthly_market: List[MonthlyMarketRecord]
    roi_leaderboard: List[LeaderboardEntry]
    profit_leaderboard: List[LeaderboardEntry]
    loss_leaderboard: List[LeaderboardEntry]
