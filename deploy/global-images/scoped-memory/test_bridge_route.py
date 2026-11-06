import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class BridgeRouteTests(unittest.TestCase):
    def test_pinned_new_sessions_and_original_sessions_keep_their_own_proxy(self):
        spec = importlib.util.spec_from_file_location('trial_bridge', Path(__file__).with_name('project_bridge.py'))
        bridge = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, project_auth=SimpleNamespace(ScopeError=ValueError, resolve=None)):
            spec.loader.exec_module(bridge)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / 'project-routing'
            self.assertEqual(bridge.proxy_port(config_dir, 'old'), 8096)
            home = root / 'scoped-memory-1073-stage2'
            home.mkdir()
            with sqlite3.connect(home / 'overlay.sqlite') as db:
                db.execute('CREATE TABLE pins(source TEXT PRIMARY KEY,scope TEXT)')
                db.execute('INSERT INTO pins VALUES(?,?)', ('proxy:codex:new', 'daily'))
            self.assertEqual(bridge.proxy_port(config_dir, 'new'), 8097)
            self.assertEqual(bridge.proxy_port(config_dir, 'old'), 8096)
            request = bridge.make_request('memory', 'conversation/query', 'new', {}, 'fake-key', 8097)
            self.assertTrue(request.full_url.startswith('http://127.0.0.1:8097/'))
            self.assertEqual(request.get_header('X-tdai-user-key'), 'fake-key')
            with self.assertRaises(ValueError):
                bridge.make_request('skill', '../admin', 'new', {}, 'fake-key', 8097)
            with self.assertRaises(ValueError):
                bridge.make_request('memory', 'conversation/query', 'new\nspoof', {}, 'fake-key')


if __name__ == '__main__':
    unittest.main()
