import json
import sys

sys.path.insert(0, r"C:\Users\Administrator\Desktop\zpp")
import importlib.util
spec = importlib.util.spec_from_file_location("history", r"C:\Users\Administrator\Desktop\zpp\nowgoal_history.py")
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)

import analyze_totals as totals
import nowgoal_collect as core

OUT = core.HERE / 'analysis' / 'live_predict_20260910_155445'
locked = totals.read_json(OUT / 'locked_predictions.json')

fresh = {r['id']: r for r in history.fetch_day('2026-09-10', refresh=False)}

results = []
for p in locked:
    m = fresh.get(p['id'])
    r = dict(p)
    if not m or m['state'] != -1 or m['home_score'] is None:
        r['status'] = '尚未完场'
        results.append(r)
        continue
    total = m['home_score'] + m['away_score']
    outcome = totals.settle(total, p['line'], p[p['side'] + '_water'], p['side'])
    r.update(final_score=f"{m['home_score']}-{m['away_score']}", total=total,
              result=outcome['result'], profit=outcome['profit'], status='已结算')
    results.append(r)

for r in results:
    print(f"{r['home']} vs {r['away']}: 预测{r['side']} {r['line']} | 终场{r.get('final_score')} "
          f"总进球{r.get('total')} | {r.get('result')} 净{r.get('profit')}")

settled = [r for r in results if r['status'] == '已结算']
wins = sum(1 for r in settled if r['result'] in ('全赢', '半赢'))
losses = sum(1 for r in settled if r['result'] in ('全输', '半输'))
net = sum(r['profit'] for r in settled)
print(f"\n结算{len(settled)}/{len(results)}场: 正收益{wins}场 负收益{losses}场 净单位{net:+.2f}")

(OUT / 'grading_snapshot.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
