import requests
import json
import sys
import argparse
import os
from datetime import datetime, timezone, timedelta
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class WalletAnalyzer:
    def __init__(self, address, label=None):
        """初始化钱包分析器
        
        Args:
            address (str): 钱包地址
            label (str, optional): 钱包标签，用于日志记录
        """
        self.address = address
        self.label = label or address[:10]
        self.logger = logging.getLogger(f"WalletAnalyzer-{self.label}")
    
    def get_all_trades(self, start=None, end=None, max_workers=4, record_type="TRADE"):
        """获取指定地址的所有历史交易记录
        
        Args:
            start (int, optional): 起始时间（Unix时间戳，UTC）
            end (int, optional): 结束时间（Unix时间戳，UTC）
            max_workers (int, optional): 并行拉取的最大线程数
            record_type (str, optional): 交易类型 (例如 "TRADE" 或 "REDEEM")
        
        Returns:
            list: 交易记录列表
        """
        params = {
            "user": self.address,
            "type": record_type,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
            "limit": 499,
            "offset": 0
        }
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end

        # 记录开始时间
        start_time = datetime.now()
        start_desc = self.convert_timestamp_to_cst(start) if start is not None else "不限"
        end_desc = self.convert_timestamp_to_cst(end) if end is not None else "不限"
        self.logger.info(f"开始获取 {record_type} 记录: {self.address} (start={start_desc}, end={end_desc})")
        print(f"\n开始获取 {record_type} 记录: {self.address[:10]}...{self.address[-6:]} (范围: {start_desc} - {end_desc})")
        
        try:
            limit = params["limit"]
            max_workers = max(1, int(max_workers or 1))

            self.logger.info("正在获取第 1 页数据 (offset=0)...")
            print("正在获取第 1 页数据 (offset=0)...", end="", flush=True)
            first_page = self._fetch_page(dict(params))
            if not first_page:
                self.logger.info(f"未找到 {record_type} 记录: {self.label} (start={start_desc}, end={end_desc})")
                print("\r第 1 页无数据")
                return []

            self.logger.info(f"第 1 页获取成功: {len(first_page)} 条 {record_type} 记录")
            print(f"\r第 1 页获取成功: {len(first_page)} 条 {record_type} 记录")

            all_trades = first_page.copy()
            total_records = len(all_trades)
            total_requests = 1  # 已完成请求次数

            if len(first_page) < limit:
                total_time = (datetime.now() - start_time).total_seconds()
                self.logger.info(f"获取完成: 共 {total_records} 条 {record_type} 记录, 共 {total_requests} 页, 总耗时 {total_time:.2f} 秒")
                print(f"\n获取完成: 共 {total_records} 条 {record_type} 记录, 共 {total_requests} 页, 总耗时 {total_time:.2f} 秒")
                return all_trades

            next_offset = params["offset"] + limit
            submitted_offsets = set()

            def submit_offset(executor, pending, offset):
                if offset in submitted_offsets:
                    return
                page_params = dict(params)
                page_params["offset"] = offset
                future = executor.submit(self._fetch_page, page_params)
                pending[future] = offset
                submitted_offsets.add(offset)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                pending = {}

                for _ in range(max_workers):
                    submit_offset(executor, pending, next_offset)
                    next_offset += limit

                while pending:
                    futures_snapshot = list(pending.keys())
                    future = next(as_completed(futures_snapshot))
                    offset = pending.pop(future)
                    total_requests += 1
                    try:
                        page_data = future.result()
                    except Exception as e:
                        self.logger.error(f"并行获取 offset={offset} 时失败: {e}")
                        page_data = []

                    if page_data:
                        all_trades.extend(page_data)
                        total_records += len(page_data)
                        if len(page_data) == limit:
                            submit_offset(executor, pending, next_offset)
                            next_offset += limit

                    if total_requests % max(1, max_workers) == 0 or not pending:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        print(f"完成 {total_requests} 页, 当前共 {total_records} 条 {record_type}, 耗时 {elapsed:.2f} 秒", flush=True)

            all_trades.sort(key=lambda t: t.get('timestamp', 0), reverse=True)

            total_time = (datetime.now() - start_time).total_seconds()
            self.logger.info(f"获取完成: 共 {len(all_trades)} 条 {record_type} 记录, 共 {total_requests} 页, 总耗时 {total_time:.2f} 秒")
            print(f"\n获取完成: 共 {len(all_trades)} 条 {record_type} 记录, 共 {total_requests} 页, 总耗时 {total_time:.2f} 秒")
            return all_trades

        except Exception as e:
            self.logger.error(f"{record_type} fetch failed for {self.label} with start={start_desc}, end={end_desc}: {e}")
            print(f"\n获取 {record_type} 记录失败: {e}")
            return []

    def _fetch_page(self, params):
        max_retries = 10
        retry_count = 0
        offset = params.get("offset", 0)
        while retry_count < max_retries:
            try:
                response = requests.get(
                    "https://data-api.polymarket.com/activity",
                    params=params,
                    timeout=10
                )

                if response.status_code == 429:
                    retry_count += 1
                    wait_time = min(60, 2 ** retry_count)
                    self.logger.warning(
                        f"获取 offset={offset} 数据受到限流 (429) (尝试 {retry_count}/{max_retries}), {wait_time} 秒后重试"
                    )
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                trades = response.json()
                if trades:
                    return trades
                return []
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(
                        f"获取 offset={offset} 数据失败 (尝试 {retry_count}/{max_retries}): {e}"
                    )
                    raise
                wait_time = min(60, 2 ** retry_count)
                self.logger.error(
                    f"获取 offset={offset} 数据失败 (尝试 {retry_count}/{max_retries}): {e}, {wait_time} 秒后重试"
                )
                time.sleep(wait_time)
    
    def convert_timestamp_to_cst(self, timestamp):
        """将Unix时间戳转换为中国标准时间（UTC+8）
        
        Args:
            timestamp (int): Unix时间戳（秒）
            
        Returns:
            str: 格式化的中国标准时间字符串
        """
        # 创建UTC时间
        utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        # 转换为中国标准时间 (UTC+8)
        cst_time = utc_time + timedelta(hours=8)
        # 格式化为易读的字符串
        return cst_time.strftime('%Y-%m-%d %H:%M:%S')
    
    @staticmethod
    def parse_cst_datetime(time_str):
        if not time_str:
            return None
        cst_zone = timezone(timedelta(hours=8))
        dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        aware = dt.replace(tzinfo=cst_zone)
        return int(aware.astimezone(timezone.utc).timestamp())

    def generate_daily_intervals(self, start=None, end=None):
        cst_zone = timezone(timedelta(hours=8))

        def _to_cst(ts):
            if ts is None:
                return None
            return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(cst_zone)

        end_dt = _to_cst(end) or datetime.now(timezone.utc).astimezone(cst_zone)
        start_dt = _to_cst(start) or end_dt

        start_day = datetime.combine(start_dt.date(), datetime.min.time(), tzinfo=cst_zone)
        end_day = datetime.combine(end_dt.date(), datetime.min.time(), tzinfo=cst_zone)

        intervals = []
        current_day = start_day
        while current_day <= end_day:
            day_start = current_day
            day_end = day_start + timedelta(days=1)

            interval_start = max(day_start, start_dt)
            interval_end = min(day_end, end_dt)

            if interval_start < interval_end:
                start_ts = int(interval_start.astimezone(timezone.utc).timestamp())
                end_ts = int(interval_end.astimezone(timezone.utc).timestamp())
                date_tag = day_start.strftime('%Y%m%d')
                intervals.append((start_ts, end_ts, date_tag))

            current_day = day_start + timedelta(days=1)

        return intervals

    def fetch_trades_for_day(self, start_ts, end_ts, max_workers=4, record_types=("TRADE",)):
        day_desc = f"{self.convert_timestamp_to_cst(start_ts)} - {self.convert_timestamp_to_cst(end_ts)}"
        all_trades = []
        for record_type in record_types:
            self.logger.info(f"开始获取 {day_desc} 的 {record_type} 数据")
            trades = self.get_all_trades(start=start_ts, end=end_ts, max_workers=max_workers, record_type=record_type)
            all_trades.extend(trades)
            self.logger.info(f"完成获取 {day_desc} 的 {record_type} 数据，共 {len(trades)} 条")
        return all_trades

    def process_trades_with_cst(self, trades):
        """处理交易记录，将时间戳转换为中国标准时间"""
        processed_trades = []
        for trade in trades:
            processed_trade = trade.copy()
            if 'timestamp' in processed_trade:
                processed_trade['cst_time'] = self.convert_timestamp_to_cst(processed_trade['timestamp'])
            processed_trades.append(processed_trade)
        return processed_trades
    
    def save_trades_to_csv(self, trades, filename):
        """将交易记录保存到CSV文件，仅保留指定字段"""
        if not trades:
            self.logger.warning("No trades to save")
            print("没有交易记录可保存")
            return None

        fields = ["slug", "type", "side", "size", "usdcSize", "price", "cst_time"]

        if not filename:
            raise ValueError("filename is required for saving trades")

        print(f"正在处理并保存 {len(trades)} 条交易记录到 {filename}...", end="", flush=True)

        processed_trades = self.process_trades_with_cst(trades)

        with open(filename, 'w', encoding='utf-8') as f:
            header = ",".join(fields)
            f.write(header + "\n")
            for trade in processed_trades:
                row = []
                for field in fields:
                    value = trade.get(field, "")
                    if isinstance(value, (int, float)):
                        row.append(str(value))
                    elif value is None:
                        row.append("")
                    else:
                        text = str(value).replace('"', '""')
                        if ',' in text or '"' in text:
                            text = f'"{text}"'
                        row.append(text)
                f.write(",".join(row) + "\n")

        self.logger.info(f"Saved {len(trades)} trades to {filename}")
        print(" 完成!")
        return filename
    
    def analyze_trades(self, trades):
        raise NotImplementedError("分析功能已移除")


