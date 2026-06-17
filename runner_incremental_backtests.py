import json
import os
import pandas as pd
from datetime import datetime, timedelta
import concurrent.futures
from tqdm import tqdm
import glob
import numpy as np
import plotly.graph_objects as go

from backtester import prepare_allocations, load_prices, scenario
from data_downloader import get_ticker_data
from fetch_hedge_fund_allocations import update_fund_data

def load_allocations_meta():
    path = './sec/allocations_meta.json'
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def last_rebalance_on_index(alloc_df, pv_index):
    # Re-derive the trading days on which THIS strategy actually rebalanced,
    # exactly as scenario() sees them: reindex the allocations onto the existing
    # backtest's trading calendar with forward-fill, then flag every day whose
    # target weights differ from the prior day. The newest such day is the most
    # recent point at which the portfolio was at *target* weights, which is the
    # only date we can splice from without corrupting already-validated history
    # (the CSV stores portfolio values, not share counts, so drifted weights
    # cannot be reconstructed after the fact).
    if alloc_df is None or alloc_df.empty or len(pv_index) == 0:
        return None
    a = alloc_df.reindex(pv_index, method='ffill').fillna(0)
    if a.empty:
        return None
    changed = (a != a.shift()).any(axis=1)
    changed.iloc[0] = True
    rebal_dates = a.index[changed]
    if len(rebal_dates) == 0:
        return None
    return rebal_dates.max()

