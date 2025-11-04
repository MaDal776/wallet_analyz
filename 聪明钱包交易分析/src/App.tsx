import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import clsx from 'clsx';
import type {
  AnalysisRequestPayload,
  AnalysisResponse,
  DailyRecord,
  LeaderboardEntry,
  MarketVolumeRecord,
  NetPositionRecord,
  HourlyRecord,
} from './types';

const todayStr = () => new Date().toISOString().slice(0, 10);

const rawApiBase = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '').trim();
const apiBaseUrl = rawApiBase ? rawApiBase.replace(/\/+$/, '') : '';
const resolveApiUrl = (path: string) => {
  if (!apiBaseUrl) {
    return path;
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${apiBaseUrl}${normalizedPath}`;
};

const StatCard = ({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string | number | null;
  subtitle?: string;
}) => (
  <div className="rounded-2xl bg-card p-5 shadow-card border border-white/5">
    <div className="mb-1 text-sm font-medium uppercase tracking-wide text-textSecondary">
      {title}
    </div>
    <div className="text-2xl font-semibold text-textPrimary">{String(value ?? '-') }</div>
    {subtitle ? (
      <div className="mt-1 text-xs text-textSecondary">{subtitle}</div>
    ) : null}
  </div>
);

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="mt-10">
    <div className="mb-4 flex items-center justify-between">
      <h2 className="text-xl font-semibold text-textPrimary">{title}</h2>
      <div className="h-px flex-1 bg-white/10 ml-6" />
    </div>
    <div className="rounded-2xl bg-card/70 p-6 shadow-card border border-white/5">
      {children}
    </div>
  </section>
);

const HourlyDistribution = ({ records }: { records: HourlyRecord[] }) => {
  const sorted = [...records].sort((a, b) => a.hour - b.hour);
  const maxTrades = Math.max(1, ...sorted.map((record) => record.trade_count));
  const totalTrades = sorted.reduce((sum, record) => sum + record.trade_count, 0);

  const intensityColor = (value: number) => {
    const ratio = maxTrades === 0 ? 0 : value / maxTrades;
    const alpha = 0.15 + ratio * 0.85;
    return `rgba(91, 140, 255, ${alpha.toFixed(2)})`;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between text-sm text-textSecondary">
        <span>共 {totalTrades} 笔交易，颜色越深表示该时段交易越活跃。</span>
        <div className="hidden items-center gap-2 text-xs sm:flex">
          <span>低</span>
          <div className="h-2 w-16 rounded-full bg-gradient-to-r from-accent/20 via-accent/60 to-accent" />
          <span>高</span>
        </div>
      </div>
      <div className="grid grid-cols-6 gap-1 sm:grid-cols-8 md:grid-cols-12">
        {sorted.map((record) => {
          const color = intensityColor(record.trade_count);
          return (
            <div
              key={record.hour}
              className="group relative flex h-10 w-10 flex-col items-center justify-center rounded-lg border border-white/5 text-[11px] font-medium text-textPrimary"
              style={{ backgroundColor: color }}
            >
              <span>{record.hour.toString().padStart(2, '0')}</span>
              <span className="text-[10px] text-textSecondary">{record.trade_count}</span>
              <div className="pointer-events-none absolute -top-2 left-1/2 z-10 hidden w-max -translate-x-1/2 -translate-y-full rounded-xl border border-white/10 bg-background/95 px-3 py-2 text-[11px] text-textSecondary shadow-card group-hover:block">
                <div className="text-textPrimary font-semibold mb-1">{record.hour.toString().padStart(2, '0')}:00</div>
                <div>占比 {formatNullable(record.ratio)}</div>
                <div>交易数 {record.trade_count}</div>
                <div>买 {record.buy_trades} / 卖 {record.sell_trades}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const Table = <T extends object>({
  columns,
  data,
  keyExtractor,
}: {
  columns: { key: keyof T | string; header: string; className?: string; render?: (row: T) => React.ReactNode }[];
  data: T[];
  keyExtractor: (row: T, index: number) => string | number;
}) => (
  <div className="overflow-x-auto">
    <table className="min-w-full divide-y divide-white/10 text-sm">
      <thead className="bg-white/5 text-textSecondary">
        <tr>
          {columns.map((col) => (
            <th key={String(col.key)} className={clsx('px-4 py-3 text-left font-medium uppercase tracking-wide', col.className)}>
              {col.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-white/5">
        {data.map((row, index) => (
          <tr key={keyExtractor(row, index)} className="text-textPrimary/90">
            {columns.map((col) => (
              <td key={String(col.key)} className={clsx('px-4 py-3 align-middle', col.className)}>
                {col.render ? col.render(row) : ((row as unknown as Record<string, React.ReactNode>)[col.key as string] ?? '-')}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const formatNullable = (value: string | null | undefined) => (value && value !== '-' ? value : '-');

const generateDateRange = (start: string, end: string): string[] => {
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return [];
  }

  const range: string[] = [];
  const current = new Date(startDate);
  while (current <= endDate) {
    range.push(current.toISOString().slice(0, 10));
    current.setDate(current.getDate() + 1);
  }
  return range;
};

function App(): JSX.Element {
  const [form, setForm] = useState<AnalysisRequestPayload>({
    address: '',
    start_date: todayStr(),
    end_date: todayStr(),
    max_workers: 4,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [leaderboardTab, setLeaderboardTab] = useState<'profit' | 'loss'>('profit');
  const [progressDates, setProgressDates] = useState<string[]>([]);
  const [progressIndex, setProgressIndex] = useState(0);
  const progressTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isFormValid = useMemo(() => form.address.trim().startsWith('0x'), [form.address]);

  const progressPercent = useMemo(() => {
    if (!loading || progressDates.length === 0) {
      return 0;
    }
    const safeIndex = Math.min(progressIndex + 1, progressDates.length);
    return Math.min(Math.round((safeIndex / progressDates.length) * 100), 95);
  }, [loading, progressDates, progressIndex]);

  const progressMessage = useMemo(() => {
    if (!loading || progressDates.length === 0) {
      return '';
    }
    const safeIndex = Math.min(progressIndex, progressDates.length - 1);
    const currentDate = progressDates[safeIndex];
    const totalDates = progressDates.length;
    const simulatedRecord = Math.min(499, Math.max(1, Math.round(((safeIndex + 1) / totalDates) * 480)));
    return `正在获取 ${currentDate} 的第 ${simulatedRecord} 条数据（第 ${safeIndex + 1}/${totalDates} 个日期）`;
  }, [loading, progressDates, progressIndex]);

  useEffect(() => {
    if (loading && progressDates.length > 0) {
      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current);
      }
      progressTimerRef.current = setInterval(() => {
        setProgressIndex((prev) => {
          if (prev >= progressDates.length - 1) {
            return prev;
          }
          return prev + 1;
        });
      }, 1200);
    } else if (progressTimerRef.current) {
      clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }

    return () => {
      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current);
        progressTimerRef.current = null;
      }
    };
  }, [loading, progressDates]);

  const handleSubmit = async (evt: FormEvent<HTMLFormElement>) => {
    evt.preventDefault();
    if (!isFormValid) {
      setError('请输入合法的钱包地址（以 0x 开头）');
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    const dates = generateDateRange(form.start_date, form.end_date);
    setProgressDates(dates);
    setProgressIndex(0);
    try {
      const response = await axios.post<AnalysisResponse>(resolveApiUrl('/api/analyze'), form, {
        timeout: 1000 * 60 * 5,
      });
      setData(response.data);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail ?? err.message ?? '请求失败');
      } else {
        setError('请求失败');
      }
    } finally {
      setLoading(false);
      setProgressDates([]);
      setProgressIndex(0);
    }
  };

  const handleChange = <K extends keyof AnalysisRequestPayload>(key: K, value: AnalysisRequestPayload[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="min-h-screen bg-background pb-16">
      <header className="border-b border-white/5 bg-background/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <div>
            <h1 className="text-2xl font-semibold text-textPrimary">聪明钱包分析工具</h1>
            <p className="text-sm text-textSecondary mt-1">
              参考 Polymarket 配色的链上地址分析工具，整合 ROI、REDEEM 占比等指标。
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6">
        <section className="mt-10 rounded-3xl bg-card/80 p-6 shadow-card border border-white/5">
          <form className="grid gap-6 md:grid-cols-2 lg:grid-cols-4" onSubmit={handleSubmit}>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-textSecondary mb-2">钱包地址</label>
              <input
                type="text"
                value={form.address}
                onChange={(e) => handleChange('address', e.target.value)}
                placeholder="0x..."
                className="w-full rounded-xl border border-white/10 bg-background px-4 py-3 text-textPrimary focus:border-accent focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-2">开始日期 (CST)</label>
              <input
                type="date"
                value={form.start_date}
                onChange={(e) => handleChange('start_date', e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-background px-4 py-3 text-textPrimary focus:border-accent focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-2">结束日期 (CST)</label>
              <input
                type="date"
                value={form.end_date}
                min={form.start_date}
                onChange={(e) => handleChange('end_date', e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-background px-4 py-3 text-textPrimary focus:border-accent focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-2">并行线程数</label>
              <input
                type="number"
                min={1}
                max={16}
                value={form.max_workers}
                onChange={(e) => handleChange('max_workers', Number(e.target.value))}
                className="w-full rounded-xl border border-white/10 bg-background px-4 py-3 text-textPrimary focus:border-accent focus:outline-none"
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className={clsx(
                  'inline-flex w-full items-center justify-center rounded-xl bg-accent px-4 py-3 font-semibold text-background transition-colors hover:bg-accentHover',
                  loading && 'opacity-80'
                )}
                disabled={loading}
              >
                {loading ? '分析中…' : '开始分析'}
              </button>
            </div>
          </form>
          {!isFormValid ? (
            <p className="mt-4 text-sm text-danger">钱包地址必须以 0x 开头</p>
          ) : null}
          {error ? (
            <p className="mt-4 text-sm text-danger">{error}</p>
          ) : null}
          {loading && progressDates.length > 0 ? (
            <div className="mt-6 space-y-3 rounded-xl border border-accent/30 bg-background/70 p-4 shadow-card">
              <div className="flex items-center gap-3 text-sm text-textSecondary">
                <span className="inline-flex h-3 w-3 animate-ping rounded-full bg-accent" />
                <span className="font-medium text-textPrimary">数据抓取中</span>
              </div>
              <div className="text-sm text-textSecondary">{progressMessage}</div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-accent to-accentHover transition-all duration-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          ) : null}
        </section>

        {data ? (
          <div>
            <Section title="分析概览">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard title="总交易次数" value={data.global_summary.total_trades} />
                <StatCard title="买入次数 / 金额" value={data.global_summary.total_buy_trades} subtitle={data.global_summary.total_buy_usdc} />
                <StatCard title="卖出次数 / 金额" value={data.global_summary.total_sell_trades} subtitle={data.global_summary.total_sell_usdc} />
                <StatCard title="净利润" value={data.global_summary.net_profit} />
                <StatCard title="ROI" value={formatNullable(data.global_summary.roi)} />
                <StatCard title="平均单笔利润" value={formatNullable(data.global_summary.avg_profit_per_trade)} />
                <StatCard title="REDEEM 次数" value={data.global_summary.total_redeem_trades} />
                <StatCard title="REDEEM 占比" value={formatNullable(data.global_summary.redeem_ratio)} />
              </div>
              <div className="mt-6 rounded-xl border border-white/5 bg-background/60 p-4 text-sm text-textSecondary">
                <div>地址：<span className="text-textPrimary">{data.metadata.address}</span></div>
                <div className="mt-1">时间范围：{data.metadata.start_date} ~ {data.metadata.end_date}</div>
                <div className="mt-1">生成时间：{new Date(data.metadata.generated_at).toLocaleString()}</div>
              </div>
            </Section>

            <Section title="每日盈亏摘要">
              <div className="grid gap-6 lg:grid-cols-2">
                <div className="rounded-xl border border-white/5 bg-background/60 p-4">
                  <h3 className="text-base font-semibold text-textPrimary">盈利最多</h3>
                  <Table<DailyRecord>
                    columns={[
                      { key: 'date', header: '日期' },
                      { key: 'trade_count', header: '交易数' },
                      { key: 'buy_usdc', header: '买入金额' },
                      { key: 'sell_usdc', header: '卖出金额' },
                      { key: 'profit', header: '利润' },
                    ]}
                    data={data.daily_summary.top_profitable_days}
                    keyExtractor={(row) => `${row.date}-profit`}
                  />
                </div>
                <div className="rounded-xl border border-white/5 bg-background/60 p-4">
                  <h3 className="text-base font-semibold text-textPrimary">亏损最多</h3>
                  <Table<DailyRecord>
                    columns={[
                      { key: 'date', header: '日期' },
                      { key: 'trade_count', header: '交易数' },
                      { key: 'buy_usdc', header: '买入金额' },
                      { key: 'sell_usdc', header: '卖出金额' },
                      { key: 'profit', header: '利润' },
                    ]}
                    data={data.daily_summary.top_loss_days}
                    keyExtractor={(row) => `${row.date}-loss`}
                  />
                </div>
              </div>
            </Section>

            <Section title="交易时段分布 (CST)">
              <HourlyDistribution records={data.hourly_distribution} />
            </Section>

            <Section title="市场集中度">
              <div className="grid gap-6 lg:grid-cols-2">
                <div>
                  <h3 className="mb-3 text-base font-semibold text-textPrimary">成交额 Top 10</h3>
                  <Table<MarketVolumeRecord>
                    columns={[
                      { key: 'ranking', header: '排名' },
                      { key: 'slug', header: '市场' },
                      { key: 'total_volume', header: '成交额' },
                      { key: 'ratio', header: '占比' },
                    ]}
                    data={data.market_concentration.top_by_volume}
                    keyExtractor={(row) => row.slug}
                  />
                </div>
                <div>
                  <h3 className="mb-3 text-base font-semibold text-textPrimary">净头寸 Top 10</h3>
                  <Table<NetPositionRecord>
                    columns={[
                      { key: 'ranking', header: '排名' },
                      { key: 'slug', header: '市场' },
                      { key: 'net_position', header: '净头寸 (SELL-BUY)' },
                    ]}
                    data={data.market_concentration.top_by_net_position}
                    keyExtractor={(row) => row.slug}
                  />
                </div>
              </div>
            </Section>

            <Section title="ROI 榜">
              <Table<LeaderboardEntry>
                columns={[
                  { key: 'ranking', header: '排名' },
                  { key: 'slug', header: 'slug' },
                  { key: 'roi', header: 'ROI' },
                  { key: 'profit', header: '利润' },
                  { key: 'buy_usdc', header: '买入金额' },
                  { key: 'sell_usdc', header: '卖出金额' },
                  { key: 'avg_buy_price', header: '均价(BUY)' },
                  { key: 'avg_sell_price', header: '均价(SELL)' },
                  { key: 'avg_buy_amount', header: '单笔买入均额' },
                  { key: 'trade_count', header: '交易次数' },
                ]}
                data={data.roi_leaderboard.map((entry) => ({
                  ...entry,
                  roi: formatNullable(entry.roi),
                  profit: formatNullable(entry.profit),
                  buy_usdc: formatNullable(entry.buy_usdc),
                  sell_usdc: formatNullable(entry.sell_usdc),
                  avg_buy_price: formatNullable(entry.avg_buy_price),
                  avg_sell_price: formatNullable(entry.avg_sell_price),
                  avg_buy_amount: formatNullable(entry.avg_buy_amount),
                }))}
                keyExtractor={(row) => row.slug}
              />
            </Section>

            <Section title="市场盈亏榜">
              <div className="mb-4 flex gap-2 rounded-xl border border-white/10 bg-background/60 p-2">
                {([
                  { key: 'profit', label: '利润榜' },
                  { key: 'loss', label: '亏损榜' },
                ] as const).map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    className={clsx(
                      'flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                      leaderboardTab === tab.key
                        ? 'bg-accent text-background'
                        : 'bg-transparent text-textSecondary hover:text-textPrimary'
                    )}
                    onClick={() => setLeaderboardTab(tab.key)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <Table<LeaderboardEntry>
                columns={[
                  { key: 'ranking', header: '排名' },
                  { key: 'slug', header: 'slug' },
                  { key: 'profit', header: '利润' },
                  { key: 'roi', header: 'ROI' },
                  { key: 'buy_usdc', header: '买入金额' },
                  { key: 'sell_usdc', header: '卖出金额' },
                  { key: 'avg_buy_price', header: '均价(BUY)' },
                  { key: 'avg_sell_price', header: '均价(SELL)' },
                  { key: 'avg_buy_amount', header: '单笔买入均额' },
                  { key: 'trade_count', header: '交易次数' },
                ]}
                data={(leaderboardTab === 'profit' ? data.profit_leaderboard : data.loss_leaderboard).map((entry) => ({
                  ...entry,
                  roi: formatNullable(entry.roi),
                  profit: formatNullable(entry.profit),
                  buy_usdc: formatNullable(entry.buy_usdc),
                  sell_usdc: formatNullable(entry.sell_usdc),
                  avg_buy_price: formatNullable(entry.avg_buy_price),
                  avg_sell_price: formatNullable(entry.avg_sell_price),
                  avg_buy_amount: formatNullable(entry.avg_buy_amount),
                }))}
                keyExtractor={(row) => `${row.slug}-${leaderboardTab}`}
              />
            </Section>
          </div>
        ) : null}
      </main>
    </div>
  );
}

export default App;
