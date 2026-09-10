import json
from pathlib import Path
import unittest
from nowgoal_collect import parse_fixtures, prematch, literal_array


class DataSemantics(unittest.TestCase):
    def test_fixture_scope_and_timezone(self):
        matches = parse_fixtures(json.loads(Path('evidence/today.json').read_text(encoding='utf-8')))
        self.assertEqual(len(matches), 418)
        self.assertEqual(len({m['id'] for m in matches}), 418)
        self.assertTrue(all(m['kickoff'].startswith('2026-09-09T') for m in matches))
        self.assertEqual(matches[0]['kickoff'], '2026-09-09T00:00:00+08:00')
        self.assertEqual((matches[0]['home_score'], matches[0]['away_score']), (1, 1))

    def test_exclude_inplay_closed_and_post_kickoff(self):
        odds = {'u': '0.8', 'g': '0', 'd': '1'}
        def record(mt, kind=2, close=False):
            return {'mt': mt, 'type': kind, 'close': close, 'odds': odds}
        match = {'kickoff': '1970-01-01T08:01:40+08:00', 'history': {'ah': [
            record(99), record(90), record(101), record(100), record(98, 0), record(97, close=True)]}}
        self.assertEqual([r['mt'] for r in prematch(match)], [90, 99])

    def test_literal_parser(self):
        self.assertEqual(literal_array("1,'Club, FC',,'It\\'s FC',-1"), [1, 'Club, FC', None, "It's FC", -1])
        with self.assertRaises((ValueError, SyntaxError)):
            literal_array("__import__('os').getcwd()")


if __name__ == '__main__':
    unittest.main()
