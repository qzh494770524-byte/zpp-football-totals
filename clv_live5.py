"""Compute Closing Line Value (CLV) for the 5 locked live predictions: compare the
snapshot indicator we locked in (record_time, hours before kickoff) against the closing
indicator (latest available pre-kickoff quote, fetched after kickoff has passed so the
watcher/history endpoint has the final pregame record). CLV is a lower-variance read than
win/loss on a 5-match sample -- see football_modeling_notes.md 2026-09-10 CLV section.
Run this once kickoff has passed for all 5 (tonight after ~22:00 Beijing), before or
alongside grade_live5.py.
"""
from datetime import datetime
import json

import analyze_totals as totals
import nowgoal_collect as core
import nowgoal_multi as multi
import backtest_today79 as bt

OUT = core.HERE / 'analysis' / 'live_predict_20260910_155445'
locked = totals.read_json(OUT / 'locked_predictions.json')

core.OFFLINE = False
core.SOURCE_LIMITED = False

rows = []
for p in locked:
    mid = p['id']
    quotes = []
    try:
        comp = core.get_json(core.odds_url(mid, -1), f'comp_{mid}.json', refresh=True)
        offered = {c['cid']: c for c in comp['Data']['mixodds']}
        for cid in bt.BOOKS:
            company = offered.get(cid, {})
            if not (totals.quote(company.get('ou', {}).get('f')) or totals.quote(company.get('ou', {}).get('l'))):
                continue
            history = core.get_json(core.history_url(mid, cid), f'history_{mid}_{cid}.json', refresh=True)
            cutoff = datetime.fromisoformat(p['kickoff']).timestamp()
            records = [r for r in history.get('Data', {}).get('ou', []) if r.get('type') in (1, 2)
                       and not r.get('close') and totals.quote(r.get('odds')) and r.get('mt', float('inf')) < cutoff]
            if records:
                record = max(records, key=lambda r: r['mt'])
                quotes.append({'cid': cid, 'company': multi.name(cid), **totals.quote(record['odds']),
                                'record_time': datetime.fromtimestamp(record['mt'], core.TZ).isoformat()})
    except Exception as error:
        rows.append(dict(p, clv_error=str(error)))
        continue

    group = [q for q in quotes if q['line'] == p['line']]
    if len(group) < 2:
        rows.append(dict(p, clv_error=f'仅{len(group)}家同盘口收盘记录,不足以比较'))
        continue
    closing_indicator = __import__('statistics').median(
        (1/(1+q['over']))/(1/(1+q['over'])+1/(1+q['under'])) for q in group)
    moved_toward = (closing_indicator > p['indicator']) if p['side'] == 'over' else (closing_indicator < p['indicator'])
    rows.append(dict(p, closing_indicator=closing_indicator, closing_books=len(group),
                      clv_positive=moved_toward, indicator_shift=closing_indicator - p['indicator']))

for r in rows:
    print(json.dumps(r, ensure_ascii=False))

scored = [r for r in rows if 'closing_indicator' in r]
if scored:
    pos = sum(1 for r in scored if r['clv_positive'])
    print(json.dumps({'clv_scored': len(scored), 'clv_positive_count': pos,
                       'note': 'clv_positive=收盘价朝我们选的方向进一步移动,不是最终赛果对错'}, ensure_ascii=False))
(OUT / 'clv_snapshot.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
