import requests
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup
import json
import time
import os


def load_cusip_ct():
    path = './sec/cusip_conversion_table.json'
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def save_cusip_ct(data):
    os.makedirs('./sec', exist_ok=True)
    path = './sec/cusip_conversion_table.json'
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"CUSIP conversion table saved to {path}")

def get_latest_13f_filing_url(cik):
    filings_url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    headers = {'User-Agent': 'denk1k no@gmail.com'}

    try:
        response = requests.get(filings_url, headers=headers)
        response.raise_for_status()
        filings_data = response.json()

        for i, form in enumerate(filings_data['filings']['recent']['form']):
            if form == '13F-HR':
                accession_number_raw = filings_data['filings']['recent']['accessionNumber'][i]
                accession_number = accession_number_raw.replace('-', '')

                filing_directory_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/"
                dir_response = requests.get(filing_directory_url, headers=headers)
                dir_response.raise_for_status()

                soup = BeautifulSoup(dir_response.content, 'html.parser')
                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href and ('InfoTable.xml' in href or 'holding.xml' in href or 'infotable.xml' in href):
                        return f"https://www.sec.gov{href}"

                primary_document = filings_data['filings']['recent']['primaryDocument'][i]
                return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/{primary_document}"

    except requests.exceptions.RequestException as e:
        print(f"Error fetching filings index for CIK {cik}: {e}")
        return None

    return None

def parse_13f_holdings(xml_url):
    if not xml_url:
        return pd.DataFrame()

    headers = {'User-Agent': 'denk1k no@gmail.com'}

    try:
        response = requests.get(xml_url, headers=headers)
        response.raise_for_status()
        xml_content = response.content
        root = ET.fromstring(xml_content)

        holdings = []
        namespace = {'ns': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}

        for info_table in root.findall('ns:infoTable', namespace):
            holding = {
                'nameOfIssuer': info_table.find('ns:nameOfIssuer', namespace).text,
                'cusip': info_table.find('ns:cusip', namespace).text,
                'value': float(info_table.find('ns:value', namespace).text) * 1000,
                'shares': int(info_table.find('ns:shrsOrPrnAmt/ns:sshPrnamt', namespace).text)
            }
            holdings.append(holding)

        return pd.DataFrame(holdings)

    except (requests.exceptions.RequestException, ET.ParseError) as e:
        print(f"Error parsing 13F holdings from {xml_url}: {e}")
        return pd.DataFrame()

def get_tickers_from_cusips(cusips_to_find, max_retries=8, bf=1.0):
    api_url = 'https://api.openfigi.com/v3/mapping'
    headers = {'Content-Type': 'application/json'}
    batch_size = 10

    # Load existing conversion table and identify which CUSIPs are new
    existing_map = load_cusip_ct()
    new_cusips = [c for c in cusips_to_find if c not in existing_map]

    if not new_cusips:
        print("All CUSIPs found in local cache. No API calls needed.")
        return existing_map

    print(f"Found {len(existing_map)} cached CUSIPs. Fetching tickers for {len(new_cusips)} new unique CUSIPs...")

    newly_fetched_tickers = {}
    for i in range(0, len(new_cusips), batch_size):
        batch_cusips = new_cusips[i:i + batch_size]
        jobs = [{'idType': 'ID_CUSIP', 'idValue': cusip} for cusip in batch_cusips]

        retries = 0
        while retries <= max_retries:
            try:
                response = requests.post(api_url, headers=headers, data=json.dumps(jobs))
                if response.status_code == 429:
                    wt = bf * (2 ** retries)
                    print(f"Rate limit hit. Waiting {wt:.2f}s before retry {retries + 1}/{max_retries}...")
                    time.sleep(wt)
                    retries += 1
                    continue

                response.raise_for_status()
                mapping_results = response.json()
                for idx, result in enumerate(mapping_results):
                    original_cusip = batch_cusips[idx]
                    if 'data' in result and result['data']:
                        newly_fetched_tickers[original_cusip] = result['data'][0].get('ticker', 'N/A')
                    else:
                        newly_fetched_tickers[original_cusip] = 'N/A'
                break
            except requests.exceptions.RequestException as e:
                print(f"error occurred for batch starting at index {i}: {e}")
                for cusip in batch_cusips:
                    newly_fetched_tickers[cusip] = 'Error'

        if retries > max_retries:
            print(f"Max retries exceeded for batch starting at {i}. Marking as Error.")
            for cusip in batch_cusips:
                newly_fetched_tickers[cusip] = 'Error'

        time.sleep(1)
    existing_map.update(newly_fetched_tickers)
    save_cusip_ct(existing_map)

    return existing_map

def generate_investment_allocations(cik):
    print(f"--- Processing CIK: {cik} ---")
    latest_13f_url = get_latest_13f_filing_url(cik)
    if not latest_13f_url:
        print("Could not find the latest 13F filing URL.")
        return

    print(f"Found 13F info table at: {latest_13f_url}")
    holdings_13f = parse_13f_holdings(latest_13f_url)
    if holdings_13f.empty:
        print("No holdings data could be parsed from the 13F filing.")
        return

    unique_cusips = holdings_13f['cusip'].unique().tolist()
    cusip_to_ticker_map = get_tickers_from_cusips(unique_cusips)
    holdings_13f['ticker'] = holdings_13f['cusip'].map(cusip_to_ticker_map)
    total_portfolio_value = holdings_13f['value'].sum()
    holdings_13f['allocation_percent'] = (holdings_13f['value'] / total_portfolio_value) * 100

    final_columns = ['ticker', 'nameOfIssuer', 'cusip', 'value', 'shares', 'allocation_percent']
    final_allocations = holdings_13f.sort_values(by='allocation_percent', ascending=False)[final_columns]
    output_dir = './sec/allocations'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{cik}.csv")
    final_allocations.to_csv(output_path, index=False)

    print(f"\nTotal portfolio value from 13F: ${total_portfolio_value:,.2f}")
    print(f"Report saved to: {output_path}")
    print("\nInvestment Allocations:")
    print(final_allocations.to_string())

if __name__ == "__main__":
    renaissance_cik = '1037389' # renaissance technologies
    generate_investment_allocations(renaissance_cik)
