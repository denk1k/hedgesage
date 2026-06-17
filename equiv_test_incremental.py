import json
import os
import glob
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.getcwd())

from backtester import backtest_hedge_fund
from runner_incremental_backtests import run_incremental_backtests

BACKTEST_DIR = "./sec/backtests"
TOP_FUNDS = "top_funds.json"
TRUNCATE_ROWS = 40
PV_RTOL = 1e-6
METRIC_RTOL = 1e-6


def pick_cik(funds):
    for raw in funds:
        c = raw.zfill(10)
        if glob.glob(f"./sec/past_allocations/{c}/*.csv"):
            return raw, c
    return None, None


def read_pv(path):
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def read_metrics(raw_cik):
    with open(TOP_FUNDS) as f:
        return json.load(f).get(raw_cik, {}).get("backtest_results", {})


def main():
    incr = None
    with open(TOP_FUNDS) as f:
        original_text = f.read()
    funds_backup = json.loads(original_text)

    raw_cik, cik = pick_cik(funds_backup)
    if cik is None:
        print("EQUIV_TEST: no CIK with allocation files found.")
        return 1
    print(f"EQUIV_TEST: using CIK {raw_cik} -> {cik}")
    csv_path = os.path.join(BACKTEST_DIR, f"{cik}_backtest_values.csv")

    ok = True
    try:
        # 1) Establish a complete baseline CSV (on-disk prices) so we have
        #    something to truncate into a "stale" prior backtest.
        backtest_hedge_fund(cik, download_data=False)
        if not os.path.exists(csv_path):
            print("EQUIV_TEST: baseline run produced no CSV.")
            return 1
        baseline = read_pv(csv_path)
        if len(baseline) <= TRUNCATE_ROWS + 5:
            print(f"EQUIV_TEST: only {len(baseline)} rows; too short to test.")
            return 1

        # 2) Simulate a stale prior backtest by dropping the tail.
        stale = baseline.iloc[:-TRUNCATE_ROWS].copy()
        stale.to_csv(csv_path)
        print(f"EQUIV_TEST: stale end={stale.index.max().date()} baseline end={baseline.index.max().date()}")

        # 3) Restrict top_funds to this CIK so the run stays bounded, then run
        #    the incremental updater. Phase 2 downloads FRESH prices, so it can
        #    legitimately extend past the baseline end date.
        with open(TOP_FUNDS, "w") as f:
            json.dump({raw_cik: funds_backup[raw_cik]}, f)
        run_incremental_backtests()
        incr = read_pv(csv_path)
        incr_metrics = read_metrics(raw_cik)

        # 4) FAIR GROUND TRUTH: re-run the full backtest now that fresh prices
        #    are on disk (downloaded in step 3). Both sides now use IDENTICAL
        #    price data, so a correct incremental splice must reproduce the full
        #    run over their shared dates AND reach the same end date. This is the
        #    apples-to-apples comparison the previous version lacked (it diffed
        #    incremental-on-fresh-data against full-on-stale-data, so the metrics
        #    diverged purely because the date ranges differed).
        backtest_hedge_fund(cik, download_data=False)
        truth = read_pv(csv_path)
        truth_metrics = read_metrics(raw_cik)

        # --- Assertions ---
        if set(incr.columns) != set(truth.columns):
            print(f"EQUIV_TEST: column mismatch truth={list(truth.columns)} incr={list(incr.columns)}")
            ok = False

        if incr.index.max() != truth.index.max():
            print(f"EQUIV_TEST: end-date mismatch truth={truth.index.max().date()} incr={incr.index.max().date()}")
            ok = False

        overlap = truth.index.intersection(incr.index)
        for col in truth.columns:
            if col not in incr.columns:
                continue
            a = truth.loc[overlap, col]
            b = incr.loc[overlap, col]
            denom = a.abs().replace(0, np.nan)
            rel = ((a - b).abs() / denom).dropna()
            mx = float(rel.max()) if not rel.empty else 0.0
            print(f"EQUIV_TEST: {col} max rel diff over overlap = {mx:.3e}")
            if mx > PV_RTOL:
                ok = False
                print(rel.sort_values(ascending=False).head(5))

        for k, v in truth_metrics.items():
            if k not in incr_metrics:
                print(f"EQUIV_TEST: metric {k} missing after incremental.")
                ok = False
                continue
            try:
                fv, fi = float(v), float(incr_metrics[k])
                if abs(fv - fi) > max(METRIC_RTOL, abs(fv) * METRIC_RTOL):
                    print(f"EQUIV_TEST: metric {k} differs truth={fv} incr={fi}")
                    ok = False
            except (TypeError, ValueError):
                pass
    finally:
        # Restore the original top_funds.json (all funds). The CSV is left as the
        # latest full run, which already reflects fresh on-disk prices.
        with open(TOP_FUNDS, "w") as f:
            f.write(original_text)

    print("EQUIV_TEST_RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
