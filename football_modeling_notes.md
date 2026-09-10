# 足球数据建模方法论 - 知识积累笔记

由每日云端研究agent自动追加。目的:为 `v8_backtest_pipeline.py`(大小球盘口漂移模型)
积累可能有用的建模方法论知识——不是具体某场比赛的情报,而是可迁移的分析思路。

已知这套框架目前验证过的东西(供每次研究时参考、避免重复造轮子):

- 盘口漂移模型(线体+水位+欧赔平局代理+让球深浅)在8天/3939场大样本上命中率约51.2%,
  信心分级(S/A/B/C/D)在大样本下有微弱但真实的单调梯度。
- 水位一致性对"大"方向有效(57.4%),对"小"方向基本无效(51%),原因初步判断是
  散户天然偏爱押大球、稀释了"小"方向资金流的信息含量,而非庄家刻意诱导。
- "猜小+平局隐含概率同时上升"这个交叉确认信号,在日期分半的样本外验证中复现
  (训练集54.8% vs 测试集56.1%,且未确认时测试集只有47.8%)。
- 用真实球队近6场/主客场进失球数据做的简易泊松进球模型,以及"两模型冲突时信进球模型"
  这条规则,在样本外验证中被推翻(反而是旧盘口模型更准),已废弃。
- 另建了一套独立于v8漂移模型的"固定规则"方法(backtest_today79.py):不看盘口怎么移动的,
  只取赛前有时间核验的最后一口报价,固定公司优先级(Bet365/Crown/Sbobet/1xBet)、至少3家
  同盘口、去水后指标取中位数决定方向。79场回测正收益场次率61.1%(n=19,95% CI
  38.6%~79.7%,区间很宽),同一批比赛"无脑选大球"基线的收益(25.0%)反而比这套规则
  (13.5%)更高——目前还不能算验证过的优势,只是一次事后固定规则回测。
- 六庄(Bet365/皇冠/Sbobet/1xBet/M88/12Bet)一致偏小时反买大球:912场里383场六家最后同
  盘口,其中96场一致偏小,没有发现稳定优势,也没有证据支持"庄家诱小"这个猜测。
- "多庄全票同向"不等于更可信:在79场回测的19场结算样本里拆开看,分歧组(多数vs少数但
  中位数仍过线)胜率66.7%(n=9)反而略高于全票一致组55.6%(n=10)——样本太小,完全在
  噪声范围内,但说明"看起来更一致=更可信"这个直觉本身没有数据支撑,不要凭直觉给信号分级。
- 偏离0.5的幅度大小同样测过,一样没有救:19场里margin更大(信号更强)那一半胜率44.4%,
  margin更小(信号更弱)那一半反而70.0%,方向和常识相反。同一批数据里连着测了"全票一致"、
  "偏离幅度"、"参与公司数"三个自然会想到的置信度分层,没有一个站得住——这本身就是19场
  这个量级下,任何切法基本都是噪声互搏的证据。不要在同一小样本上继续换着法子试第4个分层
  条件,那样迟早会"试出"一个看起来好看的,但那是选择偏差,不是发现。
- 权威来源印证:检测约2%的边际优势大约需要50轮×7个市场的样本,200注的样本仍不足以把
  真实优势和方差分开;发布前先丢弃九个测试失败的想法、只展示活下来的第十个,是体育博彩里
  典型的选择偏差陷阱。这两条直接解释了上面79场/19场的结果为什么不可信。

---

## 研究记录

<!-- 每次云端agent运行后在下面追加一个章节,格式: ## YYYY-MM-DD 主题 -->

## 2026-09-10 识别真正的Sharp Money信号:庄家分层结构 + 去水(de-vig)方法如何强化水位漂移信号

### 为什么研究这个

