'''
runner_do_point_in_time_backtests.py

Builds a 'Hedge Fund Investment ETF': a point-in-time simulated portfolio that, at
every allocation-refresh window, selects the funds passing the same filter as the
website (site_src/src/routes/+page.svelte) and allocates capital to them in
proportion to each fund's Sharpe ratio (sharpe_i / sum(sharpe_j)).

It does NOT re-run any per-fund backtest. It overlays the already-computed 'Copied'
portfolio-value series (PortfolioValue_copy) from
./sec/backtests/{cik}_backtest_values.csv, holding a fixed number of 'units' of each
fund's curve through each interval and re-weighting at the next window.

The ETF timeline starts at the first refresh window once at least one fund has at
least MIN_MONTHS_BEFORE_START months of copied data (default 24 = 2 years).

Does NOT touch runner_do_backtests.py or runner_incremental_backtests.py.
'''

import argparse
import json
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from tqdm import tqdm

from backtester import prepare_allocations

# --- Config (all customizable) ---
MIN_MONTHS_BEFORE_START = 24
INITIAL_INVESTMENT = 1_000_000

# How often (in items) to emit a status line when running with --quiet.
PROGRESS_EVERY = 100

FILTER_METRIC = 'copy'
PORTFOLIO_VALUE_COL = f'PortfolioValue_{FILTER_METRIC}'

# Recompute selection stats point-in-time (only data up to each window, no
# lookahead). Set False to use lifetime backtest_results from top_funds.json.
POINT_IN_TIME_STATS = True

# Selection filter, mirroring +page.svelte defaults EXACTLY, including the full
# MIN_MONTHS=120 (10-year) track-record requirement. This is applied
# point-in-time to every fund at every rebalance window (no look-ahead): a fund
# only qualifies once it has at least 120 months of copied history as of that
# window.
MIN_SHARPE = 0.5
MIN_CALMAR = 0.3
MAX_DRAWDOWN = -0.40
MIN_TOTAL_RETURN = 1.5
MIN_ANNUALIZED_RETURN = 0.10
MIN_MONTHS = 120

# The ETF timeline does not begin until the first rebalance window at which at
# least this many funds pass the full filter above. Earlier windows (where too
# few funds have a 120-month point-in-time track record) are skipped entirely,
# so the backtest no longer starts back in 2002/2016 with one barely-eligible
# fund.
MIN_QUALIFYING_FUNDS_AT_START = 10

TOP_FUNDS_PATH = 'top_funds.json'
BACKTESTS_DIR = './sec/backtests'
OUTPUT_VALUES_CSV = './sec/pit_etf_backtest_values.csv'
OUTPUT_META_JSON = './sec/pit_etf_meta.json'
OUTPUT_HTML = './sec/pit_etf_backtest.html'
WRITE_HTML = True


def compute_stats(series):
    series = series.dropna()
    if len(series) < 2 or series.iloc[0] <= 0:
        return None
    daily_returns = series.pct_change()
    daily_returns.replace([np.inf, -np.inf], np.nan, inplace=True)
    daily_returns.fillna(0, inplace=True)
    std_dev = daily_returns.std()
    sharpe_ratio = (daily_returns.mean() / std_dev) * np.sqrt(252) if std_dev > 0 else 0.0
    cumulative_max = series.cummax()
    drawdown = (series - cumulative_max) / cumulative_max
    max_drawdown = drawdown.min()
    num_years = (series.index[-1] - series.index[0]).days / 365.25
    total_return = (series.iloc[-1] / series.iloc[0]) - 1
    annualized_return = (1 + total_return) ** (1 / num_years) - 1 if num_years > 0 else total_return
    calmar_ratio = annualized_return / abs(max_drawdown) if abs(max_drawdown) > 0 else np.inf
    return {
        'final_portfolio_value': float(series.iloc[-1]),
        'total_return': float(total_return),
        'annualized_return': float(annualized_return),
        'sharpe_ratio': float(sharpe_ratio),
        'max_drawdown': float(max_drawdown),
        'calmar_ratio': float(calmar_ratio if np.isfinite(calmar_ratio) else 1e9),
    }


