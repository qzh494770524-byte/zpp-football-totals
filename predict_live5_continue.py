"""Continue predict_live5.py: same candidate list, resume from index 60, append to the
same output directory until 5 total locked predictions (or candidates run out)."""
from datetime import datetime, timedelta
import json

import analyze_totals as totals
import nowgoal_collect as core
import nowgoal_multi as multi
import backtest_today79 as bt

TARGET = 5
MIN_LEAD = timedelta(minutes=20)
MAX_LEAD = timedelta(hours=24)
OUT = core.HERE / 'analysis' / 'live_predict_20260910_155445'
RESUME_FROM = 60

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

attempts = totals.read_json(OUT / 'attempts.json')
locked_out = totals.read_json(OUT / 'locked_predictions.json')
print(json.dumps({'candidates_total': len(candidates), 'already_scanned': len(attempts),
                   'already_locked': len(locked_out)}, ensure_ascii=False), flush=True)

for i, m in enumerate(candidates[RESUME_FROM:], RESUME_FROM + 1):
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
        locked_out.append({'id': entry['id'], 'league': entry['league'], 'home': entry['home'], 'away': entry['away'],
                            'kickoff': entry['kickoff'], 'side': entry['side'], 'line': entry['line'], 'books': entry['books'],
                            'indicator': entry['indicator'], 'anchor_company': entry['anchor_company'],
                            'over_water': entry['over_water'], 'under_water': entry['under_water'],
                            'record_time': entry['record_time'], 'locked_at': core.stamp()})
    if len(locked_out) >= TARGET or core.SOURCE_LIMITED:
        break

(OUT / 'attempts.json').write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'locked_predictions.json').write_text(json.dumps(locked_out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'locked_count': len(locked_out), 'scanned': len(attempts), 'source_limited': core.SOURCE_LIMITED},
                  ensure_ascii=False), flush=True)
