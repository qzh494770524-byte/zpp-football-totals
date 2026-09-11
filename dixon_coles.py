"""Real Dixon-Coles model: joint MLE over the whole league (not per-match near-6-game
averages like the abandoned compute_expected_goals()). Fetches full-season match lists
directly from nowgoal's per-league JSON endpoint (confirmed working for league ids
15=K League 1, 25=Japan J1 League), fits attack/defense/home-advantage/rho with
time-decay weighting, and can compute Over/Under probabilities from the fitted grid.

Reference: Dixon & Coles (1997); see football_modeling_notes.md 2026-09-11 section for the
exact formulas and known real-world caveats (unbalanced leagues can overweight
non-competitive matches; low-tier/thin leagues excluded per user instruction).
"""
from datetime import datetime, timezone, timedelta
import json
import math
import sys

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, r"C:\Users\Administrator\Desktop\zpp")
from fetch_nowgoal import fetch

TZ = timezone(timedelta(hours=8))

LEAGUES = {15: 'K League 1', 25: 'Japan J1 League', 36: 'English Premier League'}

# Asian domestic leagues (K League, J1) run within one calendar year; European leagues
# and UEFA club competitions span two ("YYYY-YYYY"). Confirmed by checking each league's
# own page network requests, not guessed.
SEASON_FORMAT = {36: '2026-2027', 103: '2026-2027'}


def _iter_round_lists(schedule_list):
    """ScheduleList is either {'sub_313': {'R_1': [...], ...}} (leagues with playoff/
    group splits like K League 1) or directly {'R_1': [...], ...} (simple single-table
    leagues like EPL). Handle both shapes."""
    for value in schedule_list.values():
        if isinstance(value, dict):
            yield from value.values()
        elif isinstance(value, list):
            yield value


def fetch_league_matches(league_id, season=None):
    season = season or SEASON_FORMAT.get(league_id, '2026')
    raw = fetch(f'https://football.nowgoal26.com/jsData/matchResult/json/{season}/s{league_id}_en.json')
    data = json.loads(raw)
    teams = {t[0]: t[1] for t in data['TeamInfo']}
    matches = []
    for round_matches in _iter_round_lists(data['ScheduleList']):
        for m in round_matches:
            if len(m) < 8:
                continue
            mid, lid, state, dt_str, home_id, away_id, score, half_score = m[:8]
            if state != -1 or not isinstance(home_id, int) or not isinstance(away_id, int):
                continue
            if not isinstance(score, str) or '-' not in score:
                continue
            try:
                hs, as_ = map(int, score.split('-'))
            except ValueError:
                continue
            if home_id not in teams or away_id not in teams:
                continue
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
            matches.append(dict(id=mid, date=dt, home_id=home_id, away_id=away_id,
                                 home=teams[home_id], away=teams[away_id], hs=hs, as_=as_))
    matches.sort(key=lambda m: m['date'])
    return matches, teams


def fetch_league_matches_multi_season(league_id, seasons):
    """Combine several seasons (older + current) into one match list -- needed early in a
    new season when the current season alone has too few matches; the exponential
    time-decay in fit_dixon_coles() down-weights the older matches appropriately, it does
    not need a hard season cutoff."""
    all_matches, teams = [], {}
    seen_ids = set()
    for season in seasons:
        m, t = fetch_league_matches(league_id, season)
        teams.update(t)
        for row in m:
            if row['id'] not in seen_ids:
                seen_ids.add(row['id'])
                all_matches.append(row)
    all_matches.sort(key=lambda m: m['date'])
    return all_matches, teams


