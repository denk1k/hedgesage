import requests
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup
import json
import time
import os

def update_fund_data(cik, new_data):
    top_funds_path = './top_funds.json'
    try:
        with open(top_funds_path, 'r') as f:
            all_funds = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_funds = {}

    cik = cik.zfill(10)
    if cik in all_funds:
        all_funds[cik].update(new_data)
    else:
        all_funds[cik] = new_data

    with open(top_funds_path, 'w') as f:
        json.dump(all_funds, f, indent=4)

def fetch_cusip_on_fmp(cusip: str):
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        print("Error: FMP_API_KEY environment variable not set.")
        return "STOP"

    url = f"https://financialmodelingprep.com/api/v3/cusip/{cusip}?apikey={api_key}"
    try:
        response = requests.get(url)
        if response.status_code == 429 or response.status_code == 403:
            print("A non-recoverable error occurred. There is no point in proceeding of CUSIP fetching via FMP.")
            return "STOP" # this usually means that the free allowment of 250 requests per day had been hit, so continuing is pointless.
        try:
            response.raise_for_status()
            data = response.json()
            if data and isinstance(data, list) and data[0].get("ticker"):
                print(f"Found ticker for {cusip}: {data[0]['ticker']}")
                return data[0]["ticker"]
            else:
                print(f"Error: Ticker not found for CUSIP {cusip}.")
                return "N/A"
        except Exception as e:
            print(f"ERR on FMP API @ CUSIP {cusip}: {e}")
    except IndexError:
        print(f"Error: Empty response for CUSIP {cusip}.")
        return "N/A"

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

                xml_url = None
                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href and ('infotable.xml' in href.lower() or 'holding.xml' in href.lower()):
                        xml_url = f"https://www.sec.gov{href}"
                        break

                if not xml_url:
                    for link in soup.find_all('a'):
                        href = link.get('href')
                        if href and href.lower().endswith('.xml') and 'primary_doc.xml' not in href.lower():
                            xml_url = f"https://www.sec.gov{href}"
                            break

                if not xml_url:
                    primary_document = filings_data['filings']['recent']['primaryDocument'][i]
                    xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/{primary_document}"
                
                return xml_url

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
        if not xml_content.strip().startswith(b'<'):
            print(f"Skipping non-XML from {xml_url}")
            return pd.DataFrame()
        root = ET.fromstring(xml_content)

        holdings = []
        
        namespace = {'ns': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}
        info_tables = root.findall('ns:infoTable', namespace)

        if info_tables:
            for info_table in info_tables:
                name_node = info_table.find('ns:nameOfIssuer', namespace)
                cusip_node = info_table.find('ns:cusip', namespace)
                value_node = info_table.find('ns:value', namespace)
                shares_node = info_table.find('ns:shrsOrPrnAmt/ns:sshPrnamt', namespace)
                
                if all(node is not None for node in [name_node, cusip_node, value_node, shares_node]):
                    holding = {
                        'nameOfIssuer': name_node.text,
                        'cusip': cusip_node.text,
                        'value': float(value_node.text) * 1000,
                        'shares': int(shares_node.text)
                    }
                    holdings.append(holding)
        else: # if above fails try w no namespace
            for info_table in root.findall('infoTable'):
                name_node = info_table.find('nameOfIssuer')
                cusip_node = info_table.find('cusip')
                value_node = info_table.find('value')
                shares_node = info_table.find('shrsOrPrnAmt/sshPrnamt')

                if all(node is not None for node in [name_node, cusip_node, value_node, shares_node]):
                    holding = {
                        'nameOfIssuer': name_node.text,
                        'cusip': cusip_node.text,
                        'value': float(value_node.text) * 1000,
                        'shares': int(shares_node.text)
                    }
                    holdings.append(holding)

        return pd.DataFrame(holdings)

    except Exception as e:
        print(f"Error parsing 13F holdings from {xml_url}: {e}")
        return pd.DataFrame()