笔记里已经记录了一个尚未解释清楚的现象:"水位一致性对'大'方向有效(57.4%),对'小'方向基本无效
(51%)",初步归因是散户天然偏爱押大球稀释了'小'方向的信息含量。这个解释是合理的方向,但目前
`v8_backtest_pipeline.py` 里的 `compute_odds_drift_signal()` 把参与计算的每一家博彩公司
一视同仁、简单平均(`line_signals`/`water_signals` 对所有公司等权),完全没有利用"这是哪家公司"
这个信息。行业里关于"sharp money vs 公众资金"的研究,核心方法论恰好是不要把所有公司的盘口变动
等权处理,而是区分"定价者(price leader)"和"跟随者(follower)"。这正好是笔记里那个薄弱环节可以
深挖、且直接可操作的方向,所以本次选它作为研究主题。

### 外部研究结论(方法论,非本仓库回测结果)

1. **Reverse Line Movement(逆向盘口移动)**:当盘口朝着与"多数下注方向"相反的方向移动时
   (例如多数注单押主队但盘口反而变得对主队更不利),通常意味着少数"sharp"下注的资金权重
   超过了大量"public"注单,庄家据此调整价格而非单纯跟票数走。
2. **Steam Move(急速联动变盘)**:多家博彩公司在很短时间内(通常以分钟计)朝同一方向大幅
   同步调整盘口/水位,是职业玩家或联合资金(betting syndicate)下重注后,一家公司先调整、
   其余公司迅速跟随对齐的信号,比缓慢渐进的盘口漂移更接近"真沙普"。
3. **Closing Line Value(收盘价值,CLV)**:大量研究(包括 Pinnacle 自己发布的长期跟踪)显示,
   CLV 是判断一个信号/一个下注策略长期是否有优势的最可靠单一指标 —— 长期能在收盘前拿到比收盘更
   好价格的一方,长期是盈利的;胜率本身反而不如 CLV 可靠,因为短期胜率受方差影响很大。这提示:
   我们评估"水位漂移信号"时,除了看命中率,也应该看"信号出现时的报价 vs 该场比赛的最终收盘价",
   这是比命中率更早、更稳定的有效性检验指标,而且不需要等比赛结束就能算。
4. **庄家分层(market maker / leader-follower)**:业内公认的分层是 Pinnacle(以及 Asian
   handicap 圈子里的 Crown 皇冠、SBOBET 沙巴、Betfair 交易所)是价格发现的"leader",大量中小
   型公司(包括面向欧美散户的软件/软盘公司)基本是"跟盘",只有在自己接到明显偏斜的下注量时才会
   独立偏离 leader 的价格,大多数时候是 leader 变、他们跟着变。leader 先变、follower 后变
   本身就是区分"真实资金驱动的价格调整"和"纯粹散户下注量堆积"的一个可观察代理。

### 与本仓库数据的对应关系(重要,待验证)

`nowgoal_collect.py` 里已经维护了一份公司ID到名称的映射(第167-169行):
`{8: 'Bet365', 3: 'Crown', 31: 'Sbobet', 50: '1xBet', 17: 'M88', 24: '12Bet', 42: '18Bet',
12: 'Easybet', 1: 'Macauslot', 4: 'Ladbrokes', 14: 'Vcbet', 19: 'Interwetten'}`。
按行业里公开、圈内公认的经验分层(注意:这是外部通用认知,不是本仓库回测验证过的结论):

- **偏向 leader / 定价方**: Crown(皇冠)、Sbobet(沙巴) —— 亚洲盘圈子里长期被认为是价格发现
  的源头之一,大额职业资金优先在这类平台上交易。
- **偏向 follower / 面向散户的软盘**: Bet365(欧美散户下注量极大,但其亚盘定价习惯上跟随
  Asian leader 而非自己发现价格)、1xBet、12Bet、18Bet、Easybet、Vcbet、Interwetten —— 这些
  公司的盘口变动更可能反映的是"票数堆积"而非"聪明钱"。
- **风格独特、变动缓慢保守**: Macauslot(澳门)一贯以调整滞后、保守著称,单独看它的变动意义有限,
  但如果连它都跟着变,说明信号已经很强。
