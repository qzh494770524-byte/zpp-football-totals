import json

ids = [3084136, 3084138, 3084139, 3084135, 3072755]
with open('analysis/live_predict_20260910_155445/attempts.json', encoding='utf-8') as f:
    data = json.load(f)
by_id = {e['id']: e for e in data}
for mid in ids:
    e = by_id[mid]
    print('=' * 80)
    print(mid, e['home'], 'vs', e['away'], '| side=', e.get('side'), '| line=', e.get('line'), '| indicator=', e.get('indicator'))
    for q in e['quotes']:
        ind = (1 / (1 + q['over'])) / (1 / (1 + q['over']) + 1 / (1 + q['under']))
        print(f"  {q['company']:10s} line={q['line']:<5} over={q['over']:<5} under={q['under']:<5} indicator={ind:.4f} record_time={q['record_time']}")
    if e.get('errors'):
        print('  errors:', e['errors'])
