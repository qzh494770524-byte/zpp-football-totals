"""Lock in fixed-rule O/U predictions for not-yet-started fixtures, to grade after kickoff.

Reuses the exact fixed rule already specified and backtested in backtest_today79.py
(company priority [Bet365, Crown, Sbobet, 1xBet], >=3 same-line books, median normalized
water indicator). No parameter changes here -- this is a forward application of that same
rule to live not-started matches, not a new rule.
"""
from datetime import datetime, timedelta
import json
import sys

import analyze_totals as totals
import nowgoal_collect as core
import nowgoal_multi as multi
import backtest_today79 as bt

TARGET = 5
MAX_TRIES = 60
MIN_LEAD = timedelta(minutes=20)
MAX_LEAD = timedelta(hours=24)

started = datetime.now(core.TZ)
OUT = core.HERE / 'analysis' / ('live_predict_' + started.strftime('%Y%m%d_%H%M%S'))
OUT.mkdir(parents=True, exist_ok=True)

core.OFFLINE = False
core.SOURCE_LIMITED = False

matches = totals.read_json(core.HERE / 'multi_collection_2026-09-10.json')
now = datetime.now(core.TZ)
candidates = []
for m in matches:
    if m.get('state') != 0 or not m.get('kickoff'):
        continue
    kickoff = datetime.fromisoformat(m['kickoff'])
    if now + MIN_LEAD < kickoff < now + MAX_LEAD:
        candidates.append(m)
candidates.sort(key=lambda m: m['kickoff'])
print(json.dumps({'total_in_file': len(matches), 'not_started_in_window': len(candidates),
                   'window': [str(now + MIN_LEAD), str(now + MAX_LEAD)]}, ensure_ascii=False), flush=True)

locked = []
attempts = []

for i, m in enumerate(candidates[:MAX_TRIES], 1):
    mid = m['id']
    entry = {'id': mid, 'league': m['league'], 'home': m['home'], 'away': m['away'],
              'kickoff': m['kickoff'], 'quotes': [], 'errors': []}
    try:
        comp = core.get_json(core.odds_url(mid, 0), f'comp_{mid}.json', refresh=True)
        offered = {c['cid']: c for c in comp['Data']['mixodds']}
        for cid in bt.BOOKS:
            company = offered.get(cid, {})
            if not (totals.quote(company.get('ou', {}).get('f')) or totals.quote(company.get('ou', {}).get('l'))):
                continue
            try:
                history = core.get_json(core.history_url(mid, cid), f'history_{mid}_{cid}.json', refresh=True)
                cutoff = datetime.fromisoformat(m['kickoff']).timestamp()
                records = [r for r in history.get('Data', {}).get('ou', []) if r.get('type') in (1, 2)
                           and not r.get('close') and totals.quote(r.get('odds')) and r.get('mt', float('inf')) < cutoff]
                if records:
                    record = max(records, key=lambda r: r['mt'])
                    entry['quotes'].append({'cid': cid, 'company': multi.name(cid), **totals.quote(record['odds']),
                                             'record_time': datetime.fromtimestamp(record['mt'], core.TZ).isoformat()})
            except Exception as error:
                entry['errors'].append(f'{multi.name(cid)}: {error}')
                if core.SOURCE_LIMITED:
                    break
    except Exception as error:
        entry['errors'].append(str(error))

    forecast = bt.forecast(entry['quotes'])
    entry.update(forecast)
    attempts.append(entry)
    print(json.dumps({'i': i, 'mid': mid, 'match': f"{m['home']} vs {m['away']}", 'kickoff': m['kickoff'],
                       'side': entry.get('side'), 'reason': entry.get('reason')}, ensure_ascii=False), flush=True)

    if entry.get('side'):
        locked.append(entry)
    if len(locked) >= TARGET or core.SOURCE_LIMITED:
        break

(OUT / 'attempts.json').write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding='utf-8')
locked_out = [{'id': e['id'], 'league': e['league'], 'home': e['home'], 'away': e['away'], 'kickoff': e['kickoff'],
               'side': e['side'], 'line': e['line'], 'books': e['books'], 'indicator': e['indicator'],
               'anchor_company': e['anchor_company'], 'over_water': e['over_water'], 'under_water': e['under_water'],
               'record_time': e['record_time'], 'locked_at': core.stamp()} for e in locked]
(OUT / 'locked_predictions.json').write_text(json.dumps(locked_out, ensure_ascii=False, indent=2), encoding='utf-8')
rule = totals.read_json(core.HERE / 'analysis' / 'backtest_79_20260910' / 'fixed_rule.json')
(OUT / 'rule.json').write_text(json.dumps(rule, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'locked_count': len(locked_out), 'scanned': len(attempts), 'source_limited': core.SOURCE_LIMITED,
                   'out_dir': str(OUT)}, ensure_ascii=False), flush=True)
