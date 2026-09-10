import unittest
from backtest_today79 import forecast


class LockedForecastRule(unittest.TestCase):
    def q(self,cid,line=2.5,over=.8,under=1):
        return {'cid':cid,'company':str(cid),'line':line,'over':over,'under':under,'record_time':'2026-09-09T20:00:00+08:00'}

    def test_three_books_required(self):
        self.assertIsNone(forecast([self.q(8),self.q(3)])['side'])
        self.assertEqual(forecast([self.q(8),self.q(3),self.q(31)])['side'],'over')

    def test_different_lines_are_not_pooled(self):
        self.assertIsNone(forecast([self.q(8),self.q(3),self.q(31,line=3)])['side'])

    def test_anchor_priority_not_best_payout(self):
        r=forecast([self.q(50,over=.95),self.q(31,over=.9),self.q(8,over=.8)])
        self.assertEqual(r['anchor_company'],'8')
        self.assertEqual(r['over_water'],.8)

    def test_equal_price_skips(self):
        self.assertIsNone(forecast([self.q(cid,over=.9,under=.9) for cid in (8,3,31)])['side'])

    def test_outcome_fields_cannot_affect_forecasts(self):
        quotes=[self.q(cid,over=1,under=.8) for cid in (8,3,31)]
        before=forecast(quotes)
        for q in quotes:q['actual_total_goals']=99
        self.assertEqual(forecast(quotes),before)
        self.assertEqual(before['side'],'under')


if __name__=='__main__':
    unittest.main()
