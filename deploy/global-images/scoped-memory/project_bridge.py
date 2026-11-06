#!/usr/bin/env python3
"""Protected bridge caller; install beside the existing project_auth.py resolver."""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.error
import urllib.request

from project_auth import ScopeError, resolve


def proxy_port(config_dir, session):
    # shortcut: one isolated trial port; replace routing before enabling multiple overlays.
    database = config_dir.parent / 'scoped-memory-1073-stage2/overlay.sqlite'
    if not database.exists():
        return 8096
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=10) as db:
        row = db.execute('SELECT 1 FROM pins WHERE source=?', ('proxy:codex:' + session,)).fetchone()
    return 8097 if row else 8096


def make_request(bridge, subpath, session, params, key, port=8096):
    if bridge not in ('memory', 'skill') or not re.fullmatch(r'[a-z_-]+(?:/[a-z_-]+)*', subpath):
        raise ScopeError('Invalid bridge path')
    if not isinstance(params, dict) or not session or '\r' in session or '\n' in session:
        raise ScopeError('A session and JSON object params are required')
    if port not in (8096, 8097):
        raise ScopeError('Unsupported private proxy')
    return urllib.request.Request(f'http://127.0.0.1:{port}/{bridge}-bridge/v3/{subpath}',
        data=json.dumps(params).encode(), headers={
            'Content-Type': 'application/json', 'x-tdai-service-id': 'default',
            'x-conversation-id': session, 'x-tdai-user-key': key,
        })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bridge', choices=('memory', 'skill'))
    parser.add_argument('subpath')
    parser.add_argument('--session', required=True)
    parser.add_argument('--params', default='{}')
    args = parser.parse_args()
    try:
        config_dir = Path(__file__).resolve().parent
        key = resolve(config_dir, Path.cwd().resolve(), os.environ)
        port = proxy_port(config_dir, args.session)
        request = make_request(args.bridge, args.subpath, args.session, json.loads(args.params), key, port)
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        if result.get('code') != 0:
            raise ScopeError('Bridge returned an application error')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except urllib.error.HTTPError as error:
        print(f'Bridge request rejected (HTTP {error.code}); no fallback credential used', file=sys.stderr)
    except (ScopeError, ValueError, OSError, KeyError, sqlite3.Error) as error:
        print(str(error) if isinstance(error, ScopeError) else 'Project bridge failed', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