- Ladbrokes、M88 目前没有查到足够明确的圈内共识定位,暂归为"中性/待观察"。

这个分层需要当作**未经本项目回测验证的外部先验**使用,不能直接当结论写死进模型,但值得作为
一个新维度加入回测:把现有等权平均的 `line_signals`/`water_signals`,拆分成"leader 子集"
(Crown+Sbobet)和"follower 子集"(其余),分别统计:
  a) leader 与 follower 方向一致 vs 冲突时,命中率是否有别于现在整体的 51.2%;
  b) 当 leader 方向 = 现有"大方向水位一致"信号方向时,57.4% 这个数字是否进一步提升;
  c) 当"小"方向变盘只有 leader 变了、follower 没跟或跟得慢时,是否比现在的 51% 更有信息量
     (即笔记里说的"小方向被散户资金稀释"的问题,是否可以通过只看 leader 动向来部分修正)。

### 数据缺口(接入前必须先补的字段)

目前 `load_workbook_data()` 在解析"各庄大小球与欧赔"和"多庄亚洲盘"两个sheet时,
`ou_by_match`/`ah_by_match` 里每一行 dict 只保存了赔率数值(`open_over/live_over/...`),
**没有保留 `cid`/`cname` 字段**(参见 v8_backtest_pipeline.py 第92-93行、105-106行,
源数据行里其实有 `cid, cname` 但被丢弃了)。要验证上面的 leader/follower 分组假设,
第一步必须在 `load_workbook_data()` 里把 `cname`(或 `cid`)也存进每行 dict,这是纯数据管道
改动,不涉及模型逻辑,风险很小,可以先做。

另外,steam move 严格定义是"分钟级的多家联动",而目前 Excel 数据结构对每场比赛只有
"开盘"和"临场最后一口"两个快照点(没有中间时间序列),**无法做真正的分钟级联动检测**。
如果要验证"steam move"这个更严格的假设,需要在 `nowgoal_collect.py` 抓取阶段增加至少
1-2个中间时间点的快照(比如赛前2小时、赛前30分钟),这是采集层面的工作量,不是回测脚本能
单独解决的,值得记录但本次不展开。

### 去水(de-vig)方法:一个相关的、可以顺手改进的技术点

`compute_odds_drift_signal()` 里的 `implied_prob_pair()`(v8_backtest_pipeline.py
第59-62行)用的是最基础的等比例归一化去水法(multiplicative method):
`p_i = (1/odds_i) / sum(1/odds_j)`。这是双向(大/小、主/客)市场最常用也最简单的方法,
在两边水位接近对称时表现尚可。但学术研究(Cain, Law & Peel 2000《Adjusting Bookmaker's
Odds to Allow for Overround》,后续 Shin 1993 的方法被广泛实现,如 R 语言 `implied` 包、
Python `mberk/shin` 包)指出:当赔率明显不对称(一边热门一边冷门,亚盘深水盘常见)时,
更贴近真实概率的是 **Shin's method**:

```
π_i(z) = (sqrt(z^2 + 4(1-z) * o_i^2 / sum(o_j^2)) - z) / (2(1-z))
```

其中 `o_i` 是第 i 个结果的原始隐含概率(未去水),`z` 是"知情交易者比例"参数,需要用非线性最小
二乘迭代估计(可直接参考开源实现 `mberk/shin`,不需要重新推导迭代算法)。研究结论:在双向盘接近
对称时 multiplicative 和 Shin 差异很小;在明显不对称(深水/浅水盘、三项赔率里有明显热门冷门)时
Shin 对 favorite-longshot bias(热门被低估、冷门被高估的系统性偏差)矫正更彻底,通常估计出更贴近
真实赛果的概率。本项目里"欧赔平局代理"信号(三项赔率,天然容易不对称)是最适合先试验 Shin 方法
的地方;"大小球水位"如果长期偏向一边(比如深盘大球水位常年不对称)也值得一试。

### 接入建议(供以后决定是否做,不代下结论)