def tau(x, y, lam, mu, rho):
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def fit_dixon_coles(matches, as_of=None, xi=0.0018, verbose=False):
    """xi is a per-day decay rate (Dixon & Coles' 0.0065 was per half-week; converting to
    per-day gives ~0.00186 -- see football_modeling_notes.md caveat that this needs
    re-estimating per league, this is a starting value not a verified constant)."""
    as_of = as_of or matches[-1]['date']
    train = [m for m in matches if m['date'] <= as_of]
    if len(train) < 20:
        return None
    team_ids = sorted({m['home_id'] for m in train} | {m['away_id'] for m in train})
    idx = {t: i for i, t in enumerate(team_ids)}
    n = len(team_ids)

    weights = np.array([math.exp(-xi * (as_of - m['date']).total_seconds() / 86400) for m in train])
    home_idx = np.array([idx[m['home_id']] for m in train])
    away_idx = np.array([idx[m['away_id']] for m in train])
    hs = np.array([m['hs'] for m in train])
    as_arr = np.array([m['as_'] for m in train])

    def unpack(params):
        a = params[:n]
        b = params[n:2 * n]
        gamma, rho = params[2 * n], params[2 * n + 1]
        return a, b, gamma, rho

    def neg_log_lik(params):
        a, b, gamma, rho = unpack(params)
        lam = np.exp(a[home_idx] + b[away_idx] + gamma)
        mu = np.exp(a[away_idx] + b[home_idx])
        ll = 0.0
        rho_c = max(min(rho, 0.99 / max(lam.max(), mu.max())), -0.99)
        for i in range(len(train)):
            t = tau(hs[i], as_arr[i], lam[i], mu[i], rho)
            if t <= 0:
                t = 1e-6
            ll += weights[i] * (math.log(t) + hs[i] * math.log(lam[i]) - lam[i]
                                 - math.lgamma(hs[i] + 1) + as_arr[i] * math.log(mu[i]) - mu[i]
                                 - math.lgamma(as_arr[i] + 1))
        # sum(a)=0 soft constraint via penalty (identifiability)
        ll -= 1000 * (a.sum()) ** 2
        return -ll

    x0 = np.concatenate([np.zeros(n), np.zeros(n), [0.3], [0.0]])
    result = minimize(neg_log_lik, x0, method='L-BFGS-B',
                       bounds=[(-3, 3)] * n + [(-3, 3)] * n + [(-1, 1.5)] + [(-0.3, 0.3)])
    a, b, gamma, rho = unpack(result.x)
    ratings = {team_ids[i]: dict(team=next(m['home'] for m in train if m['home_id'] == team_ids[i]) if any(m['home_id'] == team_ids[i] for m in train) else next(m['away'] for m in train if m['away_id'] == team_ids[i]),
                                  attack=round(float(a[i]), 3), defense=round(float(b[i]), 3))
               for i in range(n)}
    if verbose:
        print(f"fit success={result.success}  n_teams={n}  n_matches={len(train)}  gamma={gamma:.3f}  rho={rho:.3f}")
    return dict(team_ids=team_ids, idx=idx, a=a, b=b, gamma=gamma, rho=rho, ratings=ratings,
                converged=result.success)


def match_ou_prob(fit, home_id, away_id, line, max_goals=10):
    a, b, gamma, rho = fit['a'], fit['b'], fit['gamma'], fit['rho']
    idx = fit['idx']
    if home_id not in idx or away_id not in idx:
        return None
    hi, ai = idx[home_id], idx[away_id]
    lam = math.exp(a[hi] + b[ai] + gamma)
    mu = math.exp(a[ai] + b[hi])
    grid = np.zeros((max_goals + 1, max_goals + 1))
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            px = math.exp(-lam) * lam ** x / math.factorial(x)
            py = math.exp(-mu) * mu ** y / math.factorial(y)
            grid[x, y] = tau(x, y, lam, mu, rho) * px * py
    grid /= grid.sum()
    over = sum(grid[x, y] for x in range(max_goals + 1) for y in range(max_goals + 1) if x + y > line)
    under = sum(grid[x, y] for x in range(max_goals + 1) for y in range(max_goals + 1) if x + y < line)
    return dict(p_over=over, p_under=under, p_push=1 - over - under, lam=lam, mu=mu, exp_total=lam + mu)


if __name__ == '__main__':
    for lid, name in LEAGUES.items():
        print(f"\n=== {name} (id={lid}) ===")
        matches, teams = fetch_league_matches(lid)
        print(f"已完场: {len(matches)}  队伍数: {len(teams)}")
        fit = fit_dixon_coles(matches, verbose=True)
        if fit:
            ranked = sorted(fit['ratings'].values(), key=lambda r: -r['attack'])
            print("进攻强度排名前5:")
            for r in ranked[:5]:
                print(f"  {r['team']:20s} attack={r['attack']:+.3f} defense={r['defense']:+.3f}")