def load_trades_from_json(filename):
    raise NotImplementedError("分析功能已移除")


def analyze_from_json(json_file):
    raise NotImplementedError("分析功能已移除")


def print_analysis_summary(analysis):
    raise NotImplementedError("分析功能已移除")


def main(address=None, start=None, end=None, max_workers=4):
    """主函数，用于获取交易记录"""
    if not address:
        print("错误: 请指定钱包地址")
        return

    print(f"\n===== 开始获取钱包交易: {address} =====\n")
    analyzer = WalletAnalyzer(address)

    intervals = analyzer.generate_daily_intervals(start=start, end=end)
    if not intervals:
        print("未生成任何查询区间，请检查输入时间")
        return

    print(f"计划查询 {len(intervals)} 个日期区间")

    address_prefix = address[:5]
    completed = []
    skipped = []
    failed = []
    results_lock = Lock()

    def _task(interval):
        day_start, day_end, date_tag = interval
        filename = f"./data/{date_tag}_{address_prefix}.csv"
        if os.path.exists(filename):
            analyzer.logger.info(f"文件已存在，跳过 {filename}")
            with results_lock:
                skipped.append(filename)
            return None
        trades = analyzer.fetch_trades_for_day(
            day_start,
            day_end,
            max_workers=max_workers,
            record_types=("TRADE", "REDEEM"),
        )
        if not trades:
            analyzer.logger.info(f"{date_tag} 无交易记录或获取失败")
            return None
        saved = analyzer.save_trades_to_csv(trades, filename)
        with results_lock:
            completed.append(saved)
        print(f"已保存 {len(trades)} 条交易记录到 {saved}")
        return saved

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_task, interval): interval for interval in intervals}
        for future in as_completed(futures):
            interval = futures[future]
            try:
                future.result()
            except Exception as exc:
                day_start, day_end, date_tag = interval
                filename = f"{date_tag}_{address_prefix}.csv"
                analyzer.logger.error(f"处理 {filename} 时发生错误: {exc}")
                with results_lock:
                    failed.append(filename)

    print("\n===== 汇总 =====")
    print(f"完成: {len(completed)} 个文件")
    if completed:
        for fn in completed:
            print(f"  - {fn}")
    print(f"跳过: {len(skipped)} 个文件 (已存在)")
    if skipped:
        for fn in skipped:
            print(f"  - {fn}")
    print(f"失败: {len(failed)} 个文件")
    if failed:
        for fn in failed:
            print(f"  - {fn}")

if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="钱包交易获取工具")
    parser.add_argument("-a", "--address", help="钱包地址")
    parser.add_argument("--start", help="起始时间 (东八区), 格式 YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--end", help="结束时间 (东八区), 格式 YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--max-workers", type=int, default=4, help="并行请求的最大线程数，默认 4")

    args = parser.parse_args()

    # 如果没有提供任何地址，使用默认地址
    if not args.address:
        args.address = ""
        print(f"未指定地址，使用默认地址: {args.address}")
    
    # 解析时间参数
    start_ts = None
    end_ts = None
    try:
        start_ts = WalletAnalyzer.parse_cst_datetime(args.start)
    except Exception as e:
        print(f"起始时间格式错误: {e}")
        sys.exit(1)
    try:
        end_ts = WalletAnalyzer.parse_cst_datetime(args.end)
    except Exception as e:
        print(f"结束时间格式错误: {e}")
        sys.exit(1)

    main(address=args.address, start=start_ts, end=end_ts, max_workers=args.max_workers)
