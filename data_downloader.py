import os
import sys
import time
import concurrent.futures
import yfinance as yf
import pandas as pd
from tqdm import tqdm
from datetime import datetime, timedelta
from fetch_hedge_fund_allocations import get_all_13f_furls, parse_13f_holdings, get_cusip_tickers

def tickers_from_cik(cik):
    print(f"--- Getting all tickers for CIK: {cik} ---")
    furls = get_all_13f_furls(cik)
    if not furls:
        print("Could not find any 13F filings.")
        return set(), None

    all_cusips = set()
    first_filing_date = None

    for filing in furls:
        report_date = filing['reportDate']
        if first_filing_date is None or report_date < first_filing_date:
            first_filing_date = report_date
        
        xml_url = filing['url']
        holdings_df = parse_13f_holdings(xml_url)
        if not holdings_df.empty:
            all_cusips.update(holdings_df['cusip'].unique())

    if not all_cusips:
        print("No CUSIPs in any filings.")
        return set(), None

    print(f"Found {len(all_cusips)} unique CUSIPs across all filings.")
    cusip_to_ticker_map = get_cusip_tickers(list(all_cusips))
    
    all_tickers = {ticker for ticker in cusip_to_ticker_map.values() if ticker and ticker != 'N/A' and ticker != 'Error'}
    print(f"Found {len(all_tickers)} unique tickers.")
    
    return all_tickers, first_filing_date


def ticker_hist_data(ticker, sdate, edate):
    retries = 5
    delay = 2
    for i in range(retries):
        try:
            t = yf.Ticker(ticker)
            df = t.history(start=sdate, end=edate)

            if df.empty:
                ticker_info = yf.Ticker(ticker)
                if ticker_info.history(period="1d").empty:
                     print(f"{ticker} mb invalid or delisted.")
                else:
                     print(f"No data found for {ticker} in date range.")
                return None
            
            df.reset_index(inplace=True)
            df.rename(columns={'Date': 'date'}, inplace=True)
            df.columns = [col.lower() for col in df.columns]
            if df['date'].dt.tz is not None:
                df['date'] = df['date'].dt.tz_localize(None)
            return df
        except Exception as e:
            if "Too Many Requests" in str(e) or "Rate limited" in str(e) or "429" in str(e):
                if i < retries - 1:
                    print(f"Rate limited for {ticker}. Will retry in {delay} seconds...")
                    time.sleep(delay)
                    delay *= 2 
                else:
                    print(f"Error for YF ticker {ticker}, {retries} retries: {e}")
                    return None
            else:
                print(f"Err YF ticker {ticker}: {e}")
                return None
    return None


def get_ticker_data(ticker, req_start, req_end):
    output_dir = './data/historical'
    output_path = os.path.join(output_dir, f"{ticker}.csv".replace("/", "_"))
    
    new_data_list = []

    if os.path.exists(output_path):
        print(f"File for {ticker} exists. Checking date range...")
        existing_df = pd.read_csv(output_path, parse_dates=['date'])
        existing_start = existing_df['date'].min()
        existing_end = existing_df['date'].max()
        if existing_start <= req_start and existing_end >= req_end:
            print(f"Data for {ticker} is already up to date.")
            return
        
        new_data_list.append(existing_df)

        # missing data at the end
        if existing_end < req_end:
            print(f"Getting new data for {ticker} from {existing_end.date()} to {req_end.date()}")
            df_append = ticker_hist_data(ticker, (existing_end + timedelta(days=1)).strftime('%Y-%m-%d'), req_end.strftime('%Y-%m-%d'))
            if df_append is not None and not df_append.empty:
                new_data_list.append(df_append)

        # missing data at the beginning
        if existing_start > req_start:
            print(f"Getting old data for {ticker} from {req_start.date()} to {existing_start.date()}")
            df_prepend = ticker_hist_data(ticker, req_start.strftime('%Y-%m-%d'), (existing_start - timedelta(days=1)).strftime('%Y-%m-%d'))
            if df_prepend is not None and not df_prepend.empty:
                new_data_list.append(df_prepend)
        
    else:
        print(f"No existing data for {ticker}. Downloading full history...")
        df_full = ticker_hist_data(ticker, req_start.strftime('%Y-%m-%d'), req_end.strftime('%Y-%m-%d'))
        if df_full is not None and not df_full.empty:
            new_data_list.append(df_full)

    if not new_data_list:
        print(f"Couldn't get data for {ticker}.")
        return

    final_df = pd.concat(new_data_list)
    final_df.drop_duplicates(subset=['date'], keep='first', inplace=True)
    final_df.sort_values(by='date', ascending=True, inplace=True)
    
    try:
        final_df.to_csv(output_path, index=False)
    except Exception as e:
        print(e)
    print(f"Successfully saved updated data for {ticker} to {output_path}")

def download_data_since_first_filing(cik):
    all_tickers, first_filing_date_str = tickers_from_cik(cik)
    
    if not all_tickers or not first_filing_date_str:
        print("couldnt determine tickers or first filing date.")
        return

    req_start = pd.to_datetime(first_filing_date_str)
    req_end = pd.to_datetime(datetime.now().strftime('%Y-%m-%d'))
    
    print(f"Req data range: {req_start.date()} to {req_end.date()}")
    
    output_dir = './data/historical'
    os.makedirs(output_dir, exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {executor.submit(get_ticker_data, ticker, req_start, req_end): ticker for ticker in all_tickers}
        
        for future in tqdm(concurrent.futures.as_completed(future_to_ticker), total=len(all_tickers), desc="Downloading data"):
            ticker = future_to_ticker[future]
            try:
                future.result()
            except Exception as exc:
                print('exception', ticker, exc)