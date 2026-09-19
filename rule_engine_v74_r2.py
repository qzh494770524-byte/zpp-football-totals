"""Faithful implementation of gz/足球多庄大小球扫盘执行规则_v7.4-Frozen-R2.md.

This supersedes apply_rule_system_beidan20260911.py's O/U scoring logic. Key
departures, all directly required by the spec document:

  Section 4 (单一庄家的方向计算): per-book direction is LINE-MOVEMENT first
  (current line vs opening line, >=0.25 either way), falling back to a
  devigged-probability delta (>=1pp) only when the line hasn't moved. This
  replaces the old side_of()'s single-snapshot raw-water comparison, and adds
  a real 'neutral' outcome the old code never had.

  Section 5 (多庄一致率): consistency rate divides by ALL valid books;
  neutral-direction books count in the denominator, not the numerator of
  either side. A match can have over_rate + under_rate < 1 as a result.

  Section 6 (正式执行规则): of the old code's four star-contributing rules,
  three are explicitly downgraded to observation-only fields that can never
  produce stars or a formal recommendation:
    - 规则R2 (single-book water-strength band)  -> observed only
    - 规则R4 (all-book majority, any side)       -> observed only
    - H2 (high-consistency under)                -> observed only, and
      explicitly NOT symmetric evidence of "lure to under" (十四·禁止事项 #1)
  规则2.2 (core-4 majority, water<0.85 strength gating) is the ONLY rule left
  that can produce a "保留" (actionable) final status -- it keeps its original
  internal mechanics (core book set, >=3/4 majority, water<0.85 strength
  count, 3-vs-2-vs-1 star tiers) unchanged, just fed the new Section-4
  direction instead of the old single-snapshot side_of().

  H1/H1+/H2 are computed and recorded but do NOT affect final_status.
  Originally implemented as a hard veto per the spec document (>=10 valid
  books, >=80% reading 'over' -> force 剔除), but backtest_v74_r2.py's
  2026-09-13 run on the largest available sample (n=682 pooled across all
  three batches, most of it from a since-expanded 09-02~09-13 multi-bookmaker
  workbook) found the "excluded" pool actually hit 55.1%, not the ~38.5% the
  source document cites from its own OOS-2 validation. Re-running that
  original validation's own code against the same nominally-unchanged
  workbook file now returns 2473 usable matches instead of 384 -- strong
  evidence the original finding came from a small, non-random subset (only
  the matches that already had core-4 quotes backfilled at the time), not a
  real effect. Per the document's own 十三·样本外验证门槛 (formal evaluation
  needs 50+ samples across 10+ distinct match days, and 十四·禁止事项 bars
  reusing old matches to justify a new rule), H1 stays in 观察-only mode
  until it's re-validated against fresh, clearly-dated data.

Data-availability caveat this module is honest about: our historical batches
(comp_*.json snapshots, and the 09-02~09-09 folder workbook) only carry TWO
timepoints per book (初盘/initial, 页面即时/live) rather than the document's
ideal three (T-120/T-60/T-10). Section 4's direction calc only needs two
points and is unaffected. What's NOT reconstructable from 2-point data is
Section 8's 盘口过程标签 (needs 3 points to detect "临场反转" specifically)
and a fully-verified H1+ 临场转向 check -- H1+ here uses a 2-point
approximation (documented inline) precisely matching how the source document
itself says its own second validation batch was built ("页面即时快照，并非
全部经过真正T-10历史核验" -- 十三·H1下一阶段目标), so this is not a lower
standard than the document's own precedent, just not yet the fully-upgraded
T-10-verified version it reserves for promoting 反向观察小球 to a real rule.
"""
import math

CORE_PRIORITY = [1, 31, 3, 8]  # 澳彩 > 利记 > 皇冠 > Bet365 (文档 六·H1+ / 七.4)
CORE_NAMES = {1: '澳彩', 31: '利记', 3: '皇冠', 8: 'Bet365'}