def get_cusip_tickers(cusips_to_find, max_retries=8, bf=1.0):
    api_url = 'https://api.openfigi.com/v3/mapping' #openfigi has issues though - not all cusips are found. For that the function financialmodelingprep API is used to fill in the missing values.
    headers = {'Content-Type': 'application/json'}
    batch_size = 10

    # identify which CUSIPs are new
    existing_map = load_cusip_ct()
    new_cusips = [c for c in cusips_to_find if c not in existing_map]
    cusips_with_na = [c for c in cusips_to_find if c in existing_map and existing_map[c] == "N/A"]

    if not (new_cusips or cusips_with_na):
        print("All CUSIPs found in local cache. No API calls needed.")
        return existing_map
    # elif new_cusips:
    #     print("New cusips available")
    # elif cusips_with_na:
    #     print("Cusips with n/a available")

    print(f"Found {len(existing_map)} cached CUSIPs. Fetching tickers for {len(new_cusips)} new unique CUSIPs and filling {len(cusips_with_na)} CUSIPs containing N/As...")
    if new_cusips:
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
    updated_count = 0
    for cusip, ticker in existing_map.items():
        if ticker == "N/A":
            new_ticker = fetch_cusip_on_fmp(cusip) # over time if run daily this will procedurally remove the N/A's from the cusip collection leading to more precise allocations
            if new_ticker == "STOP":
                break
            if new_ticker != "N/A":
                existing_map[cusip] = new_ticker
                updated_count += 1
            time.sleep(0.5)
    save_cusip_ct(existing_map)
    print("Updated", updated_count, "via the FMP API.")
    return existing_map

def generate_investment_allocations(cik):
    cik = cik.zfill(10)
    print(f"--- Processing CIK: {cik} ---")
    latest_13f_url = get_latest_13f_filing_url(cik)
    if not latest_13f_url:
        print("Could not find the latest 13F filing URL.")
        return

    print(f"Found 13F info table at: {latest_13f_url}")
    holdings_13f = parse_13f_holdings(latest_13f_url)
    if holdings_13f.empty:
        print("No holdings data could be parsed from 13F filing.")
        return

    unique_cusips = holdings_13f['cusip'].unique().tolist()
    cusip_to_ticker_map = get_cusip_tickers(unique_cusips)
    holdings_13f['ticker'] = holdings_13f['cusip'].map(cusip_to_ticker_map)
    total_portfolio_value = holdings_13f['value'].sum()
    holdings_13f['allocation_percent'] = (holdings_13f['value'] / total_portfolio_value) * 100

    final_columns = ['ticker', 'nameOfIssuer', 'cusip', 'value', 'shares', 'allocation_percent']
    f_alloc = holdings_13f.sort_values(by='allocation_percent', ascending=False)[final_columns]
    output_dir = './sec/allocations'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{cik}.csv")
    f_alloc.to_csv(output_path, index=False)

    print(f"\nTotal portfolio value from 13F: ${total_portfolio_value:,.2f}")
    print(f"Report saved to: {output_path}")
    print("\nInvestment Allocations:")
    print(f_alloc.to_string())

