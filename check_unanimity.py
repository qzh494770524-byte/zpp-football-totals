"""Check whether unanimous-direction predictions (all contributing books agree) beat
split/majority predictions (median crosses 0.5 but books disagree), using the existing
79-match fixed-rule backtest data. No new scraping needed."""
import json
import statistics

import analyze_totals as totals
import nowgoal_collect as core

OUT = core.HERE / 'analysis' / 'backtest_79_20260910'
results = {r['id']: r for r in totals.read_json(OUT / 'results.json')}
inputs = {m['id']: m for m in totals.read_json(OUT / 'pregame_inputs.json')}

rows = []
for mid, r in results.items():
    if not r.get('settled') or not r.get('side'):
        continue
    m = inputs[mid]
    group = [q for q in m['quotes'] if q['line'] == r['line']]
    inds = [(1/(1+q['over']))/(1/(1+q['over'])+1/(1+q['under'])) for q in group]
    sides = ['over' if i > 0.5 else 'under' if i < 0.5 else 'tie' for i in inds]
    unanimous = len(set(sides)) == 1 and 'tie' not in sides
    rows.append(dict(mid=mid, side=r['side'], result=r['result'], profit=r['profit'],
                      unanimous=unanimous, n_books=len(group), sides=sides,
                      spread=max(inds)-min(inds)))

for label, grp in [('全部21场已结算', rows),
                    ('全票一致 (all books agree)', [x for x in rows if x['unanimous']]),
                    ('非一致 (含分歧)', [x for x in rows if not x['unanimous']])]:
    pos = sum(1 for x in grp if x['result'] in ('全赢', '半赢'))
    neg = sum(1 for x in grp if x['result'] in ('全输', '半输'))
    push = sum(1 for x in grp if x['result'] == '走盘')
    net = sum(x['profit'] for x in grp)
    rate = pos/(pos+neg) if pos+neg else None
    print(f"{label}: n={len(grp)} 正{pos}/负{neg}/走盘{push}  胜率(除走盘)={rate}  净单位={net:+.2f}")

print()
for x in sorted(rows, key=lambda x: x['unanimous']):
    print(f"mid={x['mid']} side={x['side']:5s} result={x['result']:4s} profit={x['profit']:+.2f} "
          f"unanimous={x['unanimous']} n_books={x['n_books']} spread={x['spread']:.4f} sides={x['sides']}")
