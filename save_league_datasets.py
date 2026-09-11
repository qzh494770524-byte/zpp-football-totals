"""Save clean, properly-named copies of the league match data collected so far during the
Dixon-Coles work -- the raw fetches currently only exist as hash-named cache files in
evidence/, not as an identifiable, reusable dataset."""
import json
from datetime import datetime, timezone

import dixon_coles as dc

OUT_DIR = dc.__file__.rsplit('\\', 1)[0] + r'\league_data'
import os
os.makedirs(OUT_DIR, exist_ok=True)

TARGETS = [
    (15, 'K League 1', None),
    (25, 'Japan J1 League', None),
    (36, 'English Premier League', ['2025-2026', '2026-2027']),
]

manifest = {}
for lid, name, seasons in TARGETS:
    if seasons:
        matches, teams = dc.fetch_league_matches_multi_season(lid, seasons)
        season_label = '+'.join(seasons)
    else:
        matches, teams = dc.fetch_league_matches(lid)
        season_label = dc.SEASON_FORMAT.get(lid, '2026')

    rows = [dict(id=m['id'], date=m['date'].isoformat(), home_id=m['home_id'], away_id=m['away_id'],
                 home=m['home'], away=m['away'], hs=m['hs'], as_=m['as_']) for m in matches]
    safe_name = name.replace(' ', '_')
    path = f"{OUT_DIR}\\{safe_name}_{lid}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dict(league_id=lid, league_name=name, season=season_label,
                        fetched_at=datetime.now(timezone.utc).isoformat(),
                        n_teams=len(teams), n_matches=len(rows),
                        teams={str(k): v for k, v in teams.items()}, matches=rows),
                  f, ensure_ascii=False, indent=2)
    manifest[lid] = dict(name=name, season=season_label, n_matches=len(rows), n_teams=len(teams), file=path)
    print(f"{name}: {len(rows)}场  {len(teams)}队  -> {path}")

with open(f"{OUT_DIR}\\manifest.json", 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
