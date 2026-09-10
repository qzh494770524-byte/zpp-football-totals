import unittest
import nowgoal_multi as multi


class MultiBookmakerSemantics(unittest.TestCase):
    def test_half_hour_cadence_excludes_work_duration(self):
        self.assertEqual(multi.next_cycle_delay(120, 1800), 1680)
        self.assertEqual(multi.next_cycle_delay(1900, 1800), 1700)

    def test_history_is_scoped_to_company(self):
        match = {'kickoff': '1970-01-01T08:01:40+08:00', 'state': -1,
                 'multi_history': {'8': {'ah': [{'mt': 90, 'type': 2, 'close': False,
                                               'odds': {'u': '0.8', 'g': '0', 'd': '1'}}]}}}
        self.assertIsNotNone(multi.verified_close(match, 8))
        self.assertIsNone(multi.verified_close(match, 3))
        match['history_refresh_needed'] = ['8']
        self.assertIsNone(multi.verified_close(match, 8))
        match['history_refresh_needed'] = []
        match['state'] = 0
        self.assertIsNone(multi.verified_close(match, 8))

    def test_final_score_requires_finished_state(self):
        match = {'state': 3, 'home_score': 2, 'away_score': 1}
        self.assertIsNone(multi.score(match))
        match['state'] = -1
        self.assertEqual(multi.score(match), '2-1')
        match['home_score'] = None
        self.assertIsNone(multi.score(match))


if __name__ == '__main__':
    unittest.main()
