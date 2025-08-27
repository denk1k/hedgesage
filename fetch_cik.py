import requests
import json

def get_cik_by_comp_name(company_name):
    print(f"Searching for CIK for {company_name}...")
    url = f"https://efts.sec.gov/LATEST/search-index"
    headers = {'User-Agent': 'denk1k no@gmail.com'}
    params = {
        "q": company_name,
        "category": "form-filings",
        "startdt": "2001-01-01",
        "enddt": "2023-12-31",
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        search_results = response.json()

        if 'hits' in search_results and 'hits' in search_results['hits']:
            for hit in search_results['hits']['hits']:
                for i, display_name in enumerate(hit['_source']['display_names']):
                    if company_name.lower() in display_name.lower():
                        if i < len(hit['_source']['ciks']):
                            return str(hit['_source']['ciks'][i]).zfill(10)

        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching CIK: {e}")
        return None

if __name__ == "__main__":
    hedge_fund_name = "RENAISSANCE TECHNOLOGIES LLC"
    cik = get_cik_by_comp_name(hedge_fund_name)
    print(cik)