1. **低成本、可以先做**:在 `load_workbook_data()` 里保留 `cname`,把 `ah_by_match`/
   `ou_by_match` 的每行加上公司名字段,为分组统计做准备,不改变现有信号计算逻辑。
2. **中等成本、需要独立离线验证脚本**(不要改 v8_backtest_pipeline.py 主逻辑):写一个单独的
   分析脚本,用已有历史 predictions.json + 原始 Excel 里的 `cid`,按"leader(Crown/Sbobet)
   方向 vs follower 方向"重新切分现有回测样本,统计各分组命中率,看是否比整体 51.2% 或"大方向"
   57.4% 有显著提升。这一步不需要新抓数据,用现有历史文件就能做。
3. **高成本、需要改采集脚本**:如果第2步显示 leader/follower 分组确实有信息量,再考虑在
   `nowgoal_collect.py` 里增加公司名字段的完整保留 + 中间时间点快照,以便未来做真正的
   steam-move(分钟级联动)检测。
4. **去水方法替换**:在 `implied_prob_pair()` 旁边新增一个 `implied_prob_shin()` 作为对照
   (不要替换现有实现,保持可回退),用两种方法各算一版 `water_signal`,离线比较两者在样本外的
   命中率差异,尤其重点看欧赔平局代理这个子信号。

### 信息来源

