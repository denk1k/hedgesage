import pandas as pd
import numpy as np
import glob
import os
import plotly.graph_objects as go
from fetch_hedge_fund_allocations import fetch_all_past_allocations, update_fund_data
from data_downloader import download_data_since_first_filing

def scenario(alloc_df, prices_df, initial_investment, name):
    print(f"scenario {name}")

    prices_df = prices_df.copy()
    alloc_df = alloc_df.copy()

    start_date = max(prices_df.index.min(), alloc_df.index.min()) if not alloc_df.index.empty else prices_df.index.min()
    end_date = prices_df.index.max()
    
    if start_date > end_date:
        print(f"No overlapping data for scenario {name}. Skipping.")
        return None, {}

    prices_df = prices_df.loc[start_date:end_date]
    alloc_df = alloc_df.reindex(prices_df.index, method='ffill')
    
    common_tickers = prices_df.columns.intersection(alloc_df.columns)
    prices_df = prices_df[common_tickers]
    alloc_df = alloc_df[common_tickers]
    
    alloc_df.fillna(0, inplace=True)

    print(f"Backtest period: {start_date.date()} to {end_date.date()}")
    print(f"Number of tickers in backtest: {len(common_tickers)}")

    if prices_df.empty or alloc_df.empty or len(common_tickers) == 0:
        print(f"No data to backtest for scenario {name}. Skipping.")
        return None, {}

    portfolio_values = pd.Series(index=prices_df.index, dtype=float)
    current_shares = pd.Series(0.0, index=common_tickers)
    cash = initial_investment

    portfolio_values.iloc[0] = initial_investment
    
    talloc = alloc_df.iloc[0].copy()
    prices = prices_df.iloc[0]

    #avoid investing in stocks with extremely low prices (< 0.01) ?
    # sus_low = prices.index[prices < 0.01]
    # if not sus_low.empty:
    #     tickers_to_allocate = talloc.index[talloc > 0]
    #     problem_tickers = sus_low.intersection(tickers_to_allocate)
    #     if not problem_tickers.empty:
    #         print(f"On initial rebalance, not investing in tickers with price < $0.01: {problem_tickers.tolist()}")
    #         talloc[problem_tickers] = 0

    target_investment = initial_investment * talloc
    current_shares = target_investment / prices
    current_shares.fillna(0, inplace=True)
    
    invested_value = (current_shares * prices).sum()
    cash = initial_investment - invested_value
    portfolio_values.iloc[0] = invested_value + cash

    for i in range(1, len(prices_df)):
        start_of_day_portfolio_value = portfolio_values.iloc[i-1]
        prices_today = prices_df.iloc[i]

        is_scheduled_rebalance = not alloc_df.iloc[i].equals(alloc_df.iloc[i-1])
        
        if is_scheduled_rebalance and start_of_day_portfolio_value > 0:
            talloc = alloc_df.iloc[i].copy()
            target_investment = start_of_day_portfolio_value * talloc
            new_shares = target_investment / prices_today
            new_shares.fillna(0, inplace=True)

            current_shares = new_shares
            invested_value = (current_shares * prices_today).sum()
            cash = start_of_day_portfolio_value - invested_value

        equity_value = (current_shares * prices_today).sum()
        total_portfolio_value = equity_value + cash
        
        if pd.isna(total_portfolio_value) or total_portfolio_value <= 0:
             portfolio_values.iloc[i] = portfolio_values.iloc[i-1]
             current_shares.values[:] = 0
             cash = 0
        else:
            portfolio_values.iloc[i] = total_portfolio_value

    portfolio_value = portfolio_values.rename(f"PortfolioValue_{name}")
    portfolio_value.ffill(inplace=True)

    portfolio_daily_returns = portfolio_value.pct_change()
    portfolio_daily_returns.replace([np.inf, -np.inf], np.nan, inplace=True)
    portfolio_daily_returns.fillna(0, inplace=True)

    std_dev = portfolio_daily_returns.std()
    if std_dev > 0:
        sharpe_ratio = (portfolio_daily_returns.mean() / std_dev) * np.sqrt(252)
    else:
        sharpe_ratio = 0.0

    cumulative_max = portfolio_value.cummax()
    drawdown = (portfolio_value - cumulative_max) / cumulative_max
    max_drawdown = drawdown.min()

    num_years = (portfolio_value.index[-1] - portfolio_value.index[0]).days / 365.25
    total_return = (portfolio_value.iloc[-1] / portfolio_value.iloc[0]) - 1
    
    if num_years > 0:
        annualized_return = (1 + total_return) ** (1 / num_years) - 1
    else:
        annualized_return = total_return

    if abs(max_drawdown) > 0:
        calmar_ratio = annualized_return / abs(max_drawdown)
    else:
        calmar_ratio = np.inf

    print(f"\nBacktest Results for {name}:")
    print(f"Final Portfolio Value: ${portfolio_value.iloc[-1]:,.2f}")
    print(f"Total Return: {total_return:.2%}")
    print(f"Annualized Return: {annualized_return:.2%}")
    print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
    print(f"Max Drawdown: {max_drawdown:.2%}")
    print(f"Calmar Ratio: {calmar_ratio:.2f}")

    results = {
        "final_portfolio_value": portfolio_value.iloc[-1],
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar_ratio
    }
    return portfolio_value, results

