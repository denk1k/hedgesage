# This script can be run via github actions very well, because it does not require a lot of storage neither (too many) runtime minutes.
from fetch_hedge_fund_allocations import generate_investment_allocations
import json
if __name__ == "__main__":
    with open("top_funds.json", "r") as f:
        top_funds = json.load(f)
    for fund in top_funds:
        cik = fund["cik"]
        name = fund["name"]
        print(f"Generating investment allocations for a fund {name}")
        generate_investment_allocations(cik)