- Reverse line movement / steam move 定义与判别方法: [betfanatics.com](https://betfanatics.com/blog/what-is-sharp-money-and-steam-moves-in-sports-betting), [xclsvmedia.com RLM指南](https://xclsvmedia.com/reverse-line-movement-explained-how-to-spot-sharp-money-sports-betting-2026-guide/), [bettoredge.com](https://www.bettoredge.com/post/tracking-line-movement-for-market-inefficiencies)
- Closing Line Value 作为长期盈利能力最可靠指标: [sharpfootballanalysis.com CLV指南](https://www.sharpfootballanalysis.com/sportsbook/clv-betting/), [vsin.com CLV说明](https://vsin.com/how-to-bet/the-importance-of-closing-line-value/)
- 庄家分层(leader/follower)与 Pinnacle/Asian handicap 市场结构: [unabated.com 市场制造者](https://unabated.com/articles/who-sets-the-sports-betting-line-market-makers), [completesports.com Pinnacle定价](https://www.completesports.com/how-pinnacle-sets-the-sharpest-lines/), [oddalerts.com 亚洲盘sharp book](https://www.oddalerts.com/learn/sharp-bookmakers-football-betting)
- 哪家公司先变盘作为sharp信号的判别经验: [covers.com 盘口变动解读](https://www.covers.com/guides/what-line-moves-can-tell-us), [bettoredge.com sharp vs public](https://www.bettoredge.com/post/sharp-money-vs-public-action-line-movement-explained)
- Favorite-longshot bias 在足球赔率市场的学术证据(用于理解为何不对称赔率需要更精细的去水法):
  [ResearchGate: Favorite-Longshot Bias and Market Efficiency in the Soccer Betting Market](https://www.researchgate.net/publication/351985837_Favorite-Longshot_Bias_and_Market_Efficiency_in_the_Soccer_Betting_Market),
  [ScienceDirect: 什么驱动了体育博彩市场里的赔率偏差](https://www.sciencedirect.com/science/article/abs/pii/S105905602300059X)
- 去水方法(multiplicative / power / Shin)对比与实现: [ResearchGate: Adjusting Bookmaker's Odds to Allow for Overround (Cain, Law & Peel)](https://www.researchgate.net/publication/326510904_Adjusting_Bookmaker's_Odds_to_Allow_for_Overround), [Shin方法公式与GitHub实现 mberk/shin](https://github.com/mberk/shin), [opisthokonta.net implied包说明](https://opisthokonta.net/?p=1797), [karlwhelan.com Shin方法与z参数论文](https://www.karlwhelan.com/Papers/ShinzNov24.pdf)

### 验证结果(2026-09-10 补充,已用现有历史数据测试): Leader/Follower分层假设,未获支持

上面提出的"Crown/Sbobet(leader) vs 其余公司(follower)"分层假设,当天就用已有的8天历史数据
(不需要重新抓取)离线测试了一遍(min_companies>=2, n=3650可评分场次)。结果:

- 只用Leader方向单独预测: 51.63%(n=1774),和整体模型51.73%基本没区别。
- Leader与Follower方向"一致" vs "冲突": 一致时51.29%(n=1472),冲突时信Leader反而是53.14%
  (n=271,但样本小,标准误约3pp,不显著)——方向和假设(一致更可信)相反。
- "判小+Leader确认": 52.77%(n=578) vs "判小+Leader未确认": 50.71%(n=1124)——方向勉强对,
  但只差2个点,在1.3个标准误内,不算显著。
- "判大+Leader确认"(本该强化前面发现的57.4%水位一致效应): 51.27%(n=987) vs
  "判大+Leader未确认": 52.76%(n=961)——**方向和假设相反**,确认反而更低。

**结论:Crown/Sbobet作为leader的简单二分法,拿真实数据一测站不住,不要再往这个方向深挖
(至少不要用"是不是Crown/Sbobet"这么粗的二分法)。** 可能的原因:leader/follower这个分层
本身是海外主流体育(NFL/NBA等)博彩市场的经验,不一定适用于亚洲盘/东亚及南美中小联赛为主的
Nowgoal数据;也可能两家公司样本(n=1774)对这批联赛覆盖不够多。如果以后还想深挖这个方向,
要先确认Crown/Sbobet在当前数据集里到底覆盖了哪些联赛、样本是否有代表性,而不是直接扩大到
全量重测。

---

## 2026-09-10(续) 固定规则方法:79场回测 + 六庄诱小复盘 + 5场实盘预测的"全票一致"检验

### 固定规则方法是什么、为什么和v8漂移模型分开

`backtest_today79.py` / `predict_live5.py` 用的是一套和 `v8_backtest_pipeline.py` 完全独立
的方法:不看开盘到临场的漂移方向,只取"赛前有时间核验的最后一条大小球历史记录"(来自
`history_url` 接口,精确到秒级时间戳,不是Excel里的开盘/临场两点快照)。固定公司优先级
`[Bet365=8, Crown=3, Sbobet=31, 1xBet=50]`,要求同一盘口至少3家在这个优先级列表里的公司
有报价,盘口选"覆盖公司数最多的那个,并列按优先级"。方向:每家公司把大水/小水换算成去水后的
隐含概率(`(1/(1+大水)) / (1/(1+大水)+1/(1+小水))`),取这些概率的中位数,大于0.5选大、
小于0.5选小、相等跳过。规则在看到79场里任何一场赛果之前就写死进了 `fixed_rule.json`,不是
事后调出来的。

### 79场固定规则回测(analysis/backtest_79_20260910/)

79场新完结比赛里21场形成预测、19场可结算(58场因同盘口不足3家或无核验记录跳过)。
全赢10、半赢1、走盘1、半输1、全输6,剔除走盘后正收益场次率61.1%(95% CI 38.6%~79.7%,
区间跨了将近一半,n=19撑不住这个精度)。同一批比赛"无脑选大球"基线ROI 25.0%,"无脑选小球"
基线ROI -33.8%——固定规则的ROI(13.5%)反而低于"无脑选大球"。**这不代表规则无效,更可能是
19场的噪声,但明确说明这套规则目前谈不上"验证过的优势",只是一次有纪律的事后回测(锁定规则
在先、结算在后,没有调参)。**

### 六庄一致偏小复盘(analysis/six_book_review_20260910_100510/)——回应"庄家是否诱小"的疑问

固定六家(Bet365/皇冠/Sbobet/1xBet/M88/12Bet),5244场符合比分口径的完赛赛事中912场有六家
可核验历史,383场六家最后报价盘口相同,其中96场六庄一致偏小(来自9月2日至6日,历史覆盖不全,
不能代表总体)。统一按Bet365赛前最后盘口结算:96场里反买大球正收益47/96(49.0%),大球ROI
-0.88%,没有优势。事后收窄到"六家初末同盘且价格指标都向小球移动"的10场子组,反买大球
7/10正收益、ROI+33.45%,但这是看到长崎vs大阪钢巴2-2这场之后才提出的事后条件,10场的95%
区间(约39.7%~89.2%)跨度极大,不能当规律用。**结论:现有数据既不能证明庄家"诱小",也不能
证明"六庄一致偏小反买大球"有稳定优势——报价和赛果不能直接识别庄家意图,后续验证必须先锁定
条件再收集新样本,不能用已经看到结果的比赛去挑条件。**

### 5场实盘预测 + "全票一致"过滤的临时验证

按固定规则对2026-09-10未开赛的比赛做了一次真正的事前预测(不是回测):102场"未来20分钟~24
小时内未开赛"的候选里,只有约7%(66场里4场)能形成预测,而且几乎全被UEFA青年联赛U19占了——
说明这套规则对联赛覆盖要求很高,当前时段主流联赛大多还没开赛,凑出来的5场不代表典型比赛的
命中率。

其中2场(费内巴切U19 vs 罗马、科莫U19 vs 莱比锡红牛)是"多数(2家)vs少数(1家打平/1家反向)"
勉强过中位数0.5的情况,用户直觉认为这种"硬凑"的不该要。顺手用79场回测数据检验了这个直觉:
拆开19场结算样本,"全票一致"组(参与公司全部同向)胜率55.6%(n=10,净+0.25单位),"有分歧"组
(多数vs少数但中位数仍过线)胜率66.7%(n=9,净+2.31单位)——**分歧组反而略高,和"一致更可信"
的直觉方向相反**,但两组都只有9~10场,差距在噪声范围内,不能说分歧组真的更好。已写进上面
"已知验证过的东西"列表。

处理方式:把这2场从实盘预测里剔除,不是因为数据证明它们更差,而是"证据内部有分歧就不推"
本身是合理的风控标准,和"是否提升胜率"是两件独立的事——后续补的2场(卡塔尔联赛
Al Shamal vs Al-Wakra、乌兹别克联赛FK Andijon vs Kuruvchi Kokand)额外要求参与公司全部
同向才收录。最终5场锁定预测存在 `analysis/live_predict_20260910_155445/locked_predictions.json`
(带锁定时间戳),用 `grade_live5.py` 结算。**这次全票一致过滤是应用户风险偏好做的展示层
筛选,不是证明过的模型改进,以后不要把"全票一致"直接当成可以加到v8模型里的新信号,除非未来
在更大样本上专门测过。**

---

## 2026-09-10(续2) 用户明确表示要用这5场实盘下注:样本量要求、CLV优先验证、分数Kelly仓位

### 起因

用户在看到"全票一致"、"偏离幅度"、"参与公司数"三个分层都测不出稳定优势之后,明确说
"我只要稳,我要投注的"。不能为了给一个让人安心的答案而在19场这个小样本上继续挑第4个、
第5个筛选条件——那正好是下面查到的"选择偏差"陷阱本身。于是转向外部资料,查三件事:
这么小的样本到底能不能验证出优势、有没有比等赛果更快的验证方法、如果明知优势不确定还要
下注该怎么控制仓位。

### 查到的结论

1. **样本量:19~79场远远不够。** 检测约2%的真实优势大约需要50轮×7个市场的样本;检测
   1%的优势需要4倍以上的样本。200注的样本仍然不足以把真实优势和方差分开,20注"几乎
   什么都说明不了"。这直接解释了为什么79场回测和19场的三次分层测试都测不出可信的差异——
   不是方法错了,是样本量本身就不支持这个问题有答案。
2. **选择偏差是体育博彩回测里最常见的坑。** 测试十个想法、丢掉九个失败的、把活下来的第十个
   当成"发现"公布,是历史数据回测的经典陷阱——数据挖得越多,越容易挖到纯属巧合的"规律"。
   这是今天没有在19场里继续测第4个分层条件的直接理由。
3. **CLV(收盘价值)比胜率更快验证模型是否有效。** 单纯靠赛果验证一个真实优势可能需要几千注,
   但持续以5%左右的幅度跑赢收盘价,大约50注就能有统计显著性。原因是ROI在小样本上被方差
   主导(靠谱的预测可能短期运气差、垃圾预测可能短期蒙对),而CLV衡量的是"市场后来是否印证了
   你的判断方向",不直接依赖那一场比赛的随机结果。**这意味着以后不必等几百场的胜负结果才能
   判断这套规则是否有信息量,可以先看每次锁定预测之后,收盘价是不是持续朝我们选的方向移动。**
   `clv_live5.py` 已经写好,今晚5场比赛开球后可以跑,对比锁定时的报价和收盘前最后报价,
   不需要等有比分结果。
4. **如果证据不确定还要下注,标准做法是分数Kelly(fractional Kelly),不是满仓单位注。**
   实际优势永远是估计出来的、不是精确已知的;如果按估计优势全额下注(Kelly),一旦估计
   偏高就会变成系统性下注过量。专业玩家普遍只下1/4到1/2 Kelly仓位——半Kelly能拿到接近
   75%的理论增长率,但只承担25%的方差。**这里更关键的是:我们连"是否存在正优势"这件事
   本身都没有在统计上确认(79场的置信区间下限38.6%,包含亏损情形;19场的三次分层测试
   全部不显著),按Kelly逻辑,一个没有确认为正的优势对应的最优仓位接近于零,不是"选5场
   打满"。**

### 对当前5场实盘预测的直接影响

不改变已经锁定的5场预测内容(仍然是那5场,不重新调整选择标准),但结算方式加一层:
`grade_live5.py` 继续按胜负结算(供参考),同时新增 `clv_live5.py` 在赛后计算这5场各自
是收盘价朝我们方向移动(正CLV)还是反向移动(负CLV)。如果以后要持续做这种实盘预测,
CLV应该和胜负一起追踪、写进笔记,而不是只看那一批的胜负数字——胜负在小样本上基本是噪声,
CLV能更早说明这套规则是不是真的在识别市场即将确认的方向。

### 信息来源

- 检测优势所需样本量、200注不足以分离优势与方差: [Punter2Pro 样本量在投注分析里的重要性](https://punter2pro.com/sample-size-betting-results-analysis/), [arXiv: Beating the House - Identifying Inefficiencies in Sports Betting Markets](https://arxiv.org/pdf/1910.08858)
- 小样本回测的过拟合与选择偏差陷阱: [Great Bets 如何在不过拟合的情况下回测投注策略](https://www.greatbets.co.uk/how-to-backtest-a-sports-betting-strategy-without-overfitting/), [Betting Forum 过拟合问题:回测系统为什么在实盘失败](https://www.betting-forum.com/threads/the-overfitting-problem-why-backtested-betting-systems-fail-in-production.47444/)
- CLV比胜率更快验证模型、约50注可达统计显著: [Rowdie CLV是唯一能说明模型好坏的指标](https://www.rowdie.co.uk/closing-line-value-the-only-metric-that-tells-you-whether-your-model-is-any-good), [ModelPlay 投注模型如何验证:Holdout/Grade/EV/CLV](https://modelplay.ai/learn), [sports-ai.dev CLV指南](https://www.sports-ai.dev/blog/closing-line-value-and-ai-model-performance)
- 分数Kelly与优势估计误差: [Matthew Downey 为什么用分数Kelly:不确定性与下行风险模拟](https://matthewdowney.github.io/uncertainty-kelly-criterion-optimal-bet-size.html), [Quantt Kelly准则详解](https://www.quantt.co.uk/resources/kelly-criterion-explained), [arXiv: Kelly betting on horse races with uncertainty in probability estimates](https://arxiv.org/pdf/1701.02814)