def backtest_hedge_fund(cik: str, initial_investment: float = 1_000_000, download_data=False):
    cik = cik.zfill(10) # make sure that ciks are uniform
    print(f"Starting backtest for CIK: {cik}")
    if download_data:
        print(f"Making sure hist price data is available for {cik}")
        download_data_since_first_filing(cik)
        print(f"Download process complete")

    allocation_path = f'./sec/past_allocations/{cik}/*.csv'
    allocation_files = glob.glob(allocation_path)
    
    if not allocation_files:
        print(f"No allocation files found locally for CIK {cik}. Attempting to fetch them...")
        fetch_all_past_allocations(cik)
        allocation_files = glob.glob(allocation_path) # Retry finding files
        if not allocation_files:
            print(f"Error: No allocation files could be found or fetched for CIK {cik}.")
            return

    # Original backtest (filing date)
    all_dfs_copy = []
    for f in allocation_files:
        df = pd.read_csv(f)
        df['date'] = pd.to_datetime(df['filingDate'], utc=True)
        all_dfs_copy.append(df)

    # the boring stuff
    all_alloc_copy = pd.concat(all_dfs_copy)
    all_alloc_copy.sort_values('accessionNumber', ascending=True, inplace=True)
    all_alloc_copy.drop_duplicates(subset=['date', 'ticker'], keep='last', inplace=True)
    all_alloc_copy = all_alloc_copy[all_alloc_copy['ticker'] != 'N/A']
    all_alloc_copy['allocation_percent'] = pd.to_numeric(all_alloc_copy['allocation_percent'], errors='coerce')
    all_alloc_copy.dropna(subset=['allocation_percent', 'ticker'], inplace=True)
    allocations_cp = all_alloc_copy.pivot(index='date', columns='ticker', values='allocation_percent').div(100)
    allocations_cp.fillna(0, inplace=True)

    # Scaled allocations (based on original)
    allocations_cp_scaled = allocations_cp.div(allocations_cp.sum(axis=1), axis=0).fillna(0)

    # Fund's timing (report date from filename)
    all_dfs_fund = []
    for f in allocation_files:
        df = pd.read_csv(f)
        report_date = os.path.basename(f).replace('.csv', '')
        df['date'] = pd.to_datetime(report_date, utc=True)
        all_dfs_fund.append(df)

    all_alloc_fund = pd.concat(all_dfs_fund)
    all_alloc_fund.sort_values('accessionNumber', ascending=True, inplace=True)
    all_alloc_fund.drop_duplicates(subset=['date', 'ticker'], keep='last', inplace=True)
    all_alloc_fund = all_alloc_fund[all_alloc_fund['ticker'] != 'N/A']
    all_alloc_fund['allocation_percent'] = pd.to_numeric(all_alloc_fund['allocation_percent'], errors='coerce')
    all_alloc_fund.dropna(subset=['allocation_percent', 'ticker'], inplace=True)
    alloc_df_fund = all_alloc_fund.pivot(index='date', columns='ticker', values='allocation_percent').div(100)
    alloc_df_fund.fillna(0, inplace=True)

    all_tickers = pd.Index([])
    all_tickers = all_tickers.union(allocations_cp.columns)
    all_tickers = all_tickers.union(allocations_cp_scaled.columns)
    all_tickers = all_tickers.union(alloc_df_fund.columns)
    all_tickers = all_tickers.unique().tolist()

    excluded = 0
    included = 0
    price_dfs = []
    for ticker in all_tickers:
        price_file = f"./data/historical/{ticker.replace('/', '_')}.csv"
        if os.path.exists(price_file):
            try:
                df = pd.read_csv(price_file, parse_dates=['date'])
                df['date'] = pd.to_datetime(df['date'], utc=True)
                close_col_name = None
                for col in df.columns:
                    col_lower = col.lower()
                    if 'adj' in col_lower and 'close' in col_lower:
                        close_col_name = col
                        break
                if not close_col_name:
                    print(f"No adjusted price col for {ticker}.")
                    for col in df.columns:
                        if col.lower() == 'close':
                            close_col_name = col
                            break
                if not close_col_name:
                    for col in df.columns:
                        col_lower = col.lower()
                        if col_lower.startswith('close') and ticker.lower().replace('/', '_') in col_lower:
                            close_col_name = col
                            break
                
                if close_col_name:
                    df.rename(columns={close_col_name: 'close'}, inplace=True)
                    df = df[['date', 'close']]
                    df.rename(columns={'close': ticker}, inplace=True)
                    df.set_index('date', inplace=True)
                    price_dfs.append(df)
                    included += 1
                else:
                    print(f"couldn't find 'close' column in {price_file} for ticker {ticker}. Deleting corrupted file.")
                    try:
                        os.remove(price_file)
                    except OSError as e:
                        print(f"Error deleting file {price_file}: {e}")
            except Exception as e:
                print(f"Error processing price file for {ticker} at {price_file}: {e}")
        else:
            print(f"Price data not found for {ticker}. It will be excluded.")
            excluded += 1

    print(excluded, "/", included+excluded, "Tickers were excluded")

    if not price_dfs:
        print("Error: No price data could be loaded for any ticker in the portfolio.")
        return

    prices_df = pd.concat(price_dfs, axis=1)
    prices_df.sort_index(inplace=True)

    print("Starting pre-backtest data sanity check")
    prices_df_for_check = prices_df.copy()
    prices_df_for_check.replace(0, np.nan, inplace=True) # no division by zero errors
    daily_returns = prices_df_for_check.pct_change()

    extreme_threshold = 20.0 # I put this in, because when I did backtests for renaissance, some of the tickers caused the backtest to be completely cooked

    anomalous_tickers = daily_returns.columns[(daily_returns > extreme_threshold).any()].tolist()

    if anomalous_tickers:
        print(f"following tickers had extreme price volatility and are removed from the backtest:")
        for ticker in anomalous_tickers:
            print(f" - {ticker}")

        prices_df.drop(columns=anomalous_tickers, inplace=True)

    prices_df.replace(0, np.nan, inplace=True)
    prices_df.bfill(inplace=True)
    prices_df.ffill(inplace=True)

    pv_copy, results_copy = scenario(allocations_cp, prices_df, initial_investment, "copy")
    pv_copy_scaled, results_copy_scaled = scenario(allocations_cp_scaled, prices_df, initial_investment, "copy_scaled")
    pv_fund, results_fund = scenario(alloc_df_fund, prices_df, initial_investment, "fund")

    all_results = {}
    all_portfolio_values = {}

    if pv_copy is not None:
        for key, value in results_copy.items():
            all_results[f"{key}_copy"] = value
        all_portfolio_values['PortfolioValue_copy'] = pv_copy

    if pv_copy_scaled is not None:
        for key, value in results_copy_scaled.items():
            all_results[f"{key}_copy_scaled"] = value
        all_portfolio_values['PortfolioValue_copy_scaled'] = pv_copy_scaled

    if pv_fund is not None:
        for key, value in results_fund.items():
            all_results[f"{key}_fund"] = value
        all_portfolio_values['PortfolioValue_fund'] = pv_fund

    if not all_results:
        print("All backtest scenarios failed. Exiting.")
        return

    update_fund_data(cik, {"backtest_results": all_results})
    print(f"\nSaved all backtest results for CIK {cik} to top_funds.json")

    output_dir = './sec/backtests'
    os.makedirs(output_dir, exist_ok=True)

    if all_portfolio_values:
        combined_pv_df = pd.concat(all_portfolio_values.values(), axis=1)
        csv_path = os.path.join(output_dir, f"{cik}_backtest_values.csv")
        combined_pv_df.to_csv(csv_path)
        print(f"All BT values saved to: {csv_path}")

        fig = go.Figure()
        for name, pv in all_portfolio_values.items():
            fig.add_trace(go.Scatter(
                x=pv.index, 
                y=pv,
                mode='lines',
                name=name
            ))
        fig.update_layout(
            title=f'Hedge Fund Backtest Comparison: CIK {cik}',
            xaxis_title='Date',
            yaxis_title='Portfolio Value (USD)',
            template='plotly_white'
        )
        html_path = os.path.join(output_dir, f"{cik}_backtest.html")
        fig.write_html(html_path)
        print(f"Backtest comparison graph saved to: {html_path}")


if __name__ == '__main__':
    renaissance_cik = '1037389'
    backtest_hedge_fund(renaissance_cik)
    # appaloosa = '0001006438'
    # backtest_hedge_fund(appaloosa)