def get_all_13f_furls(cik):
    initial_url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    headers = {'User-Agent': 'denk1k no@gmail.com'}
    all_urls = []

    urls_to_process = [initial_url]
    processed_file_names = set()

    def process_filing_data(filing_block, cik_num, headers_dict):
        urls_found = []
        forms = filing_block.get('form', [])
        accession_numbers = filing_block.get('accessionNumber', [])
        report_dates = filing_block.get('reportDate', [])
        filing_dates = filing_block.get('filingDate', [])
        primary_documents = filing_block.get('primaryDocument', [])

        for i, form in enumerate(forms):
            if form == '13F-HR':
                accession_number_raw = accession_numbers[i]
                accession_number = accession_number_raw.replace('-', '')
                report_date = report_dates[i]
                filing_date = filing_dates[i]
                primary_document = primary_documents[i]

                filing_directory_url = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession_number}/"
                try:
                    dir_response = requests.get(filing_directory_url, headers=headers_dict)
                    dir_response.raise_for_status()
                    soup = BeautifulSoup(dir_response.content, 'html.parser')
                    xml_url = None
                    for link in soup.find_all('a'):
                        href = link.get('href')
                        if href and ('infotable.xml' in href.lower() or 'holding.xml' in href.lower()):
                            xml_url = f"https://www.sec.gov{href}"
                            break
                    
                    if not xml_url:
                        for link in soup.find_all('a'):
                            href = link.get('href')
                            if href and href.lower().endswith('.xml') and 'primary_doc.xml' not in href.lower():
                                xml_url = f"https://www.sec.gov{href}"
                                break

                    if not xml_url:
                        xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession_number}/{primary_document}"

                    urls_found.append({'reportDate': report_date, 'url': xml_url, 'filingDate': filing_date, 'accessionNumber': accession_number_raw})
                except requests.exceptions.RequestException as e:
                    print(f"Could not fetch directory for {accession_number}: {e}")
                    continue

        return urls_found

    try:
        response = requests.get(initial_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if 'filings' in data and 'recent' in data['filings']:
            all_urls.extend(process_filing_data(data['filings']['recent'], cik, headers))

        if 'filings' in data and 'files' in data['filings']:
            for file_info in data['filings']['files']:
                file_name = file_info.get('name')
                if file_name:
                    urls_to_process.append(f"https://data.sec.gov/submissions/{file_name}")
        
        processed_file_names.add(initial_url.split('/')[-1])

        for url in urls_to_process:
            file_name = url.split('/')[-1]
            if file_name in processed_file_names:
                continue

            print(f"Processing older filings from: {file_name}")
            try:
                resp = requests.get(url, headers=headers)
                resp.raise_for_status()
                older_data = resp.json()
                all_urls.extend(process_filing_data(older_data, cik, headers))
                processed_file_names.add(file_name)
            except requests.exceptions.RequestException as e:
                print(f"couldnt fetch or process older filing file {url}: {e}")
                continue

    except requests.exceptions.RequestException as e:
        print(f"Error fetching initial submissions for CIK {cik}: {e}")
        return []

    print(f"Found {len(all_urls)} total 13F-HR filings for CIK {cik}.")
    return all_urls

def fetch_all_past_allocations(cik):
    print(f"--- Fetching all past allocations for CIK: {cik} ---")
    furls = get_all_13f_furls(cik)
    if not furls:
        print("Could not find any 13F filings.")
        return

    if furls:
        earliest_date = min(pd.to_datetime(f['reportDate']) for f in furls)
        update_fund_data(cik, {'earliest_filing_date': earliest_date.strftime('%Y-%m-%d')})
        print(f"Set earliest filing date for CIK {cik} to {earliest_date.strftime('%Y-%m-%d')}")

    for filing in furls:
        report_date = filing['reportDate']
        filing_date = filing['filingDate']
        accession_number = filing['accessionNumber']
        xml_url = filing['url']

        output_dir = f'./sec/past_allocations/{cik}'
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{report_date}.csv")

        if os.path.exists(output_path):
            # For now, if a file for a report date exists, its just skipped.
            print(f"Skipping filing for {report_date} - already fetched")
            continue
        
        print(f"\n--- Processing filing for {report_date} ---")
        print(f"Found 13F info table at: {xml_url}")

        holdings_13f = parse_13f_holdings(xml_url)
        if holdings_13f.empty:
            print(f"No holdings data could be parsed from the 13F filing for {report_date}.")
            continue

        unique_cusips = holdings_13f['cusip'].unique().tolist()
        cusip_to_ticker_map = get_cusip_tickers(unique_cusips)
        holdings_13f['ticker'] = holdings_13f['cusip'].map(cusip_to_ticker_map)
        total_portfolio_value = holdings_13f['value'].sum()
        holdings_13f['allocation_percent'] = (holdings_13f['value'] / total_portfolio_value) * 100

        final_columns = ['ticker', 'nameOfIssuer', 'cusip', 'value', 'shares', 'allocation_percent']
        f_alloc = holdings_13f.sort_values(by='allocation_percent', ascending=False)[final_columns]
        
        f_alloc['filingDate'] = filing_date
        f_alloc['reportDate'] = report_date
        f_alloc['accessionNumber'] = accession_number

        f_alloc.to_csv(output_path, index=False)

        print(f"Report at {report_date} saved to: {output_path}")

if __name__ == "__main__":
    renaissance_cik = '0001050464' # renaissance technologies
    generate_investment_allocations(renaissance_cik)