# Ported from apply_rule_system_beidan20260911.py -- found earlier this
# session that Korean-league matches were getting undeserved high stars
# despite this project's own documented downgrade rule for that league
# system's overall reliability. Not part of the R2 spec document itself, but
# a real, already-validated safety rule that must not silently drop out when
# 规则2.2's star computation gets ported to a new engine.
LEAGUE_CAPS = [
    (('K League 1', 'Korea Republic K1', 'K1 League'), 3, '韩职联(顶级)上限⭐⭐⭐'),
    (('K League 2', 'K League 3', 'Korean FA Cup', 'Korea K2', 'Korea K3', 'WK League'), 2, '韩K2联及以下上限⭐⭐'),
]


def league_cap(league_en):
    for keys, cap, note in LEAGUE_CAPS:
        if any(k.lower() in league_en.lower() for k in keys):
            return cap, note
    return None, None


def devig_p_over(q):
    q_o = 1 / (1 + q['over'])
    q_u = 1 / (1 + q['under'])
    return q_o / (q_o + q_u)


def book_direction_detail(q_initial, q_live):
    """文档 四·单一庄家的方向计算,附带判定依据(线动 vs 纯水位)。

    Added 2026-09-18: Olimpia vs Firpo 和 Hachinohe vs Miyazaki 两场复盘都是
    核心庄多数一致的方向输了,唯一反向的那家核心庄反而赢了,而且两次反向都是
    真的动了盘口线,不只是水位变化。n=2太小不能改规则,但先把"哪家反向、反向
    是靠线move还是纯水位"这个维度记下来(见 core_dissent),攒够样本再研究要
    不要给这种反向额外权重。Returns (side, basis); basis 是
    'line_move' | 'water_only' | 'neutral' | 'no_data'。
    """
    if not q_initial or not q_live:
        return 'neutral', 'no_data'
    line_delta = q_live['line'] - q_initial['line']
    if line_delta >= 0.25:
        return 'over', 'line_move'
    if line_delta <= -0.25:
        return 'under', 'line_move'
    delta_p = (devig_p_over(q_live) - devig_p_over(q_initial)) * 100
    if delta_p >= 1:
        return 'over', 'water_only'
    if delta_p <= -1:
        return 'under', 'water_only'
    return 'neutral', 'neutral'


def book_direction(q_initial, q_live):
    """文档 四·单一庄家的方向计算。Returns 'over' | 'under' | 'neutral'."""
    return book_direction_detail(q_initial, q_live)[0]


def book_tier(n_valid):
    """文档 二·庄家数量等级。"""
    if n_valid < 8:
        return '不足'
    if n_valid < 10:
        return '观察'
    return '有效'


def consistency_label(rate):
    """文档 五·一致率分层。"""
    if rate < 2 / 3:
        return '分散'
    if rate < 0.8:
        return '多数同向'
    return '高度一致'


def strength_band(water):
    """文档 六·规则R2 (旧'规则2')使用的水位分档,现仅作观察字段。"""
    if water < 0.75:
        return 4, '极强(<0.75)'
    if water < 0.83:
        return 3, '强(0.75-0.82)'
    if water < 0.89:
        return 2, '中强(0.83-0.88)'
    return 0, '弱/不构成信号(>=0.89)'


def _water_of(books, cid):
    q = books[cid]['initial']
    return min(q['over'], q['under'])


