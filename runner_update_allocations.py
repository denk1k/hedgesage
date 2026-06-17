from fetch_hedge_fund_allocations import generate_investment_allocations
import json
import os
from datetime import datetime

def load_allocations_meta():
    path = './sec/allocations_meta.json'
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def save_allocations_meta(data):
    os.makedirs('./sec', exist_ok=True)
    path = './sec/allocations_meta.json'
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    with open("top_funds.json", "r") as f:
        top_funds = json.load(f)
    
    allocations_meta = load_allocations_meta()
    technical_update_date = datetime.now().strftime('%Y-%m-%d')
    
    for cik, info in top_funds.items():
        name = info["name"]
        print(f"Generating investment allocations for a fund {name}")
        
        # Check if allocations actually changed
        # We can check the modification time of the latest allocation file or return status from generate_investment_allocations
        # For now, let's assume generate_investment_allocations returns True if new data was found/saved
        latest_report_date = generate_investment_allocations(cik)
        
        if cik not in allocations_meta:
            allocations_meta[cik] = {}
            
        allocations_meta[cik]['technical_update_date'] = technical_update_date
        
        if latest_report_date:
             # If we have a report date, check if it's new compared to what is stored
             prev_practical_date = allocations_meta[cik].get('practical_update_date')
             if prev_practical_date != latest_report_date:
                 allocations_meta[cik]['practical_update_date'] = latest_report_date
                 print(f"Allocations practically updated for {name} to {latest_report_date}")
             else:
                 print(f"No practical update for {name} (still {latest_report_date})")
        else:
            print(f"Could not determine latest report date for {name}")

    save_allocations_meta(allocations_meta)