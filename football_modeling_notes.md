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
