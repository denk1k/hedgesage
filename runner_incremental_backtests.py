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

def run_incremental_backtests():
    with open("top_funds.json", "r") as f:
        top_funds = json.load(f)
    
    allocations_meta = load_allocations_meta()
    
    for cik, info in top_funds.items():
        name = info["name"]
        print(f"\nChecking incremental backtest for {name} ({cik})")
        
        # 1. Determine Last Rebalance Date
        allocations_cp, allocations_cp_scaled, alloc_df_fund = prepare_allocations(cik)
        if alloc_df_fund is None or alloc_df_fund.empty:
            print(f"No allocations found for {name}. Skipping.")
            continue
            
        last_rebalance_date = alloc_df_fund.index.max()
        print(f"Last rebalance date: {last_rebalance_date.date()}")
        
        # 2. Check Existing Backtest
        backtest_csv_path = f"./sec/backtests/{cik}_backtest_values.csv"
        existing_pv_df = None
        last_backtest_date = None
        
        if os.path.exists(backtest_csv_path):
            existing_pv_df = pd.read_csv(backtest_csv_path, parse_dates=['date'], index_col='date')
            if not existing_pv_df.empty:
                last_backtest_date = existing_pv_df.index.max()
                # Ensure timezone awareness compatibility
                if last_backtest_date.tz is None:
                    last_backtest_date = last_backtest_date.tz_localize('UTC')
                else:
                    last_backtest_date = last_backtest_date.tz_convert('UTC')
                
                print(f"Last backtest date: {last_backtest_date.date()}")
        
        today = pd.Timestamp.now(tz='UTC')
        
        # 3. Decide if update is needed
        # We update if:
        # a) No existing backtest
        # b) Last backtest is older than today (missing recent days)
        # c) Last rebalance date is newer than last backtest date (new filing came in)
        
        needs_update = False
        if last_backtest_date is None:
            print("No existing backtest. Full run required (but this script is for incremental).")
            # For now, we can try to run it incrementally from the start if we fetch all data?
            # But the user said "fetches past n days".
            # If no backtest exists, we probably shouldn't run this script, or we should warn.
            # Let's assume this script is for UPDATING.
            print("Skipping (use runner_do_backtests.py for initial run).")
            continue
        elif last_backtest_date.date() < today.date():
            print("Backtest is outdated.")
            needs_update = True
        
        if not needs_update:
            print("Backtest is up to date.")
            continue
            
        # 4. Prepare for Incremental Run
        # We will re-run from last_rebalance_date to ensure accuracy.
        # We need the Portfolio Value at last_rebalance_date from the existing backtest.
        
        # Handle timezone mismatch in indexing
        if existing_pv_df.index.tz is None:
             existing_pv_df.index = existing_pv_df.index.tz_localize('UTC')
        else:
             existing_pv_df.index = existing_pv_df.index.tz_convert('UTC')

        # Find the closest date in existing backtest to last_rebalance_date
        # Ideally it should exist.
        start_date = last_rebalance_date
        
        # If last_rebalance_date is NOT in existing backtest (e.g. new filing), 
        # we need to go back to the PREVIOUS rebalance to chain it correctly?
        # Or we can just take the PV from the day before last_rebalance_date?
        # Actually, if a new filing came in, the existing backtest might have run PAST that date using old allocations.
        # So we overwrite from that date.
        # We need the PV at start_date.
        
        try:
            # We look for the value at start_date. 
            # If start_date is a weekend/holiday, it might not be in prices/backtest.
            # We need to find the latest available date <= start_date in the existing backtest.
            valid_dates = existing_pv_df.index[existing_pv_df.index <= start_date]
            if valid_dates.empty:
                print(f"Cannot find a valid start point in existing backtest before {start_date}. Skipping.")
                continue
            
            actual_start_date = valid_dates[-1]
            print(f"Starting incremental update from: {actual_start_date.date()}")
            
            # Get initial investments for each scenario
            initial_investments = {}
            for col in existing_pv_df.columns:
                initial_investments[col] = existing_pv_df.loc[actual_start_date, col]
            
        except Exception as e:
            print(f"Error determining start values: {e}")
            continue

        # 5. Fetch Data
        # We need data from actual_start_date to today.
        req_start = actual_start_date
        req_end = today
        
        all_tickers = pd.Index([])
        all_tickers = all_tickers.union(allocations_cp.columns)
        all_tickers = all_tickers.union(allocations_cp_scaled.columns)
        all_tickers = all_tickers.union(alloc_df_fund.columns)
        all_tickers = all_tickers.unique().tolist()
        
        print(f"Fetching data for {len(all_tickers)} tickers from {req_start.date()} to {req_end.date()}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {executor.submit(get_ticker_data, ticker, req_start, req_end): ticker for ticker in all_tickers}
            for future in tqdm(concurrent.futures.as_completed(future_to_ticker), total=len(all_tickers), desc="Fetching incremental data"):
                try:
                    future.result()
                except Exception as exc:
                    print(f'Downloader exception for {future_to_ticker[future]}: {exc}')

        # 6. Run Scenarios
        prices_df = load_prices(all_tickers)
        if prices_df is None:
            print("Failed to load prices.")
            continue
            
        # Filter prices to relevant range (optimization)
        prices_df = prices_df[prices_df.index >= actual_start_date]
        
        # Run scenarios
        # We need to map column names in existing_pv_df to scenario names
        # existing columns: PortfolioValue_copy, PortfolioValue_copy_scaled, PortfolioValue_fund
        
        new_results = {}
        
        # Scenario: Copy
        if 'PortfolioValue_copy' in initial_investments:
            pv, res = scenario(allocations_cp, prices_df, initial_investments['PortfolioValue_copy'], "copy", specific_start_date=actual_start_date)
            if pv is not None:
                new_results['PortfolioValue_copy'] = pv

        # Scenario: Copy Scaled
        if 'PortfolioValue_copy_scaled' in initial_investments:
            pv, res = scenario(allocations_cp_scaled, prices_df, initial_investments['PortfolioValue_copy_scaled'], "copy_scaled", specific_start_date=actual_start_date)
            if pv is not None:
                new_results['PortfolioValue_copy_scaled'] = pv

        # Scenario: Fund
        if 'PortfolioValue_fund' in initial_investments:
            pv, res = scenario(alloc_df_fund, prices_df, initial_investments['PortfolioValue_fund'], "fund", specific_start_date=actual_start_date)
            if pv is not None:
                new_results['PortfolioValue_fund'] = pv
        
        if not new_results:
            print("No new results generated.")
            continue
            
        # 7. Merge and Save
        # Combine new results into a DataFrame
        new_pv_df = pd.concat(new_results.values(), axis=1)
        new_pv_df.columns = new_results.keys()
        
        # Ensure timezone consistency
        if new_pv_df.index.tz is None:
            new_pv_df.index = new_pv_df.index.tz_localize('UTC')
        else:
            new_pv_df.index = new_pv_df.index.tz_convert('UTC')
            
        # Merge: keep existing up to actual_start_date (exclusive? or inclusive?), append new
        # Since we started simulation from actual_start_date using the value AT that date,
        # the new series starts at actual_start_date.
        # We should replace everything from actual_start_date onwards.
        
        final_pv_df = existing_pv_df[existing_pv_df.index < actual_start_date].copy()
        final_pv_df = pd.concat([final_pv_df, new_pv_df])
        
        # Save CSV
        final_pv_df.to_csv(backtest_csv_path)
        print(f"Updated backtest saved to {backtest_csv_path}")
        
        # 8. Update Stats in top_funds.json
        # We need to recalculate stats for the whole period
        all_results_stats = {}
        
        for col in final_pv_df.columns:
            series = final_pv_df[col]
            # Calculate stats (copied from backtester.py)
            portfolio_daily_returns = series.pct_change().fillna(0)
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
        print(f"Updated stats for {name} in top_funds.json")
        
        # Update Graph
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
        print(f"Updated graph saved to: {html_path}")

if __name__ == "__main__":
    run_incremental_backtests()