def run_incremental_backtests():
    with open("top_funds.json", "r") as f:
        top_funds = json.load(f)
    
    allocations_meta = load_allocations_meta()
    
    funds_to_process = []
    ticker_requirements = {} # ticker -> min_start_date
    
    print("--- Phase 1: Identifying required updates ---")
    
    for cik, info in top_funds.items():
        # Normalize CIK to 10 digits to match backtest_hedge_fund (backtester.py:251),
        # which zero-pads before building every path (allocations, backtest CSV) and
        # before update_fund_data. Without this the incremental runner reads/writes
        # mismatched filenames and keys, so the existing-backtest check fails silently.
        cik = cik.zfill(10)
        name = info["name"]
        
        # 1. Determine Last Rebalance Date
        allocations_cp, allocations_cp_scaled, alloc_df_fund = prepare_allocations(cik)
        if alloc_df_fund is None or alloc_df_fund.empty:
            continue
            
        last_rebalance_date = alloc_df_fund.index.max()
        
        # 2. Check Existing Backtest
        backtest_csv_path = f"./sec/backtests/{cik}_backtest_values.csv"
        existing_pv_df = None
        last_backtest_date = None
        
        if os.path.exists(backtest_csv_path):
            existing_pv_df = pd.read_csv(backtest_csv_path, parse_dates=['date'], index_col='date')
            if not existing_pv_df.empty:
                last_backtest_date = existing_pv_df.index.max()
                if last_backtest_date.tz is None:
                    last_backtest_date = last_backtest_date.tz_localize('UTC')
                else:
                    last_backtest_date = last_backtest_date.tz_convert('UTC')
        
        today = pd.Timestamp.now(tz='UTC')
        
        needs_update = False
        if last_backtest_date is None:
            # Skip full runs in this incremental script
            continue
        elif last_backtest_date.date() < today.date():
            needs_update = True
        
        if not needs_update:
            continue
            
        # 4. Prepare for Incremental Run
        if existing_pv_df.index.tz is None:
             existing_pv_df.index = existing_pv_df.index.tz_localize('UTC')
        else:
             existing_pv_df.index = existing_pv_df.index.tz_convert('UTC')

        start_date = last_rebalance_date
        
        try:
            valid_dates = existing_pv_df.index[existing_pv_df.index <= start_date]
            if valid_dates.empty:
                print(f"Cannot find a valid start point in existing backtest for {name} before {start_date}. Skipping.")
                continue
            
            actual_start_date = valid_dates[-1]
            
            # Collect tickers
            all_tickers = pd.Index([])
            all_tickers = all_tickers.union(allocations_cp.columns)
            all_tickers = all_tickers.union(allocations_cp_scaled.columns)
            all_tickers = all_tickers.union(alloc_df_fund.columns)
            all_tickers = all_tickers.unique().tolist()
            
            # Update requirements. Use the EARLIEST possible per-strategy splice
            # date so the batch download always covers every strategy's window.
            # Individual strategies may splice from a later rebalance day, but
            # never earlier than actual_start_date.
            for ticker in all_tickers:
                if ticker not in ticker_requirements:
                    ticker_requirements[ticker] = actual_start_date
                else:
                    if actual_start_date < ticker_requirements[ticker]:
                        ticker_requirements[ticker] = actual_start_date
            
            funds_to_process.append({
                'cik': cik,
                'name': name,
                'actual_start_date': actual_start_date,
                'existing_pv_df': existing_pv_df,
                'allocations_cp': allocations_cp,
                'allocations_cp_scaled': allocations_cp_scaled,
                'alloc_df_fund': alloc_df_fund,
                'all_tickers': all_tickers
            })
            print(f"Queued {name} for update from {actual_start_date.date()}")
            
        except Exception as e:
            print(f"Error preparing {name}: {e}")
            continue

    if not funds_to_process:
        print("No updates needed.")
        return

    print(f"\n--- Phase 2: Batch Downloading {len(ticker_requirements)} tickers ---")
    req_end = pd.Timestamp.now(tz='UTC')
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {
            executor.submit(get_ticker_data, ticker, start_date, req_end): ticker 
            for ticker, start_date in ticker_requirements.items()
        }
        for future in tqdm(concurrent.futures.as_completed(future_to_ticker), total=len(ticker_requirements), desc="Fetching all data"):
            try:
                future.result()
            except Exception as exc:
                print(f'Downloader exception for {future_to_ticker[future]}: {exc}')

    print("\n--- Phase 3: Running Backtests ---")
    
    # Load price history ONCE for the union of all tickers and reuse it per
    # fund. Previously load_prices() was called inside the loop, re-reading the
    # full price history from disk for every fund (and re-reading shared tickers
    # repeatedly), which is what made this script lag out.
    master_tickers = sorted({t for fd in funds_to_process for t in fd['all_tickers']})
    prices_master = load_prices(master_tickers)
    if prices_master is None:
        print("Failed to load any price data for the queued funds.")
        return

    for fund_data in funds_to_process:
        cik = fund_data['cik']
        name = fund_data['name']
        actual_start_date = fund_data['actual_start_date']
        existing_pv_df = fund_data['existing_pv_df']
        allocations_cp = fund_data['allocations_cp']
        allocations_cp_scaled = fund_data['allocations_cp_scaled']
        alloc_df_fund = fund_data['alloc_df_fund']
        all_tickers = fund_data['all_tickers']
        
        print(f"Updating {name} ({cik})...")
        
        # Select this fund's tickers from the pre-loaded master price frame
        # instead of re-reading every CSV from disk per fund (the lag source).
        available_tickers = [t for t in all_tickers if t in prices_master.columns]
        if not available_tickers:
            print(f"No price data available for {name}.")
            continue
        prices_df = prices_master[available_tickers].copy()

        # Mirror the data sanity checks from backtest_hedge_fund so incremental
        # results aren't corrupted by extreme/zero price data.
        prices_df_for_check = prices_df.copy()
        prices_df_for_check.replace(0, np.nan, inplace=True)
        daily_returns = prices_df_for_check.pct_change()
        extreme_threshold = 20.0
        anomalous_tickers = daily_returns.columns[(daily_returns > extreme_threshold).any()].tolist()
        if anomalous_tickers:
            print(f"Removing extreme-volatility tickers from {name}: {anomalous_tickers}")
            prices_df.drop(columns=anomalous_tickers, inplace=True)

        prices_df.replace(0, np.nan, inplace=True)
        prices_df.bfill(inplace=True)
        prices_df.ffill(inplace=True)

        prices_df = prices_df[prices_df.index >= actual_start_date]

        # Splice each strategy from its OWN last rebalance date. Previously all
        # three strategies were restarted at the single fund-report-based
        # actual_start_date; for the filing-date "copy"/"copy_scaled" series that
        # date is usually NOT a rebalance day, so scenario()'s mandatory day-0
        # rebalance reset weights to target mid-stream and silently rewrote
        # correct historical values. Starting each strategy from a real
        # rebalance day makes the regenerated overlap reproduce the original run
        # exactly and only extends it with the new dates.
        scenario_specs = [
            ('PortfolioValue_copy', allocations_cp, 'copy'),
            ('PortfolioValue_copy_scaled', allocations_cp_scaled, 'copy_scaled'),
            ('PortfolioValue_fund', alloc_df_fund, 'fund'),
        ]

        final_columns = {}
        for col, alloc_df, label in scenario_specs:
            if col not in existing_pv_df.columns:
                continue

            scen_start = last_rebalance_on_index(alloc_df, existing_pv_df.index)
            if scen_start is None:
                scen_start = actual_start_date

            # initial_investment = the portfolio value carried into that
            # rebalance. Guard against duplicate timestamps in the CSV, which
            # would make .loc return a Series and turn scenario()'s
            # initial_investment * talloc into corrupting DataFrame math.
            init_value = existing_pv_df.loc[scen_start, col]
            if isinstance(init_value, pd.Series):
                init_value = init_value.iloc[-1]

            pv, _res = scenario(
                alloc_df,
                prices_df,
                init_value,
                label,
                specific_start_date=scen_start,
            )

            if pv is None:
                # Could not regenerate this strategy this run; keep its existing
                # series intact rather than dropping the column entirely (which
                # would also leave its metrics stale in top_funds.json).
                final_columns[col] = existing_pv_df[col]
                continue

            if pv.index.tz is None:
                pv.index = pv.index.tz_localize('UTC')
            else:
                pv.index = pv.index.tz_convert('UTC')

            # Keep the validated history before the rebalance, then append the
            # freshly recomputed values from the rebalance onward.
            history = existing_pv_df.loc[existing_pv_df.index < scen_start, col]
            final_columns[col] = pd.concat([history, pv])

        if not final_columns:
            print(f"No new results generated for {name}.")
            continue

        final_pv_df = pd.concat(final_columns.values(), axis=1)
        final_pv_df.columns = list(final_columns.keys())
        final_pv_df.sort_index(inplace=True)
        final_pv_df = final_pv_df[~final_pv_df.index.duplicated(keep='last')]

        backtest_csv_path = f"./sec/backtests/{cik}_backtest_values.csv"
        final_pv_df.to_csv(backtest_csv_path)
        
        all_results_stats = {}
        for col in final_pv_df.columns:
            # Compute metrics on the strategy's OWN unpadded series. The concat
            # above aligns columns on the UNION of dates, so a strategy that
            # starts later than another (copy/copy_scaled start after the
            # earlier-starting fund) carries leading NaN rows. scenario()
            # computes its stats on the standalone series BEFORE any concat, so
            # to reproduce it exactly we must drop those padding NaNs here.
            # Otherwise pct_change().fillna(0) injects extra zero-return days
            # that dilute mean/std (shifting Sharpe), and series.iloc[0] is a
            # NaN that silently corrupts total_return.
            series = final_pv_df[col].dropna()
            portfolio_daily_returns = series.pct_change()
            portfolio_daily_returns.replace([np.inf, -np.inf], np.nan, inplace=True)
            portfolio_daily_returns.fillna(0, inplace=True)
            std_dev = portfolio_daily_returns.std()
            sharpe_ratio = (portfolio_daily_returns.mean() / std_dev) * np.sqrt(252) if std_dev > 0 else 0.0
            
            cumulative_max = series.cummax()
            drawdown = (series - cumulative_max) / cumulative_max
            max_drawdown = drawdown.min()
            
            num_years = (series.index[-1] - series.index[0]).days / 365.25
            total_return = (series.iloc[-1] / series.iloc[0]) - 1
            annualized_return = (1 + total_return) ** (1 / num_years) - 1 if num_years > 0 else total_return
            
            calmar_ratio = annualized_return / abs(max_drawdown) if abs(max_drawdown) > 0 else np.inf
            
            suffix = col.replace('PortfolioValue_', '')
            all_results_stats[f"final_portfolio_value_{suffix}"] = series.iloc[-1]
            all_results_stats[f"total_return_{suffix}"] = total_return
            all_results_stats[f"annualized_return_{suffix}"] = annualized_return
            all_results_stats[f"sharpe_ratio_{suffix}"] = sharpe_ratio
            all_results_stats[f"max_drawdown_{suffix}"] = max_drawdown
            all_results_stats[f"calmar_ratio_{suffix}"] = calmar_ratio
            
        update_fund_data(cik, {"backtest_results": all_results_stats})
        
        fig = go.Figure()
        for col in final_pv_df.columns:
            fig.add_trace(go.Scatter(
                x=final_pv_df.index, 
                y=final_pv_df[col],
                mode='lines',
                name=col
            ))
        fig.update_layout(
            title=f'Hedge Fund Backtest Comparison: CIK {cik}',
            xaxis_title='Date',
            yaxis_title='Portfolio Value (USD)',
            template='plotly_white'
        )
        html_path = os.path.join("./sec/backtests", f"{cik}_backtest.html")
        fig.write_html(html_path)
        print(f"Completed update for {name}")

if __name__ == "__main__":
    run_incremental_backtests()

    from runner_do_point_in_time_backtests import main as build_pit_etf
    build_pit_etf()
