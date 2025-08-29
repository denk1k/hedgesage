import pandas as pd
import numpy as np
import glob
import os
import plotly.graph_objects as go
from fetch_hedge_fund_allocations import fetch_all_past_allocations, update_fund_data
from data_downloader import download_data_since_first_filing

def backtest_hedge_fund(cik: str, initial_investment: float = 1_000_000, download_data=True):
    cik = cik.zfill(10) # make sure that ciks are uniform
    print(f"--- Starting backtest for CIK: {cik} ---")
    if download_data:
        print(f"--- Making sure hist price data is available for {cik} ---")
        download_data_since_first_filing(cik)
        print(f"--- Download process complete ---")

    allocation_path = f'./sec/past_allocations/{cik}/*.csv'
    allocation_files = glob.glob(allocation_path)
    
    if not allocation_files:
        print(f"No allocation files found locally for CIK {cik}. Attempting to fetch them...")
        fetch_all_past_allocations(cik)
        allocation_files = glob.glob(allocation_path) # Retry finding files
        if not allocation_files:
            print(f"Error: No allocation files could be found or fetched for CIK {cik}.")
            return

    all_dfs = []
    for f in allocation_files:
        df = pd.read_csv(f)
        df['date'] = pd.to_datetime(df['filingDate'], utc=True)
        all_dfs.append(df)

    all_allocations_df = pd.concat(all_dfs)
    
    all_allocations_df.sort_values('accessionNumber', ascending=True, inplace=True)
    all_allocations_df.drop_duplicates(subset=['date', 'ticker'], keep='last', inplace=True)

    all_allocations_df = all_allocations_df[all_allocations_df['ticker'] != 'N/A']

    all_allocations_df['allocation_percent'] = pd.to_numeric(all_allocations_df['allocation_percent'], errors='coerce')
    
    all_allocations_df.dropna(subset=['allocation_percent', 'ticker'], inplace=True)

    allocations_df = all_allocations_df.pivot(index='date', columns='ticker', values='allocation_percent').div(100)
    allocations_df.fillna(0, inplace=True)

    all_tickers = allocations_df.columns.unique().tolist()
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
                    print(f"Warning: Could not find a 'close' column in {price_file} for ticker {ticker}. Deleting corrupted file.")
                    try:
                        os.remove(price_file)
                    except OSError as e:
                        print(f"Error deleting file {price_file}: {e}")
            except Exception as e:
                print(f"Error processing price file for {ticker} at {price_file}: {e}")
        else:
            print(f"Warning: Price data not found for {ticker}. It will be excluded.")
            excluded += 1

    print(excluded, "/", included+excluded, "Tickers were excluded")


    if not price_dfs:
        print("Error: No price data could be loaded for any ticker in the portfolio.")
        return

    prices_df = pd.concat(price_dfs, axis=1)
    prices_df.sort_index(inplace=True)

    print("--- Starting pre-backtest data sanity check ---")
    prices_df_for_check = prices_df.copy()
    prices_df_for_check.replace(0, np.nan, inplace=True) # no division by zero errors
    daily_returns = prices_df_for_check.pct_change()

    extreme_threshold = 20.0 

    # tickers w at least one day of extreme returns
    anomalous_tickers = daily_returns.columns[(daily_returns > extreme_threshold).any()].tolist()

    if anomalous_tickers:
        print(f"Warning: following tickers had extreme price volatility and are removed from the backtest:")
        for ticker in anomalous_tickers:
            print(f" - {ticker}") # This is actually extremely important lol

        prices_df.drop(columns=anomalous_tickers, inplace=True)


    prices_df.replace(0, np.nan, inplace=True)
    prices_df.bfill(inplace=True)
    prices_df.ffill(inplace=True)
    start_date = max(prices_df.index.min(), allocations_df.index.min())
    end_date = prices_df.index.max()
    
    prices_df = prices_df.loc[start_date:end_date]
    allocations_df = allocations_df.reindex(prices_df.index, method='ffill')
    common_tickers = prices_df.columns.intersection(allocations_df.columns)
    prices_df = prices_df[common_tickers]
    allocations_df = allocations_df[common_tickers]
    
    # allocations_df = allocations_df.div(allocations_df.sum(axis=1), axis=0) # can normalize to 1 but mb not
    allocations_df.fillna(0, inplace=True)

    print(f"Backtest period: {start_date.date()} to {end_date.date()}")
    print(f"Number of tickers in backtest: {len(common_tickers)}")

    
    portfolio_values = pd.Series(index=prices_df.index, dtype=float)
    current_shares = pd.Series(0.0, index=common_tickers)
    cash = initial_investment

    portfolio_values.iloc[0] = initial_investment
    
    target_allocations = allocations_df.iloc[0].copy()
    prices = prices_df.iloc[0]

    #avoid investing in stocks with extremely low prices (< 0.01) ?
    # sus_low = prices.index[prices < 0.01]
    # if not sus_low.empty:
    #     tickers_to_allocate = target_allocations.index[target_allocations > 0]
    #     problem_tickers = sus_low.intersection(tickers_to_allocate)
    #     if not problem_tickers.empty:
    #         print(f"Warning: On initial rebalance, not investing in tickers with price < $0.01: {problem_tickers.tolist()}")
    #         target_allocations[problem_tickers] = 0

    target_investment = initial_investment * target_allocations
    with np.errstate(divide='ignore', invalid='ignore'):
        current_shares = target_investment / prices
    current_shares.fillna(0, inplace=True)
    
    invested_value = (current_shares * prices).sum()
    cash = initial_investment - invested_value
    portfolio_values.iloc[0] = invested_value + cash

    for i in range(1, len(prices_df)):
        start_of_day_portfolio_value = portfolio_values.iloc[i-1]
        prices_today = prices_df.iloc[i]

        is_scheduled_rebalance = not allocations_df.iloc[i].equals(allocations_df.iloc[i-1])
        
        if is_scheduled_rebalance and start_of_day_portfolio_value > 0:
            target_allocations = allocations_df.iloc[i].copy()
            target_investment = start_of_day_portfolio_value * target_allocations
            with np.errstate(divide='ignore', invalid='ignore'):
                new_shares = target_investment / prices_today
            new_shares.fillna(0, inplace=True)

            current_shares = new_shares
            invested_value = (current_shares * prices_today).sum()
            cash = start_of_day_portfolio_value - invested_value

        # calc portfolio value at the end of the day with current shares and EOD prices
        equity_value = (current_shares * prices_today).sum()
        total_portfolio_value = equity_value + cash
        
        if pd.isna(total_portfolio_value) or total_portfolio_value <= 0:
             portfolio_values.iloc[i] = portfolio_values.iloc[i-1] # Carry over last value
             current_shares.values[:] = 0 # Portfolio is worthless
             cash = 0
        else:
            portfolio_values.iloc[i] = total_portfolio_value

    portfolio_value = portfolio_values.rename("PortfolioValue")
    portfolio_value.ffill(inplace=True) # Fill any gaps if loop failed early

    portfolio_daily_returns = portfolio_value.pct_change()
    portfolio_daily_returns.replace([np.inf, -np.inf], np.nan, inplace=True)
    portfolio_daily_returns.fillna(0, inplace=True)

    # Use a small epsilon to avoid division by zero if std is 0
    std_dev = portfolio_daily_returns.std()
    if std_dev > 1e-8:
        sharpe_ratio = (portfolio_daily_returns.mean() / std_dev) * np.sqrt(252)
    else:
        sharpe_ratio = 0.0

    cumulative_max = portfolio_value.cummax()
    drawdown = (portfolio_value - cumulative_max) / cumulative_max
    max_drawdown = drawdown.min()

    num_years = (portfolio_value.index[-1] - portfolio_value.index[0]).days / 365.25
    total_return = (portfolio_value.iloc[-1] / portfolio_value.iloc[0]) - 1
    
    if num_years > 1e-3:
        annualized_return = (1 + total_return) ** (1 / num_years) - 1
    else:
        annualized_return = total_return

    if abs(max_drawdown) > 1e-8:
        calmar_ratio = annualized_return / abs(max_drawdown)
    else:
        calmar_ratio = np.inf

    print("\nBacktest Results:")
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
    update_fund_data(cik, {"backtest_results": results})
    print(f"Saved backtest results for CIK {cik} to top_funds.json")

    output_dir = './sec/backtests'
    os.makedirs(output_dir, exist_ok=True)

    csv_path = os.path.join(output_dir, f"{cik}_backtest_values.csv")
    portfolio_value.to_csv(csv_path)
    print(f"BT values saved to: {csv_path}")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=portfolio_value.index, 
        y=portfolio_value,
        mode='lines',
        name='Portfolio Value'
    ))
    fig.update_layout(
        title=f'Hedge Fund Backtest: CIK {cik}',
        xaxis_title='Date',
        yaxis_title='Portfolio Value (USD)',
        template='plotly_white'
    )
    html_path = os.path.join(output_dir, f"{cik}_backtest.html")
    fig.write_html(html_path)
    print(f"Backtest graph saved to: {html_path}")


if __name__ == '__main__':
    # renaissance_cik = '1037389'
    # backtest_hedge_fund(renaissance_cik)
    appaloosa = '0001006438'
    backtest_hedge_fund(appaloosa)