"""Grade the 5 locked live predictions in analysis/live_predict_20260910_155445/.
Run after the matches should have finished (e.g. the next day)."""
import json

import analyze_totals as totals
import nowgoal_collect as core

OUT = core.HERE / 'analysis' / 'live_predict_20260910_155445'
locked = totals.read_json(OUT / 'locked_predictions.json')
ids = {p['id'] for p in locked}

found = {}
for path in list(core.HERE.glob('*collection*.json')) + list(core.HERE.glob('rolling_collection.json')):
    try:
        for m in totals.read_json(path):
            if m.get('id') in ids and m.get('state') == -1 and m.get('home_score') is not None:
                found[m['id']] = m
    except Exception:
        continue

results = []
for p in locked:
    m = found.get(p['id'])
    r = dict(p)
    if not m:
        r['status'] = '尚未完场或未找到赛果'
        results.append(r)
        continue
    total = m['home_score'] + m['away_score']
    outcome = totals.settle(total, p['line'], p[p['side'] + '_water'], p['side'])
    r.update(final_score=f"{m['home_score']}-{m['away_score']}", total=total,
              result=outcome['result'], profit=outcome['profit'], status='已结算')
    results.append(r)

for r in results:
    print(json.dumps(r, ensure_ascii=False))

settled = [r for r in results if r['status'] == '已结算']
if settled:
    wins = sum(1 for r in settled if r['result'] in ('全赢', '半赢'))
    print(json.dumps({'settled': len(settled), 'of': len(results), 'wins_incl_half': wins,
                       'net_units': sum(r['profit'] for r in settled)}, ensure_ascii=False))
(OUT / 'grading_snapshot.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
