"""Out-of-sample validation for the Dixon-Coles fit: split each league's matches by date
(first ~75% = train, last ~25% = test, never fit on test matches), predict Over/Under 2.5
for each test match using only the train-period fit, compare against actual outcomes.
This mirrors the date-split discipline used earlier this session for the odds-drift model."""
import math
import statistics

import dixon_coles as dc

LINE = 2.5

for lid, name in dc.LEAGUES.items():
    print(f"\n=== {name} ===")
    matches, teams = dc.fetch_league_matches(lid)
    matches.sort(key=lambda m: m['date'])
    n = len(matches)
    split = int(n * 0.75)
    train_matches = matches[:split]
    test_matches = matches[split:]
    cutoff = train_matches[-1]['date']
    print(f"总场次{n}  train={len(train_matches)}(截至{cutoff.date()})  test={len(test_matches)}")

    fit = dc.fit_dixon_coles(train_matches, as_of=cutoff)
    if not fit:
        print("训练集太小,跳过")
        continue

    rows = []
    for m in test_matches:
        pred = dc.match_ou_prob(fit, m['home_id'], m['away_id'], LINE)
        if pred is None:
            continue  # team not seen in training period (promoted/new)
        total = m['hs'] + m['as_']
        actual = 'over' if total > LINE else 'under'
        side = 'over' if pred['p_over'] > pred['p_under'] else 'under'
        rows.append(dict(match=f"{m['home']} vs {m['away']}", date=m['date'].date(),
                          p_over=pred['p_over'], exp_total=pred['exp_total'],
                          side=side, actual=actual, total=total, correct=side == actual))

    if not rows:
        print("没有可评估的测试场次(可能全是新晋升球队)")
        continue

    hit = sum(r['correct'] for r in rows)
    over_rate = sum(1 for r in rows if r['actual']=='over')/len(rows)
    always_over_hit = sum(1 for r in rows if r['actual']=='over')
    always_under_hit = sum(1 for r in rows if r['actual']=='under')
    print(f"可评估场次: {len(rows)}  模型命中: {hit} ({hit/len(rows)*100:.1f}%)")
    print(f"  对照基线: 无脑选大={always_over_hit}({always_over_hit/len(rows)*100:.1f}%)  "
          f"无脑选小={always_under_hit}({always_under_hit/len(rows)*100:.1f}%)")
    n_over_pred = sum(1 for r in rows if r['side']=='over')
    print(f"  模型预测分布: 判大{n_over_pred}场  判小{len(rows)-n_over_pred}场"
          f"(该期间实际大率{over_rate*100:.1f}%)")

    # Brier score for calibration (lower is better; 0.25 = always guessing 50%)
    brier = statistics.mean((r['p_over'] - (1 if r['actual']=='over' else 0))**2 for r in rows)
    print(f"  Brier score (p_over vs 真实结果): {brier:.4f}  (0.25=纯瞎猜, 越低越好)")

    for r in rows:
        print(f"  {r['date']} {r['match']:35s} 预测P(大)={r['p_over']:.2f} 预期总进球={r['exp_total']:.2f} "
              f"预测={r['side']:5s} 实际={r['actual']:5s}({r['total']}球) {'✓' if r['correct'] else '✗'}")
