import json
from pathlib import Path
import unittest
import nowgoal_history as history
import nowgoal_collect as core


class HistoricalBackfill(unittest.TestCase):
    def test_full_seven_days(self):
        self.assertEqual(history.dates('2026-09-02', '2026-09-08'),
                         ['2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05',
                          '2026-09-06', '2026-09-07', '2026-09-08'])

    def test_only_finished_and_idempotent(self):
        rows = {}
        payload = json.loads(Path('evidence/fixtures_2026-09-02.json').read_text(encoding='utf-8'))
        fixtures = core.parse_fixtures(payload)
        self.assertEqual(history.merge_fixtures(rows, fixtures, '2026-09-02', True), 350)
        self.assertEqual(history.merge_fixtures(rows, fixtures, '2026-09-02', True), 0)
        self.assertEqual(len(rows), 350)
        self.assertTrue(all(r['state'] == -1 for r in rows.values()))
        with self.assertRaises(ValueError):
            history.merge_fixtures(rows, fixtures, '2026-09-03', True)

    def test_all_historical_fixture_counts(self):
        rows = {}
        for day in history.dates('2026-09-02', '2026-09-08'):
            payload = json.loads(Path(f'evidence/fixtures_{day}.json').read_text(encoding='utf-8'))
            history.merge_fixtures(rows, core.parse_fixtures(payload), day, True)
        self.assertEqual(len(rows), 4900)
        self.assertTrue(all(r['home_score'] is not None and r['away_score'] is not None for r in rows.values()))


if __name__ == '__main__':
    unittest.main()
