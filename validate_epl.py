"""Out-of-sample validation for EPL using combined 2025-26 (full season) + 2026-27
(season so far) data -- same walk-forward discipline as K League/J1: fit only on matches
before the split date, test on matches strictly after."""
import statistics

import dixon_coles as dc

LINE = 2.5

matches, teams = dc.fetch_league_matches_multi_season(36, ['2025-2026', '2026-2027'])
n = len(matches)
split = int(n * 0.75)
train_matches = matches[:split]
test_matches = matches[split:]
cutoff = train_matches[-1]['date']
print(f"总场次{n}  train={len(train_matches)}(截至{cutoff.date()})  test={len(test_matches)}"
      f"(至{test_matches[-1]['date'].date()})")

fit = dc.fit_dixon_coles(train_matches, as_of=cutoff, verbose=True)

rows = []
for m in test_matches:
    pred = dc.match_ou_prob(fit, m['home_id'], m['away_id'], LINE)
    if pred is None:
        continue
    total = m['hs'] + m['as_']
    actual = 'over' if total > LINE else 'under'
    side = 'over' if pred['p_over'] > pred['p_under'] else 'under'
    rows.append(dict(match=f"{m['home']} vs {m['away']}", date=m['date'].date(),
                      p_over=pred['p_over'], side=side, actual=actual, total=total, correct=side == actual))

hit = sum(r['correct'] for r in rows)
always_over = sum(1 for r in rows if r['actual'] == 'over')
always_under = len(rows) - always_over
n_over_pred = sum(1 for r in rows if r['side'] == 'over')
brier = statistics.mean((r['p_over'] - (1 if r['actual'] == 'over' else 0)) ** 2 for r in rows)

print(f"\n可评估场次: {len(rows)}  模型命中: {hit} ({hit/len(rows)*100:.1f}%)")
print(f"对照基线: 无脑选大={always_over}({always_over/len(rows)*100:.1f}%)  "
      f"无脑选小={always_under}({always_under/len(rows)*100:.1f}%)")
print(f"模型预测分布: 判大{n_over_pred}场  判小{len(rows)-n_over_pred}场")
print(f"Brier score: {brier:.4f}  (0.25=纯瞎猜)")

# Wilson CI for the hit rate
z = 1.96
p = hit / len(rows)
denom = 1 + z**2/len(rows)
center = (p + z*z/(2*len(rows))) / denom
margin = z * ((p*(1-p)/len(rows) + z*z/(4*len(rows)**2)) ** 0.5) / denom
print(f"命中率95%置信区间: {center-margin:.1%} ~ {center+margin:.1%}")
