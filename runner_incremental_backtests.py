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
    
    funds_to_process = []
    ticker_requirements = {} # ticker -> min_start_date
    
    print("--- Phase 1: Identifying required updates ---")
    
    for cik, info in top_funds.items():
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
            
            # Update requirements
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
        
        # Get initial investments
        initial_investments = {}
        for col in existing_pv_df.columns:
            initial_investments[col] = existing_pv_df.loc[actual_start_date, col]
            
        prices_df = load_prices(all_tickers)
        if prices_df is None:
            print(f"Failed to load prices for {name}.")
            continue
            
        prices_df = prices_df[prices_df.index >= actual_start_date]
        
        new_results = {}
        
        if 'PortfolioValue_copy' in initial_investments:
            pv, res = scenario(allocations_cp, prices_df, initial_investments['PortfolioValue_copy'], "copy", specific_start_date=actual_start_date)
            if pv is not None:
                new_results['PortfolioValue_copy'] = pv

        if 'PortfolioValue_copy_scaled' in initial_investments:
            pv, res = scenario(allocations_cp_scaled, prices_df, initial_investments['PortfolioValue_copy_scaled'], "copy_scaled", specific_start_date=actual_start_date)
            if pv is not None:
                new_results['PortfolioValue_copy_scaled'] = pv

        if 'PortfolioValue_fund' in initial_investments:
            pv, res = scenario(alloc_df_fund, prices_df, initial_investments['PortfolioValue_fund'], "fund", specific_start_date=actual_start_date)
            if pv is not None:
                new_results['PortfolioValue_fund'] = pv
        
        if not new_results:
            print(f"No new results generated for {name}.")
            continue
            
        new_pv_df = pd.concat(new_results.values(), axis=1)
        new_pv_df.columns = new_results.keys()
        
        if new_pv_df.index.tz is None:
            new_pv_df.index = new_pv_df.index.tz_localize('UTC')
        else:
            new_pv_df.index = new_pv_df.index.tz_convert('UTC')
            
        final_pv_df = existing_pv_df[existing_pv_df.index < actual_start_date].copy()
        final_pv_df = pd.concat([final_pv_df, new_pv_df])
        
        backtest_csv_path = f"./sec/backtests/{cik}_backtest_values.csv"
        final_pv_df.to_csv(backtest_csv_path)
        
        all_results_stats = {}
        for col in final_pv_df.columns:
            series = final_pv_df[col]
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
