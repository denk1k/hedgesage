# This script cannot be run via GH actions, since historical data consumes a ton of resources. It could very well run for a day.
import json
import os
import pandas as pd
from datetime import datetime
import concurrent.futures
from backtester import backtest_hedge_fund
from data_downloader import tickers_from_cik, get_ticker_data
from tqdm import tqdm

if __name__ == "__main__":
    with open("top_funds.json", "r") as f:
        top_funds = json.load(f)

    all_tickers = set()
    earliest_start = pd.to_datetime('2100-01-01')

    for cik, info in top_funds.items():
        name = info["name"]
        print(f"Getting tickers for {name} ({cik})")
        tickers, first_filing_date = tickers_from_cik(cik)
        if tickers:
            all_tickers.update(tickers)
        if first_filing_date:
            filing_date = pd.to_datetime(first_filing_date)
            if filing_date < earliest_start:
                earliest_start = filing_date

    if not all_tickers:
        print("Nothing to download.")
    else:
        print(f"Found {len(all_tickers)} unique tickers in total.")
        print(f"Earliest filing is at {earliest_start.date()}.")

        required_start = earliest_start
        required_end = pd.to_datetime(datetime.now().strftime('%Y-%m-%d'))

        output_dir = './data/historical'
        os.makedirs(output_dir, exist_ok=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {executor.submit(get_ticker_data, ticker, required_start, required_end): ticker for ticker in all_tickers}

            for future in tqdm(concurrent.futures.as_completed(future_to_ticker), total=len(all_tickers), desc="Getting all ticker data"):
                try:
                    future.result()
                except Exception as exc:
                    print(f'downloader had an exception: {exc}')

    print("All data downloaded. Starting backtests.")
    for cik, info in top_funds.items():
        name = info["name"]
        print(f"Generating backtest for: {name}")
        backtest_hedge_fund(cik, download_data=False)
