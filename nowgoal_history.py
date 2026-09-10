"""Backfill finished fixtures for a fixed historical range and maintain today's scores."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import time

import nowgoal_multi as multi
import nowgoal_collect as core


def dates(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError('Start date must precede end date')
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def save(path, value):
    temp = path.with_suffix('.tmp.json')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def read(path, fallback):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else fallback


def merge_fixtures(existing, fixtures, day, finished_only):
    if any(not m['kickoff'].startswith(day + 'T') for m in fixtures):
        raise ValueError('Fixture date mismatch: ' + day)
    added = 0
    for fresh in fixtures:
        if finished_only and (fresh['state'] != -1 or fresh['home_score'] is None or fresh['away_score'] is None):
            existing.pop(fresh['id'], None)
            continue
        mid = fresh['id']
        if mid not in existing:
            added += 1
        saved = existing.setdefault(mid, dict(fresh, collected_at=core.stamp(), companies=[], comparison_complete=False))
        if saved['state'] != fresh['state']:
            saved['comparison_refresh_needed'] = True
            saved['history_refresh_needed'] = [str(c['cid']) for c in saved.get('companies', []) if multi.eligible(c)]
        saved.update(fresh)
        saved['scores_at'] = core.stamp()
        saved.setdefault('comparison_at', saved['collected_at'])
    return added


def fetch_day(day, refresh):
    return core.parse_fixtures(core.get_json(
        f'{core.BASE}/ajax/SoccerAjax?type=6&date={day}&order=time&timezone=8', f'fixtures_{day}.json', refresh=refresh))


def compact_history(match):
    for cid, history in match.get('multi_history', {}).items():
        match['multi_history'][cid] = {'ah': core.prematch({'kickoff': match['kickoff'], 'history': history})}


def export_all(archive, current, args, errors):
    archive_path = core.HERE / f'history_collection_{args.start}_{args.end}.json'
    current_path = core.HERE / f'multi_collection_{args.current_date}.json'
    for match in list(archive.values()) + list(current.values()):
        compact_history(match)
    save(archive_path, list(archive.values()))
    save(current_path, list(current.values()))
    combined = dict(archive)
    combined.update(current)
    daily = Counter(m['kickoff'][:10] for m in archive.values())
    source = '; '.join(errors) if errors else '赛事名单及比分已整理，未获取的多庄盘口与历史继续补采'
    command = f'python nowgoal_history.py --start {args.start} --end {args.end} --current-date {args.current_date} --watch --interval {args.interval}'
    multi.export(list(current.values()), args.current_date, source, update_command=command)
    label = args.start + '_至_' + args.current_date
    summary = multi.export(list(combined.values()), label, source,
                           f'北京时间{args.start}至{args.end}仅纳入已完场比赛；另保留{args.current_date}全部已有赛事。按比赛ID去重。', update_command=command)
    historical_summary = {
        'historical_start': args.start, 'historical_end': args.end,
        'historical_finished_matches': len(archive), 'historical_counts_by_day': dict(sorted(daily.items())),
        'historical_fixture_days_loaded': sum(day in daily for day in dates(args.start, args.end)),
        'current_date': args.current_date, 'current_matches': len(current),
        'updated_at': core.stamp(), **summary}
    save(core.HERE / 'history_summary.json', historical_summary)
    print(json.dumps(historical_summary, ensure_ascii=True), flush=True)
    return historical_summary


def run(args):
    started = time.monotonic()
    core.SOURCE_LIMITED = False
    core.OFFLINE = args.offline
    archive_path = core.HERE / f'history_collection_{args.start}_{args.end}.json'
    current_path = core.HERE / f'multi_collection_{args.current_date}.json'
    archive = {m['id']: m for m in read(archive_path, [])}
    current = {m['id']: m for m in read(current_path, [])}
    errors = []
    # Current-day scores retain the existing 30-minute priority.
    try:
        merge_fixtures(current, fetch_day(args.current_date, not args.offline), args.current_date, False)
    except Exception as error:
        errors.append('今日比分更新待重试：' + str(error))
    for day in dates(args.start, args.end):
        try:
            fixtures = fetch_day(day, args.refresh_fixtures and not args.offline)
            merge_fixtures(archive, fixtures, day, True)
        except Exception as error:
            errors.append(day + '名单待补采：' + str(error))
    for match in list(archive.values()) + list(current.values()):
        multi.import_cached([match])
        compact_history(match)
    summary = export_all(archive, current, args, errors)
    if args.offline or core.SOURCE_LIMITED or args.budget_seconds <= 0:
        return summary
    deadline = started + min(args.budget_seconds, max(0, args.interval - 120))
    # Reserve part of each cycle for verified histories while expanding overall coverage.
    comparison_deadline = started + (deadline - started) * 0.7
    combined = dict(archive); combined.update(current)
    ordered = sorted(combined.values(), key=lambda m: (m['kickoff'], m['id']))
    count = 0
    try:
        for match in ordered:
            if time.monotonic() >= comparison_deadline:
                break
            if match.get('comparison_complete') and not match.get('comparison_refresh_needed'):
                continue
            mid = match['id']
            try:
                response = core.get_json(core.odds_url(mid, match['state']), f'comp_{mid}.json', refresh=bool(match.get('comparison_refresh_needed')))
                match['companies'] = response['Data']['mixodds']
                match['comparison_complete'] = True
                match['comparison_refresh_needed'] = False
                match['comparison_at'] = core.stamp()
                match.pop('comparison_error', None)
                count += 1
            except Exception as error:
                match['comparison_error'] = str(error)
                if core.SOURCE_LIMITED:
                    raise
            if count and count % 50 == 0:
                save(archive_path, list(archive.values()))
                save(current_path, list(current.values()))
                print(json.dumps({'bookmaker_comparisons_added': count}), flush=True)
        # Verify each company's own records, refreshing any records invalidated by kickoff.
        for match in ordered:
            if time.monotonic() >= deadline:
                break
            if match['state'] not in multi.STARTED:
                continue
            for company in match.get('companies', []):
                if time.monotonic() >= deadline:
                    break
                cid = str(company['cid'])
                needs_refresh = cid in match.get('history_refresh_needed', [])
                histories = match.setdefault('multi_history', {})
                if not multi.eligible(company) or (cid in histories and not needs_refresh):
                    continue
                try:
                    response = core.get_json(core.history_url(match['id'], cid), f"history_{match['id']}_{cid}.json", refresh=needs_refresh)
                    histories[cid] = {'ah': core.prematch({'kickoff': match['kickoff'], 'history': response['Data']})}
                    match.setdefault('multi_errors', {}).pop(cid, None)
                    if needs_refresh:
                        match['history_refresh_needed'].remove(cid)
                except Exception as error:
                    match.setdefault('multi_errors', {})[cid] = str(error)
                    if core.SOURCE_LIMITED:
                        raise
    except Exception as error:
        errors.append('赔率补采待重试：' + str(error))
    return export_all(archive, current, args, errors)


def watch(args):
    status_path = core.HERE / 'multi_automation_status.json'
    while True:
        started = time.monotonic()
        status = {'state': 'running', 'interval_seconds': args.interval, 'historical_start': args.start,
                  'historical_end': args.end, 'date': args.current_date, 'last_started': core.stamp(),
                  'next_run': (datetime.now(core.TZ) + timedelta(seconds=args.interval)).isoformat()}
        save(status_path, status)
        try:
            result = run(args)
            done = (result['pending_matches'] == 0 and result['comparison_pending_matches'] == 0
                    and result['history_pending_rows'] == 0 and result['historical_fixture_days_loaded'] == len(dates(args.start, args.end)))
            if not args.watch or done:
                status.update(state='complete' if done else 'one_run_finished', last_finished=core.stamp())
                save(status_path, status)
                break
        except Exception as error:
            print(json.dumps({'cycle_error': str(error)}, ensure_ascii=True), flush=True)
            if not args.watch:
                raise
        delay = multi.next_cycle_delay(time.monotonic() - started, args.interval)
        status.update(state='waiting', last_finished=core.stamp(), next_run=(datetime.now(core.TZ) + timedelta(seconds=delay)).isoformat())
        save(status_path, status)
        print(json.dumps(status), flush=True)
        time.sleep(delay)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--current-date', default=datetime.now(core.TZ).date().isoformat())
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--refresh-fixtures', action='store_true')
    parser.add_argument('--interval', type=int, default=1800)
    parser.add_argument('--budget-seconds', type=int, default=1200)
    watch(parser.parse_args())
