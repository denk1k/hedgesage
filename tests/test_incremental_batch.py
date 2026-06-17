import json
import os
import pandas as pd
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from runner_incremental_backtests import run_incremental_backtests

# Mock top_funds.json with a subset
mock_funds = {
    "0001647251": {
        "name": "TCI FUND MANAGEMENT LTD",
        "earliest_filing_date": "2015-06-30"
    },
    "0001275228": {
        "name": "SHENKMAN CAPITAL MANAGEMENT INC",
        "earliest_filing_date": "2003-12-31"
    }
}

def test_batch_run():
    # Backup original top_funds.json
    if os.path.exists("top_funds.json"):
        os.rename("top_funds.json", "top_funds.json.bak")
    
    try:
        with open("top_funds.json", "w") as f:
            json.dump(mock_funds, f)
            
        print("Running incremental backtests with mock funds...")
        run_incremental_backtests()
        
    finally:
        # Restore original
        if os.path.exists("top_funds.json.bak"):
            os.rename("top_funds.json.bak", "top_funds.json")

if __name__ == "__main__":
    test_batch_run()
