"""Download public Nowgoal source files into the local evidence folder."""
import argparse
import hashlib
import gzip
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent / 'evidence'

def fetch(url, name=None):
    host = urlparse(url).hostname or ''
    if not (host.endswith('.nowgoal26.com') or host == 'nowgoal26.com'):
        raise ValueError('Only the requested Nowgoal site is allowed')
    ROOT.mkdir(exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://live11.nowgoal26.com/'})
    with urllib.request.urlopen(request, timeout=35) as response:
        data = response.read()
    if data.startswith(b'\x1f\x8b'):
        data = gzip.decompress(data)
    filename = name or hashlib.sha256(url.encode()).hexdigest()[:16] + '.txt'
    if Path(filename).name != filename:
        raise ValueError('Invalid filename')
    (ROOT / filename).write_bytes(data)
    print(json.dumps({'url': url, 'file': filename, 'bytes': len(data)}), flush=True)
    return data.decode('utf-8-sig', errors='replace')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='+')
    args = parser.parse_args()
    for value in args.urls:
        url, _, name = value.partition('|')
        try:
            fetch(url, name or None)
        except Exception as error:
            print(json.dumps({'url': url, 'error': str(error)}), flush=True)
