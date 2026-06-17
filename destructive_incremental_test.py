import json
import os
import glob
import random
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.getcwd())

from runner_incremental_backtests import run_incremental_backtests

BACKTESTS_DIR = "./sec/backtests"
TOP_FUNDS = "top_funds.json"
N_SAMPLE = 10
PV_RTOL = 1e-6
SEED = 20260617


def read_pv(path):
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def cik_of(path):
    return os.path.basename(path).replace("_backtest_values.csv", "")


def main():
    rng = random.Random(SEED)

    with open(TOP_FUNDS) as f:
        original_top_funds_text = f.read()
    full_funds = json.loads(original_top_funds_text)

    # Only sample backtests whose CIK is still present in top_funds.json AND
    # that have enough rows that dropping the last day leaves a history the
    # incremental runner can splice from. Skip any with duplicate timestamps.
    padded_to_raw = {raw.zfill(10): raw for raw in full_funds}
    all_csvs = sorted(glob.glob(os.path.join(BACKTESTS_DIR, "*_backtest_values.csv")))
    candidates = []
    for path in all_csvs:
        if cik_of(path) not in padded_to_raw:
            continue
        try:
            df = read_pv(path)
        except Exception:
            continue
        if len(df) >= 5 and not df.index.has_duplicates:
            candidates.append(path)

    if len(candidates) < N_SAMPLE:
        print(f"DESTRUCTIVE_TEST: only {len(candidates)} usable backtests; need {N_SAMPLE}.")
        return 1

    sample = rng.sample(candidates, N_SAMPLE)
    sample_ciks = [cik_of(p) for p in sample]
    print("DESTRUCTIVE_TEST: selected CIKs:", sample_ciks)

    originals = {p: read_pv(p) for p in sample}

    ok = True
    try:
        # 1) Destructive step: drop the LAST day from each selected backtest CSV.
        dropped_dates = {}
        for p in sample:
            df = originals[p]
            last_date = df.index.max()
            dropped_dates[p] = last_date
            truncated = df.iloc[:-1].copy()
            truncated.to_csv(p)
            print(f"DESTRUCTIVE_TEST: {cik_of(p)} dropped last day {last_date.date()} "
                  f"(now ends {truncated.index.max().date()})")

        # 2) Restrict top_funds.json to ONLY the sampled CIKs so the incremental
        #    batch processes exactly these 10 funds and nothing else.
        subset = {padded_to_raw[c]: full_funds[padded_to_raw[c]] for c in sample_ciks}
        with open(TOP_FUNDS, "w") as f:
            json.dump(subset, f)

        # 3) Run the incremental backtester over the batch. It should rebuild the
        #    dropped tail for every one of the 10 funds (and may extend further
        #    with freshly downloaded prices).
        run_incremental_backtests()

        # 4) One assertion per fund (= 10 reconstruction tests): the dropped day
        #    must be back, and the reconstructed series must match the original
        #    over their shared dates within tolerance.
        for p in sample:
            cik = cik_of(p)
            orig = originals[p]
            recon = read_pv(p)
            dropped = dropped_dates[p]

            if dropped not in recon.index:
                print(f"DESTRUCTIVE_TEST: {cik} FAIL - dropped day {dropped.date()} not reconstructed")
                ok = False
                continue

            if set(orig.columns) != set(recon.columns):
                print(f"DESTRUCTIVE_TEST: {cik} FAIL - column mismatch "
                      f"orig={list(orig.columns)} recon={list(recon.columns)}")
                ok = False

            overlap = orig.index.intersection(recon.index)
            worst = 0.0
            for col in orig.columns:
                if col not in recon.columns:
                    continue
                a = orig.loc[overlap, col]
                b = recon.loc[overlap, col]
                denom = a.abs().replace(0, np.nan)
                rel = ((a - b).abs() / denom).dropna()
                mx = float(rel.max()) if not rel.empty else 0.0
                worst = max(worst, mx)
            verdict = "OK" if worst <= PV_RTOL else "FAIL"
            if worst > PV_RTOL:
                ok = False
            print(f"DESTRUCTIVE_TEST: {cik} reconstructed {dropped.date()} "
                  f"max rel diff over overlap = {worst:.3e} [{verdict}]")
    finally:
        # Always restore the original CSVs and the full top_funds.json.
        for p, df in originals.items():
            df.to_csv(p)
        with open(TOP_FUNDS, "w") as f:
            f.write(original_top_funds_text)

    print("DESTRUCTIVE_TEST_RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