def months_between(start, end):
    return (end.year - start.year) * 12 - start.month + end.month


def passes_filter(stats, months):
    if not stats:
        return False
    sharpe = stats.get('sharpe_ratio')
    calmar = stats.get('calmar_ratio')
    dd = stats.get('max_drawdown')
    tr = stats.get('total_return')
    ar = stats.get('annualized_return')
    if sharpe is None or sharpe < MIN_SHARPE:
        return False
    if calmar is None or calmar < MIN_CALMAR:
        return False
    if dd is None or dd < MAX_DRAWDOWN:
        return False
    if tr is None or tr < MIN_TOTAL_RETURN:
        return False
    if ar is None or ar < MIN_ANNUALIZED_RETURN:
        return False
    if months < MIN_MONTHS:
        return False
    return True


def load_copy_series(cik):
    path = os.path.join(BACKTESTS_DIR, f'{cik}_backtest_values.csv')
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=[0])
    except Exception as e:
        print(f'Failed reading {path}: {e}')
        return None
    if df.empty or PORTFOLIO_VALUE_COL not in df.columns:
        return None
    s = df[PORTFOLIO_VALUE_COL].copy()
    if s.index.tz is None:
        s.index = s.index.tz_localize('UTC')
    else:
        s.index = s.index.tz_convert('UTC')
    s = s[~s.index.duplicated(keep='last')].sort_index().dropna()
    s = s[s > 0]
    return s if len(s) > 1 else None


def select_funds(copy_series, lifetime_stats, w_start):
    '''Point-in-time fund selection as of w_start.

    Returns a list of (cik, sharpe_ratio) tuples for every fund that passes the
    full filter (MIN_SHARPE/MIN_CALMAR/MAX_DRAWDOWN/MIN_TOTAL_RETURN/
    MIN_ANNUALIZED_RETURN/MIN_MONTHS) using only the copied series data
    available up to and including w_start. No look-ahead.
    '''
    selected = []
    for cik, s in copy_series.items():
        s_pit = s[s.index <= w_start]
        if len(s_pit) < 2:
            continue
        months = months_between(s_pit.index[0], w_start)
        if POINT_IN_TIME_STATS:
            stats = compute_stats(s_pit)
        else:
            lt = lifetime_stats.get(cik, {})
            stats = {
                'sharpe_ratio': lt.get(f'sharpe_ratio_{FILTER_METRIC}'),
                'calmar_ratio': lt.get(f'calmar_ratio_{FILTER_METRIC}'),
                'max_drawdown': lt.get(f'max_drawdown_{FILTER_METRIC}'),
                'total_return': lt.get(f'total_return_{FILTER_METRIC}'),
                'annualized_return': lt.get(f'annualized_return_{FILTER_METRIC}'),
            } if lt else None
        if stats and stats.get('sharpe_ratio') and stats['sharpe_ratio'] > 0 and passes_filter(stats, months):
            selected.append((cik, stats['sharpe_ratio']))
    return selected


