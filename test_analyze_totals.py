import unittest
from analyze_totals import settle, quote, bootstrap


class TotalsSettlement(unittest.TestCase):
    def test_quarter_line_two_goals(self):
        self.assertEqual(settle(2, 2.25, .9), {'grade': -1, 'result': '半输', 'profit': -.5})
        self.assertEqual(settle(2, 2.25, .9, 'under'), {'grade': 1, 'result': '半赢', 'profit': .45})

    def test_quarter_line_three_goals(self):
        self.assertEqual(settle(3, 2.75, .8)['profit'], .4)
        self.assertEqual(settle(3, 2.75, .8, 'under')['profit'], -.5)

    def test_push_and_full_outcomes(self):
        self.assertEqual(settle(3, 3, .88)['result'], '走盘')
        self.assertEqual(settle(3, 2.5, .88)['profit'], .88)
        self.assertEqual(settle(2, 2.5, .88)['profit'], -1)

    def test_complementary_settlement(self):
        for total in range(16):
            for quarter in range(41):
                over = settle(total, quarter/4, 1)
                under = settle(total, quarter/4, 1, 'under')
                self.assertEqual(over['grade'], -under['grade'])
                self.assertAlmostEqual(over['profit'], -under['profit'])

    def test_invalid_quotes_and_degenerate_interval(self):
        self.assertIsNone(quote({'u':'', 'g':'2.5', 'd':'0.9'}))
        self.assertIsNone(quote({'u':'0.9', 'g':'2.6', 'd':'0.9'}))
        self.assertEqual(bootstrap([0]*10), (0,0))


if __name__ == '__main__':
    unittest.main()
