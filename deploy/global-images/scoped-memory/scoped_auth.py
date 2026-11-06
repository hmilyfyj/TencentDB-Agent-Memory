#!/usr/bin/env python3
"""Codex auth command for the private overlay experiment; stdout is the token only."""
import json
import os
from pathlib import Path
import sys

from scoped_memory import Store, context


def main():
    os.umask(0o077)
    home = Path(__file__).resolve().parent
    try:
        config_path = home / 'scope-config.json'
        if config_path.stat().st_mode & 0o077:
            raise ValueError('Private configuration required')
        config = json.loads(config_path.read_text())
        scope, source = context(config, Path.cwd().resolve(), os.environ)
        store = Store(home / 'overlay.sqlite')
        try:
            store.pin(source, scope)
        finally:
            store.db.close()
        routing = home.parent / 'project-routing'
        sys.path.insert(0, str(routing))
        from project_auth import resolve
        key = resolve(routing, Path.cwd().resolve(), os.environ)
        print(key)
        return 0
    except Exception:
        # Imported credential loaders and service errors must never echo their data.
        print('Private scoped authentication failed; no fallback credential used', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
