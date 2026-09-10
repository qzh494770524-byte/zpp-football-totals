"""Run an isolated fresh totals analysis for a Windows scheduled task."""
from datetime import datetime, timedelta, timezone
import html
import json
import msvcrt
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / 'analysis'
TZ = timezone(timedelta(hours=8))


def write_status(value):
    value['updated_at'] = datetime.now(TZ).isoformat(timespec='seconds')
    path = ANALYSIS / 'last_auto_run.json'
    temporary = path.with_suffix('.tmp.json')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    ANALYSIS.mkdir(exist_ok=True)
    # Lock is released by Windows even if a run is interrupted.
    with (ANALYSIS / 'auto_analysis.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return 0  # An already running analysis will publish its own result.
        started = datetime.now(TZ)
        folder = ANALYSIS / ('auto_' + started.strftime('%Y%m%d_%H%M%S'))
        folder.mkdir()
        status = {'state': 'running', 'started_at': started.isoformat(), 'output_directory': str(folder),
                  'dataset': '2026-09-02至2026-09-09的既有赛事，使用最新已抓取数据'}
        write_status(status)
        try:
            with (folder / 'analysis_run.log').open('w', encoding='utf-8') as log:
                completed = subprocess.run([sys.executable, str(ROOT / 'analyze_totals.py'), '--refresh', '--out', str(folder)],
                                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=7200)
            if completed.returncode:
                raise RuntimeError(f'Analyzer exited with {completed.returncode}; see analysis_run.log')
            expected = ['summary.json', '大小球分析.xlsx', '大小球分析.md', '大小球看板.html', 'input_snapshot.json']
            if any(not (folder / filename).is_file() for filename in expected):
                raise RuntimeError('One or more report files are missing')
            summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
            status.update(state='complete', finished_at=datetime.now(TZ).isoformat(),
                          finished_matches=summary['finished_raw'], analyzed_matches=summary['overall']['n'],
                          initial_ou_matches=summary['initial_games'], verified_closing_ou_matches=summary['closing_games'])
            latest = ANALYSIS / '最新自动分析.html'
            text = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>最新大小球分析</title>'
                    '<style>body{font:18px system-ui;margin:48px;line-height:1.9}a{color:#174c86}</style>'
                    '<h1>最新大小球自动分析</h1><p>完成时间：' + html.escape(status['finished_at']) + '</p><ul>')
            for filename, label in [('大小球看板.html', '打开交互看板'), ('大小球分析.xlsx', '下载Excel分析'), ('大小球分析.md', '查看文字报告')]:
                text += f'<li><a href="{html.escape(folder.name + "/" + filename)}">{label}</a></li>'
            text += '</ul><p>这份分析基于运行时已抓到的数据；盘口缺失与核验情况在报告中列出。</p></html>'
            temporary = latest.with_suffix('.tmp.html')
            temporary.write_text(text, encoding='utf-8'); temporary.replace(latest)
            write_status(status)
            return 0
        except Exception as error:
            status.update(state='failed', error=str(error), finished_at=datetime.now(TZ).isoformat())
            write_status(status)
            return 1
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == '__main__':
    raise SystemExit(main())