def main(quiet=False, status=None):
    # status: optional real-console printer passed by runner_do_backtests so
    # heartbeats stay visible even though this build runs inside that script's
    # quiet stdout/stderr redirect. Falls back to plain print() standalone.
    if status is None:
        def status(msg):
            print(msg, flush=True)

    with open(TOP_FUNDS_PATH, 'r') as f:
        top_funds = json.load(f)

    copy_series = {}
    fund_names = {}
    lifetime_stats = {}
    rebalance_dates = set()

    print('--- Loading copied backtests and rebalance dates ---')
    fund_items = list(top_funds.items())
    n_funds = len(fund_items)
    load_step = max(1, n_funds // 100)
    status(f'PIT stage 1/2: loading {n_funds} funds...')
    fund_iter = fund_items if quiet else tqdm(fund_items, desc='Loading funds')
    for fund_i, (cik, info) in enumerate(fund_iter, 1):
        if fund_i % load_step == 0 or fund_i == n_funds:
            status(f'  PIT loading funds: {fund_i}/{n_funds} processed')
        s = load_copy_series(cik)
        if s is None:
            continue
        copy_series[cik] = s
        fund_names[cik] = info.get('name', cik)
        lifetime_stats[cik] = info.get('backtest_results') or {}
        try:
            allocations_cp, _, _ = prepare_allocations(cik)
        except Exception as e:
            print(f'prepare_allocations failed for {cik}: {e}')
            allocations_cp = None
        if allocations_cp is not None and not allocations_cp.empty:
            idx = allocations_cp.index
            idx = idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
            for d in idx:
                rebalance_dates.add(pd.Timestamp(d))

    if not copy_series:
        print('No copied backtests found. Run runner_do_backtests.py first.')
        return

    global_index = pd.DatetimeIndex([])
    for s in copy_series.values():
        global_index = global_index.union(s.index)
    global_index = global_index.sort_values()

    # Find the ETF start: the first rebalance window at which at least
    # MIN_QUALIFYING_FUNDS_AT_START funds pass the full point-in-time filter
    # (including the 120-month track-record requirement). Earlier windows are
    # dropped entirely, so the timeline no longer starts back in 2002/2016 with
    # one barely-eligible fund.
    all_windows = sorted(rebalance_dates)
    status(f'PIT: searching for start window (>= {MIN_QUALIFYING_FUNDS_AT_START} qualifying funds)...')
    start = None
    for w in all_windows:
        n_qualify = len(select_funds(copy_series, lifetime_stats, w))
        if n_qualify >= MIN_QUALIFYING_FUNDS_AT_START:
            start = w
            break
    if start is None:
        print(f'No rebalance window has at least {MIN_QUALIFYING_FUNDS_AT_START} qualifying funds.')
        return
    windows = [w for w in all_windows if w >= start]
    status(f'PIT: ETF starts {start.date()} ({MIN_QUALIFYING_FUNDS_AT_START}+ funds qualify)')

    etf_index = global_index[global_index >= start]
    etf_values = pd.Series(index=etf_index, dtype=float)
    aligned = {cik: s.reindex(etf_index, method='ffill') for cik, s in copy_series.items()}

    etf_value = float(INITIAL_INVESTMENT)
    window_records = []

    print('--- Simulating point-in-time ETF ---')
    n_windows = len(windows)
    rebal_step = max(1, n_windows // 100)
    status(f'PIT stage 2/2: simulating {n_windows} rebalance windows...')
    window_iter = windows if quiet else tqdm(windows, desc='Rebalances')
    for k, w_start in enumerate(window_iter):
        # k must stay 0-based: it indexes windows[k + 1] below. Report k + 1
        # for the human-readable heartbeat count only.
        if (k + 1) % rebal_step == 0 or (k + 1) == n_windows:
            status(f'  PIT rebalances: {k + 1}/{n_windows} processed')
        w_end = windows[k + 1] if k + 1 < len(windows) else (etf_index[-1] + pd.Timedelta(days=1))
        interval_dates = etf_index[(etf_index >= w_start) & (etf_index < w_end)]
        if len(interval_dates) == 0:
            continue

        start_value = etf_value
        # Use the same point-in-time selection helper that drives the start-date
        # search, so the filter (incl. the 120-month track record) is applied
        # identically at every window with no duplicated/divergent logic.
        selected = select_funds(copy_series, lifetime_stats, w_start)

        if selected:
            total_sharpe = sum(sh for _, sh in selected)
            weights = {cik: sh / total_sharpe for cik, sh in selected}
            interval_value = pd.Series(0.0, index=interval_dates)
            for cik, w in weights.items():
                base = copy_series[cik][copy_series[cik].index <= w_start].iloc[-1]
                if not base or base <= 0:
                    continue
                units = (start_value * w) / base
                contrib = aligned[cik].reindex(interval_dates).ffill() * units
                interval_value = interval_value.add(contrib.fillna(0.0), fill_value=0.0)
            etf_values.loc[interval_dates] = interval_value.values
            etf_value = float(interval_value.iloc[-1])
        else:
            etf_values.loc[interval_dates] = start_value

        window_records.append({
            'date': w_start.strftime('%Y-%m-%d'),
            'end_date': interval_dates[-1].strftime('%Y-%m-%d'),
            'value_start': round(start_value, 2),
            'value_end': round(etf_value, 2),
            'num_funds': len(selected),
            'selected': [
                {
                    'cik': cik,
                    'name': fund_names.get(cik, cik),
                    'weight': round(sh / sum(s2 for _, s2 in selected), 6),
                    'sharpe': round(sh, 4),
                }
                for cik, sh in sorted(selected, key=lambda x: x[1], reverse=True)
            ],
        })

    etf_values = etf_values.dropna()
    if etf_values.empty:
        print('ETF series is empty after simulation.')
        return

    overall = compute_stats(etf_values)
    print('--- Hedge Fund Investment ETF results ---')
    for key, value in (overall or {}).items():
        print(f'{key}: {value}')

    os.makedirs(os.path.dirname(OUTPUT_VALUES_CSV), exist_ok=True)
    out_df = etf_values.rename('PortfolioValue_etf').to_frame()
    out_df.index.name = 'date'
    out_df.to_csv(OUTPUT_VALUES_CSV)
    print(f'Saved ETF values to {OUTPUT_VALUES_CSV}')

    meta = {
        'config': {
            'min_qualifying_funds_at_start': MIN_QUALIFYING_FUNDS_AT_START,
            'initial_investment': INITIAL_INVESTMENT,
            'filter_metric': FILTER_METRIC,
            'point_in_time_stats': POINT_IN_TIME_STATS,
            'filter': {
                'min_sharpe': MIN_SHARPE,
                'min_calmar': MIN_CALMAR,
                'max_drawdown': MAX_DRAWDOWN,
                'min_total_return': MIN_TOTAL_RETURN,
                'min_annualized_return': MIN_ANNUALIZED_RETURN,
                'min_months': MIN_MONTHS,
            },
        },
        'start_date': start.strftime('%Y-%m-%d'),
        'end_date': etf_values.index[-1].strftime('%Y-%m-%d'),
        'backtest_results': overall,
        'num_rebalances': len(window_records),
        'windows': window_records,
    }
    with open(OUTPUT_META_JSON, 'w') as f:
        json.dump(meta, f, indent=2, default=str)
    print(f'Saved ETF meta to {OUTPUT_META_JSON}')

    if WRITE_HTML:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=etf_values.index, y=etf_values.values, mode='lines', name='Hedge Fund Investment ETF'))
        # Build all rebalance markers as a single shapes list. Calling
        # fig.add_vline() in a loop re-validates the whole (growing) figure on
        # every call, which is O(n^2) and effectively hangs for thousands of
        # rebalance windows. Setting them all at once via update_layout is O(n).
        rebalance_shapes = [
            dict(
                type='line', xref='x', yref='paper',
                x0=d, x1=d, y0=0, y1=1,
                line=dict(width=1, dash='dot', color='rgba(120,120,120,0.35)'),
            )
            for d in (pd.to_datetime(rec['date']) for rec in window_records)
        ]
        fig.update_layout(title='Hedge Fund Investment ETF (point-in-time, Sharpe-weighted)', xaxis_title='Date', yaxis_title='Portfolio Value (USD)', template='plotly_white', shapes=rebalance_shapes)
        fig.write_html(OUTPUT_HTML)
        print(f'Saved ETF chart to {OUTPUT_HTML}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Build the point-in-time Hedge Fund Investment ETF.'
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Suppress live tqdm progress bars; print a status line every '
             'PROGRESS_EVERY items instead.'
    )
    args = parser.parse_args()
    main(quiet=args.quiet)
