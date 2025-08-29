# This script cannot be run via GH actions, since historical data consumes a ton of resources.
from backtester import backtest_hedge_fund
import json
if __name__ == "__main__":
    with open("top_funds.json", "r") as f:
        top_funds = json.load(f)
    for name, cik in top_funds.items():
        print(f"Generating backtests for a fund {name}")
        backtest_hedge_fund(cik)