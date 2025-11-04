export interface AnalysisRequestPayload {
  address: string;
  start_date: string;
  end_date: string;
  max_workers: number;
}

export interface Metadata {
  address: string;
  start_date: string;
  end_date: string;
  generated_at: string;
}

export interface GlobalSummary {
  total_trades: number;
  total_buy_trades: number;
  total_sell_trades: number;
  total_buy_usdc: string;
  total_sell_usdc: string;
  net_profit: string;
  roi: string | null;
  avg_profit_per_trade: string | null;
  total_redeem_trades: number;
  redeem_ratio: string | null;
}

export interface DailyRecord {
  date: string;
  trade_count: number;
  buy_usdc: string;
  sell_usdc: string;
  profit: string;
}

export interface DailySummary {
  total_days: number;
  total_buy: string;
  total_sell: string;
  total_profit: string;
  top_profitable_days: DailyRecord[];
  top_loss_days: DailyRecord[];
}

export interface HourlyRecord {
  hour: number;
  trade_count: number;
  buy_trades: number;
  sell_trades: number;
  ratio: string | null;
}

export interface MarketVolumeRecord {
  ranking: number;
  slug: string;
  total_volume: string;
  ratio: string | null;
}

export interface NetPositionRecord {
  ranking: number;
  slug: string;
  net_position: string;
}

export interface MarketConcentration {
  top_by_volume: MarketVolumeRecord[];
  top_by_net_position: NetPositionRecord[];
}

export interface MonthlyMarketRecord {
  month: string;
  ranking: number;
  token: string;
  duration: string;
  settlement: string;
  trade_count: number;
  buy_usdc: string;
  sell_usdc: string;
  profit: string;
  roi: string | null;
  redeem_count: number;
  redeem_ratio: string | null;
}

export interface LeaderboardEntry {
  ranking: number;
  slug: string;
  profit: string | null;
  roi: string | null;
  buy_usdc: string | null;
  sell_usdc: string | null;
  avg_buy_price: string | null;
  avg_sell_price: string | null;
  avg_buy_amount: string | null;
  trade_count: number | null;
}

export interface AnalysisResponse {
  metadata: Metadata;
  global_summary: GlobalSummary;
  daily_summary: DailySummary;
  hourly_distribution: HourlyRecord[];
  market_concentration: MarketConcentration;
  monthly_market: MonthlyMarketRecord[];
  roi_leaderboard: LeaderboardEntry[];
  profit_leaderboard: LeaderboardEntry[];
  loss_leaderboard: LeaderboardEntry[];
}