def evaluate_v74_r2(mid, league_en, books):
    """books: {cid: {'initial': {line,over,under}, 'live': {line,over,under}}}.

    Returns the 文档十·最终输出等级 classification plus every rule's raw
    (never-deleted, per 十四·禁止事项#9) observation fields.
    """
    directions = {}
    direction_basis = {}
    anomaly = None
    for cid, q in books.items():
        init, live = q.get('initial'), q.get('live')
        if init is None or live is None:
            continue
        try:
            if init['line'] <= 0 or live['line'] <= 0 or min(init['over'], init['under'], live['over'], live['under']) <= 0:
                anomaly = anomaly or f'庄家{cid}盘口线或水位非正值'
                continue
        except (KeyError, TypeError):
            anomaly = anomaly or f'庄家{cid}报价字段缺失'
            continue
        directions[cid], direction_basis[cid] = book_direction_detail(init, live)

    n_valid = len(directions)
    tier = book_tier(n_valid)

    over_n = sum(1 for d in directions.values() if d == 'over')
    under_n = sum(1 for d in directions.values() if d == 'under')
    over_rate = over_n / n_valid if n_valid else 0.0
    under_rate = under_n / n_valid if n_valid else 0.0

    valid_cids = [c for c in books if books[c].get('initial') and c in directions]
    anchor_cid = 1 if 1 in valid_cids else (min(valid_cids, key=lambda c: _water_of(books, c)) if valid_cids else None)
    anchor_line = books[anchor_cid]['initial']['line'] if anchor_cid is not None else None

    result = dict(
        mid=mid, league=league_en, n_valid=n_valid, tier=tier,
        over_n=over_n, under_n=under_n,
        over_rate=round(over_rate, 4), under_rate=round(under_rate, 4),
        anchor_cid=anchor_cid, anchor_line=anchor_line,
        r1=None, h1=False, h1_plus=False, h2=False,
        rule22_raw=dict(side=None, stars=0, reason=None),
        rule2_observed=None, rule4_observed=None, core_dissent=[],
        core_majority_basis=[], core_majority_line_moves=0,
        final_status='数据待核验', final_side=None,
        reverse_observe_side=None, notes=[],
    )

    if anomaly:
        result['notes'].append(anomaly)
        return result

    if tier == '不足':
        result['final_status'] = '观察'
        result['notes'].append(f'有效庄家{n_valid}<8,数据不足,只保存')
        return result

    # R1: 有效庄家>=10 且某方向一致率达到66.7%
    if n_valid >= 10 and (over_rate >= 2 / 3 or under_rate >= 2 / 3):
        r1_side = 'over' if over_rate >= under_rate else 'under'
        result['r1'] = dict(side=r1_side, rate=round(max(over_rate, under_rate), 4),
                             label=consistency_label(max(over_rate, under_rate)))

    # R2 (旧"规则2"单庄水位强度) -- 观察字段,不加星,不用于仓位
    if anchor_cid is not None:
        aw = _water_of(books, anchor_cid)
        band_stars, band_label = strength_band(aw)
        result['rule2_observed'] = dict(water=round(aw, 2), band=band_label, legacy_would_be_stars=band_stars)

    # R4 (全部庄多数方向) -- 观察字段,不加星,不单独形成推荐
    if n_valid >= 3:
        r4_side = 'over' if over_n >= under_n else 'under'
        result['rule4_observed'] = dict(side=r4_side, rate=round(max(over_rate, under_rate), 4))

    # 规则2.2 冻结规则:核心四庄多数 + water<0.85 强度分级,方向改用四节的新算法
    core_dirs = {cid: directions[cid] for cid in CORE_PRIORITY if cid in directions}
    if len(core_dirs) >= 2:
        side_counts = {}
        for cid, d in core_dirs.items():
            if d == 'neutral':
                continue
            side_counts.setdefault(d, []).append(cid)
        if side_counts:
            majority_side, cids_maj = max(side_counts.items(), key=lambda kv: len(kv[1]))
            n_majority = len(cids_maj)
            n_total = len(core_dirs)
            strong = sum(1 for c in cids_maj if _water_of(books, c) < 0.85)
            # 观察字段,不影响final_status/stars -- 记录哪家核心庄反向、反向依据是
            # 线move还是纯水位,供样本攒够后研究(见book_direction_detail的说明)。
            result['core_dissent'] = [
                dict(cid=cid, name=CORE_NAMES.get(cid, str(cid)),
                     side=core_dirs[cid], basis=direction_basis.get(cid))
                for cid in CORE_PRIORITY if cid in core_dirs and core_dirs[cid] != majority_side
            ]
            # 同一批数据,记多数方向自己是怎么形成的 -- 2026-09-19复盘发现"三场选三场,
            # 唯一输的塞伊奈约基vs玛丽港"正是核心4家全程没有一家真的挪过线,91.7%一致率
            # 全靠水位堆出来;这个区分深挖时才查出来,选球时没用上。现在选球时就该看:
            # 多数方向里有几家是line_move(线真的动了)撑起来的,0家=纯水位堆出来的多数,
            # 是比H1/H1+更早、更直接的"确认是否扎实"信号,即使这个match本身没触发H1。
            result['core_majority_basis'] = [
                dict(cid=cid, name=CORE_NAMES.get(cid, str(cid)), basis=direction_basis.get(cid))
                for cid in cids_maj
            ]
            result['core_majority_line_moves'] = sum(
                1 for cid in cids_maj if direction_basis.get(cid) == 'line_move')
            if n_majority >= 3 and strong >= n_majority / 2:
                result['rule22_raw'] = dict(side=majority_side, stars=3,
                                             reason=f'核心{n_majority}/{n_total}庄一致{majority_side},多数<0.85')
            elif n_majority >= 3:
                result['rule22_raw'] = dict(side=majority_side, stars=2,
                                             reason=f'核心{n_majority}/{n_total}庄一致{majority_side},强度不够0.85')
            elif strong == 1 and n_majority < 3:
                result['rule22_raw'] = dict(side=majority_side, stars=1,
                                             reason='伪强信号:仅1庄达标,其余不跟随,降级')

    # League-specific hard cap (Korean league system), applied right after
    # 规则2.2's stars are set so it can't be bypassed by any later logic --
    # same placement discipline as the original engine used.
    cap, cap_note = league_cap(league_en)
    if cap is not None and result['rule22_raw']['stars'] > cap:
        result['rule22_raw']['reason'] = f"{result['rule22_raw']['reason']};{cap_note},封顶降为{'★'*cap}"
        result['rule22_raw']['stars'] = cap

    # H1: 多庄拥挤大球反向风险 -- 标签仅供观察,不再改变final_status。
    # 2026-09-13 backtest_v74_r2.py 用扩大后的样本(n=682, 09-02~09-13+09-11+09-12)
    # 复核发现被H1命中的"拥挤大球"实际命中55.1%,不支持文档引用的38.5%验证结果
    # (该验证很可能建立在当时数据尚未补全、非随机的384场子集上)。按文档自己的
    # 十三·样本外验证门槛(需50+样本、覆盖10+不同比赛日,不得拿旧比赛证明新规则),
    # 现阶段H1退回"观察"级别,只打标签、留痕,不再触发剔除或反向观察下注。
    if n_valid >= 10 and over_rate >= 0.80:
        result['h1'] = True
        result['notes'].append('多庄拥挤大球反向风险(诱大候选,仅观察,未获样本外复核支持)')
        conflict = False
        for cid in CORE_PRIORITY:
            if cid not in directions:
                continue
            if directions[cid] != 'over':
                conflict = True
                break
            q = books[cid]
            if (q['live']['line'] - q['initial']['line']) < 0.25:
                conflict = True
                break
        result['h1_plus'] = conflict
        if conflict:
            result['notes'].append('H1+重点冲突')

    # H2: 高度一致小球观察 -- 不认定诱小,不加星 (十四·禁止事项#1)
    if n_valid >= 10 and under_rate >= 0.80:
        result['h2'] = True
        result['notes'].append('高一致小球观察(不认定诱小,不加星)')

    # ---- 十·最终输出等级 ----
    # H1不再直接决定final_status(见上方说明);状态完全按数据完整度+规则2.2走,
    # H1/H1+/H2只作为并行观察字段保留在结果里,供继续积累样本外验证用。
    r22 = result['rule22_raw']
    if tier == '观察':
        result['final_status'] = '观察'
        result['final_side'] = result['r1']['side'] if result['r1'] else None
    elif r22['side'] is not None and r22['stars'] > 0:
        result['final_status'] = '保留'
        result['final_side'] = r22['side']
        result['notes'].append(f"规则2.2原始验证状态保留:{r22['reason']}")
    elif result['r1']:
        result['final_status'] = '观察'
        result['final_side'] = result['r1']['side']
    else:
        result['final_status'] = '观察'

    return result
