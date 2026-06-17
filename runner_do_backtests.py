# This script cannot be run via GH actions, since historical data consumes a ton of resources. It could very well run for a day.
import argparse
import collections
import contextlib
import io
import json
import os
import sys
import traceback
from datetime import datetime
import concurrent.futures

import pandas as pd
from tqdm import tqdm

from backtester import backtest_hedge_fund
from data_downloader import tickers_from_cik, get_ticker_data


class _RingBuffer(io.TextIOBase):
    """Line-bounded in-memory sink for quiet mode.

    Keeps only the most recent maxlen lines so a multi-hour run that prints
    hundreds of thousands of price/scenario log lines cannot exhaust memory.
    The retained tail is what we dump if the run errors out.
    """

    def __init__(self, maxlen=5000):
        self._lines = collections.deque(maxlen=maxlen)
        self._partial = ""
        self._newline = chr(10)

    def write(self, s):
        self._partial += s
        while self._newline in self._partial:
            line, self._partial = self._partial.split(self._newline, 1)
            self._lines.append(line)
        return len(s)

    def writable(self):
        return True

    def flush(self):
        pass

    def getvalue(self):
        lines = list(self._lines)
        if self._partial:
            lines.append(self._partial)
        return self._newline.join(lines)


def _heartbeat_step(total):
    # Emit roughly 100 progress lines across a stage: one every n/100 items
    # (and at least every item for small n). This is the "every 100/n"
    # cadence requested so the console always shows the run is alive.
    return max(1, total // 100)


def run_all_backtests(quiet=True):
    """Download fresh data and backtest every fund.

    quiet=True (default): all the noisy per-ticker / per-scenario output is
    redirected into a bounded ring buffer and stays hidden. Even in quiet
    mode each stage (ticker gathering, price download, per-fund backtests,
    and the point-in-time ETF build) emits a heartbeat every n/100 items to
    the real console so you can be sure it's still doing something. If
    anything raises, the captured tail is flushed so the lead-up to the error
    is visible, followed by the traceback.
    """
    real_stderr = sys.stderr
    buffer = _RingBuffer()

    def status(msg):
        # Always writes to the true console, bypassing the quiet redirect.
        print(msg, file=real_stderr, flush=True)

    stdout_sink = contextlib.redirect_stdout(buffer) if quiet else contextlib.nullcontext()
    stderr_sink = contextlib.redirect_stderr(buffer) if quiet else contextlib.nullcontext()

    try:
        with stdout_sink, stderr_sink:
            with open("top_funds.json", "r") as f:
                top_funds = json.load(f)

            all_tickers = set()
            earliest_start = pd.to_datetime('2100-01-01')

            # --- Stage 1/3: gather tickers per fund ---
            fund_items = list(top_funds.items())
            n_funds = len(fund_items)
            fund_step = _heartbeat_step(n_funds)
            status(f"Stage 1/3: gathering tickers for {n_funds} funds...")
            for fi, (cik, info) in enumerate(fund_items, 1):
                name = info["name"]
                print(f"Getting tickers for {name} ({cik})")
                tickers, first_filing_date = tickers_from_cik(cik)
                if tickers:
                    all_tickers.update(tickers)
                if first_filing_date:
                    filing_date = pd.to_datetime(first_filing_date)
                    if filing_date < earliest_start:
                        earliest_start = filing_date
                if fi % fund_step == 0 or fi == n_funds:
                    status(f"  tickers gathered: {fi}/{n_funds} funds")

            if not all_tickers:
                print("Nothing to download.")
            else:
                print(f"Found {len(all_tickers)} unique tickers in total.")
                print(f"Earliest filing is at {earliest_start.date()}.")

                required_start = earliest_start
                required_end = pd.to_datetime(datetime.now().strftime('%Y-%m-%d'))

                output_dir = './data/historical'
                os.makedirs(output_dir, exist_ok=True)

                # --- Stage 2/3: download price data ---
                n_tickers = len(all_tickers)
                tick_step = _heartbeat_step(n_tickers)
                status(f"Stage 2/3: downloading price data for {n_tickers} tickers...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    future_to_ticker = {
                        executor.submit(get_ticker_data, ticker, required_start, required_end): ticker
                        for ticker in all_tickers
                    }
                    done = 0
                    for future in concurrent.futures.as_completed(future_to_ticker):
                        try:
                            future.result()
                        except Exception as exc:
                            print(f'downloader had an exception: {exc}')
                        done += 1
                        if done % tick_step == 0 or done == n_tickers:
                            status(f"  fetched: {done}/{n_tickers} tickers")

            print("All data downloaded. Starting backtests.")
            # --- Stage 3/3: per-fund backtests ---
            bt_step = _heartbeat_step(n_funds)
            status(f"Stage 3/3: backtesting {n_funds} funds...")
            for i, (cik, info) in enumerate(fund_items, 1):
                name = info["name"]
                print(f"Generating backtest for: {name}")
                backtest_hedge_fund(cik, download_data=False)
                if i % bt_step == 0 or i == n_funds:
                    status(f"  backtested: {i}/{n_funds} funds (latest: {name})")

            print("All backtests done. Building point-in-time Hedge Fund Investment ETF.")
            status("Building point-in-time Hedge Fund Investment ETF...")
            # Pass the real-console status printer so the PIT build's own
            # n/100 heartbeats stay visible even though it runs inside the
            # quiet stdout/stderr redirect (otherwise they'd be swallowed by
            # the ring buffer).
            from runner_do_point_in_time_backtests import main as build_pit_etf
            build_pit_etf(quiet=quiet, status=status)

        status("All backtests completed successfully.")
    except Exception:
        if quiet:
            captured = buffer.getvalue()
            if captured:
                status("")
                status("===== captured output (quiet mode; shown because an error occurred) =====")
                status(captured)
                status("===== end captured output =====")
                status("")
        status("ERROR: backtest run failed. Traceback:")
        traceback.print_exc(file=real_stderr)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download fresh data and run full backtests for every fund."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Stream all output live instead of staying quiet until an error occurs.",
    )
    args = parser.parse_args()
    run_all_backtests(quiet=not args.verbose)
