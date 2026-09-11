"""Calibration check for v8's confidence_prob (the probability the model assigns to its
own predicted direction), using Brier score and ECE -- not hit-rate, per the Walsh & Joshi
finding that calibration is the metric that actually predicts betting returns. Same 8-day
dataset and same date-based train/test split used for the earlier cross-signal validation.
"""
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\Users\Administrator\Desktop\zpp")
import importlib.util
spec = importlib.util.spec_from_file_location("pipeline", r"C:\Users\Administrator\Desktop\zpp\v8_backtest_pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

import openpyxl

XLSX = r"C:\Users\Administrator\Desktop\zpp\Nowgoal_2026-09-02_至_2026-09-09_多庄水位比分.xlsx"
matches, ah_by_match, ou_by_match, eu_by_match = pipeline.load_workbook_data(XLSX, min_companies=2)

wb = openpyxl.load_workbook(XLSX, data_only=True)
kickoff_by_mid = {}
for r in wb['全部赛事与比分'].iter_rows(min_row=2, values_only=True):
    mid, league, kickoff = r[0], r[1], r[2]
    if mid in matches and kickoff:
        kickoff_by_mid[mid] = str(kickoff)[:10]

rows = []
for mid, m in matches.items():
    if m['status'] != '完场' or m['total_goals'] is None or mid not in kickoff_by_mid:
        continue
    sig = pipeline.compute_odds_drift_signal(mid, ou_by_match.get(mid, []), ah_by_match.get(mid, []),
                                              eu_by_match.get(mid, []))
    if sig is None:
        continue
    line = sig['consensus_line']
    if m['total_goals'] == line:
        continue
    actual = 'over' if m['total_goals'] > line else 'under'
    rows.append(dict(mid=mid, date=kickoff_by_mid[mid], p=sig['confidence_prob'] / 100,
                      direction=sig['direction'], correct=int(sig['direction'] == actual)))

dates = sorted(set(r['date'] for r in rows))
mid_date = dates[len(dates) // 2]
train = [r for r in rows if r['date'] < mid_date]
test = [r for r in rows if r['date'] >= mid_date]
print(f"总场次{len(rows)}  切分点{mid_date}  train={len(train)}  test={len(test)}\n")


def brier(grp):
    return st.mean((r['p'] - r['correct']) ** 2 for r in grp)


def ece(grp, bins=(0.50, 0.53, 0.58, 0.63, 0.68, 0.73, 0.80, 1.01)):
    buckets = defaultdict(list)
    for r in grp:
        for lo, hi in zip(bins, bins[1:]):
            if lo <= r['p'] < hi:
                buckets[(lo, hi)].append(r)
                break
    total = len(grp)
    ece_val = 0.0
    print(f"  {'区间':16s} {'n':>5s} {'模型平均概率':>10s} {'实际命中率':>10s} {'差':>8s}")
    for (lo, hi), grp_b in sorted(buckets.items()):
        if not grp_b:
            continue
        mean_p = st.mean(r['p'] for r in grp_b)
        mean_actual = st.mean(r['correct'] for r in grp_b)
        gap = abs(mean_p - mean_actual)
        ece_val += len(grp_b) / total * gap
        print(f"  [{lo:.2f},{hi:.2f})  {len(grp_b):5d}  {mean_p*100:9.1f}%  {mean_actual*100:9.1f}%  {gap*100:7.1f}pp")
    return ece_val


for label, grp in [('train', train), ('test', test), ('全部', rows)]:
    print(f"=== {label} (n={len(grp)}) ===")
    overall_hit = st.mean(r['correct'] for r in grp)
    print(f"整体命中率: {overall_hit*100:.2f}%")
    print(f"Brier score(模型confidence_prob): {brier(grp):.4f}")
    flat_p = overall_hit  # baseline: always predict the overall historical hit rate
    brier_flat = st.mean((flat_p - r['correct']) ** 2 for r in grp)
    print(f"Brier score(拿整体命中率{overall_hit*100:.1f}%当固定概率的基线): {brier_flat:.4f}")
    e = ece(grp)
    print(f"ECE(期望校准误差): {e*100:.2f}pp\n")
