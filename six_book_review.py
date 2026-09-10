"""Descriptive, offline six-book O/U consensus audit; no outcome-based tuning."""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
import statistics
import analyze_totals as totals

BOOKS = [8, 3, 31, 50, 17, 24]
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis' / ('six_book_review_' + datetime.now().strftime('%Y%m%d_%H%M%S'))


def classify(m):
    cutoff = datetime.fromisoformat(m['kickoff']).timestamp()
    companies = {c['cid']: c for c in m.get('companies', [])}
    quotes = []
    for cid in BOOKS:
        p = ROOT / 'evidence' / f"history_{m['id']}_{cid}.json"
        if not p.exists():
            return None
        try:
            raw = p.read_bytes()
            data = json.loads(raw)
            rows = sorted([r for r in data.get('Data', {}).get('ou', [])
                           if r.get('type') in (1, 2) and not r.get('close')
                           and 0 < r.get('mt', 0) < cutoff and totals.quote(r.get('odds'))],
                          key=lambda r: r['mt'])
        except (ValueError, OSError, AttributeError, TypeError):
            return None
        if not rows:
            return None
        last = rows[-1]
        closing = totals.quote(last['odds'])
        start = [r for r in rows if r['mt'] <= cutoff - 1800]
        window = ([start[-1]] if start else []) + [r for r in rows if r['mt'] > cutoff - 1800]
        stable = bool(start) and all(totals.quote(r['odds'])['line'] == closing['line']
                                    and totals.quote(r['odds'])['over'] > totals.quote(r['odds'])['under']
                                    for r in window)
        c = companies.get(cid, {})
        opening = totals.quote(c.get('ou', {}).get('f'))
        drift = bool(opening and opening['line'] == closing['line']
                     and (1 + closing['over']) / (2 + closing['over'] + closing['under'])
                     > (1 + opening['over']) / (2 + opening['over'] + opening['under']) + 1e-9)
        quotes.append(dict(cid=cid, company=c.get('cn', str(cid)), opening=opening,
                           closing=closing, record_time=last['mt'], age_minutes=(cutoff-last['mt'])/60,
                           stable_under_30m=stable, drift_under=drift,
                           sha256=hashlib.sha256(raw).hexdigest(), source=str(p)))
    same_line = len({q['closing']['line'] for q in quotes}) == 1
    under = same_line and all(q['closing']['over'] > q['closing']['under'] for q in quotes)
    over = same_line and all(q['closing']['over'] < q['closing']['under'] for q in quotes)
    return dict(id=m['id'], home=m['home'], away=m['away'], league=m['league'], kickoff=m['kickoff'],
                quotes=quotes, same_line=same_line, under_consensus=under, over_consensus=over,
                fresh_30m=all(q['age_minutes'] <= 30 for q in quotes),
                under_stable_30m=under and all(q['stable_under_30m'] for q in quotes),
                under_drift=under and all(q['drift_under'] for q in quotes))


def metrics(rows):
    output = {'n': len(rows)}
    for side in ['over', 'under']:
        settled = [totals.settle(r['total'], r['quotes'][0]['closing']['line'],
                                r['quotes'][0]['closing'][side], side) for r in rows]
        profits = [s['profit'] for s in settled]
        counts = Counter(s['grade'] for s in settled)
        n = sum(s['grade'] != 0 for s in settled)
        wins = sum(s['grade'] > 0 for s in settled)
        output[side] = dict(grades=dict(counts), positive=wins, nonpush=n,
                            positive_rate=wins/n if n else None, wilson95=totals.wilson(wins, n),
                            net=sum(profits), roi=statistics.mean(profits) if profits else None,
                            bootstrap95=totals.bootstrap(profits))
    return output


def main():
    OUT.mkdir(parents=True)
    rule = dict(created_at=datetime.now().astimezone().isoformat(), books=BOOKS,
                type='Exploratory retrospective analysis prompted by a known losing example; not a holdout test.',
                selection='All six fixed books have valid type 1/2 OU records strictly before scheduled kickoff; same final line.',
                direction='All six have lower under HK water than over HK water.',
                strict='Additionally all six have last records within 30m and every recorded state from T-30m to kickoff stays on final line and under low water; requires state at T-30m.',
                drift='Additionally each opening line equals closing line and normalized under price indicator increases.',
                settlement='Bet365 last verified pregame quote; one unit per game, quarter lines split stakes.',
                limitations=['Cached history may omit changes/closed intervals; stability only describes available records.',
                             'Coverage is incomplete and bookmaker quotes are not independent votes.',
                             'Scheduled kickoff is used, actual delayed kickoff not verified.',
                             'Intervals are nominal match-level intervals, not adjusted for correlation or exploratory subgroup selection.'])
    (OUT/'rule.json').write_text(json.dumps(rule, ensure_ascii=False, indent=2), encoding='utf-8')
    matches = {}
    for fn in ['history_collection_2026-09-02_2026-09-08.json', 'multi_collection_2026-09-09.json']:
        for m in totals.read_json(ROOT/fn):
            matches[m['id']] = m
    eligible = [m for m in matches.values() if m.get('state') == -1
                and all(isinstance(m.get(k), int) and m[k] >= 0 for k in ['home_score', 'away_score'])
                and not totals.exclusion(m)]
    signals = [v for m in eligible if (v := classify(m)) is not None]
    (OUT/'signals.json').write_text(json.dumps(signals, ensure_ascii=False), encoding='utf-8')
    for r in signals:
        m = matches[r['id']]
        r.update(total=m['home_score']+m['away_score'], score=f"{m['home_score']}-{m['away_score']}")
    groups = {
        'all_six_same_line': [r for r in signals if r['same_line']],
        'under_consensus': [r for r in signals if r['under_consensus']],
        'under_consensus_fresh30': [r for r in signals if r['under_consensus'] and r['fresh_30m']],
        'under_consensus_drift': [r for r in signals if r['under_drift']],
        'under_stable30_fresh30': [r for r in signals if r['under_stable_30m'] and r['fresh_30m']],
        'over_consensus': [r for r in signals if r['over_consensus']],
    }
    summary = dict(output=str(OUT), eligible_finished=len(eligible), six_book_history=len(signals),
                   groups={k:metrics(v) for k,v in groups.items()},
                   date_under={day:metrics([r for r in groups['under_consensus'] if r['kickoff'][:10]==day])
                               for day in sorted({r['kickoff'][:10] for r in groups['under_consensus']})},
                   target=next((r for r in signals if r['id']==3000440), None))
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    with (OUT/'six_book_results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['id','kickoff','league','home','away','score','line','under_consensus','fresh_30m','under_drift','under_stable_30m','over_profit','under_profit']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in signals:
            if not r['same_line']:continue
            q=r['quotes'][0]['closing']
            row={k:r[k] for k in fields if k in r}
            row.update(line=q['line'],over_profit=totals.settle(r['total'],q['line'],q['over'],'over')['profit'],
                       under_profit=totals.settle(r['total'],q['line'],q['under'],'under')['profit'])
            writer.writerow(row)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
