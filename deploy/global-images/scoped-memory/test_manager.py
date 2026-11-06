import http.client
import json
from pathlib import Path
import re
import tempfile
from threading import Thread
import unittest

from manager import server
from scoped_memory import Store


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / 'scope-config.json').write_text(json.dumps({'projects': []}))
        self.store = Store(self.home / 'overlay.sqlite')
        self.addCleanup(self.store.db.close)
        self.candidate = self.store.write('daily', 'style', 'preference',
                                          'summary <script>private</script>', 'candidate', 'chat:test')
        self.httpd, self.password = server(self.home, 0)
        self.thread = Thread(target=self.httpd.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)
        self.origin = f'http://127.0.0.1:{self.httpd.server_port}'
        self.cookie = ''

    def stop(self):
        self.httpd.shutdown()
        self.thread.join(3)
        self.httpd.server_close()

    def request(self, path='/', data=None, headers=None):
        from urllib.parse import urlencode
        conn = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=3)
        self.addCleanup(conn.close)
        base = {'Origin': self.origin, 'Cookie': self.cookie}
        base.update(headers or {})
        conn.request('POST' if data is not None else 'GET', path,
                     urlencode(data) if data is not None else None, base)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode()

    def login(self):
        status, headers, _ = self.request('/login', {'password': self.password})
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        return self.request('/record?id=' + self.candidate['id'])[2]

    def test_auth_host_origin_and_csrf_boundaries(self):
        status, headers, _ = self.request()
        self.assertEqual(status, 401)
        self.assertEqual(headers['Referrer-Policy'], 'same-origin')
        for host in ['evil.example', f'localhost.evil.example:{self.httpd.server_port}', 'localhost:1']:
            self.assertEqual(self.request(headers={'Host': host})[0], 403)
        self.assertEqual(self.request('/login', {'password': 'bad'})[0], 401)
        self.assertEqual(self.request('/login', {'password': '错误密码'})[0], 401)
        for origin in ['https://evil.example', 'null', '']:
            self.assertEqual(self.request('/login', {'password': self.password}, {'Origin': origin})[0], 403)
        self.login()
        self.assertEqual(self.request('/action', {'csrf': 'bad'})[0], 403)
        self.assertEqual(self.request('/action', {'csrf': '错误令牌'})[0], 403)
        self.assertEqual(self.store.query(['public']), [])

    def test_localhost_native_review_requires_matching_origin(self):
        alias = {'Host': f'localhost:{self.httpd.server_port}',
                 'Origin': f'http://localhost:{self.httpd.server_port}'}
        self.assertEqual(self.request(headers=alias)[0], 401)
        self.assertEqual(self.request('/login', {'password': self.password},
                                      {**alias, 'Origin': self.origin})[0], 403)
        status, headers, _ = self.request('/login', {'password': self.password}, alias)
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        page = self.request('/record?id=' + self.candidate['id'], headers=alias)[2]
        csrf = re.search('name="csrf" value="([^"]+)"', page)[1]
        data = dict(csrf=csrf, id=self.candidate['id'], action='publish',
                    text='reviewed synthetic preference', confirmation='PUBLISH ' + self.candidate['id'])
        self.assertEqual(self.request('/action', data, {**alias, 'Origin': self.origin})[0], 403)
        self.assertEqual(self.store.query(['public']), [])
        self.assertEqual(self.request('/action', data, alias)[0], 200)
        self.assertEqual(self.store.query(['public'])[0]['text'], data['text'])

    def test_review_edit_publish_stale_reject_and_public_revocation(self):
        page = self.login()
        self.assertNotIn('<script>private</script>', page)
        self.assertIn('&lt;script&gt;', page)
        csrf = re.search('name="csrf" value="([^"]+)"', page)[1]
        data = {'csrf': csrf, 'id': self.candidate['id'], 'action': 'publish',
                'text': 'sanitized preference only', 'confirmation': 'wrong'}
        self.assertEqual(self.request('/action', data)[0], 409)
        data['confirmation'] = 'PUBLISH ' + self.candidate['id']
        self.assertEqual(self.request('/action', data)[0], 200)
        public = self.store.query(['public'])[0]
        self.assertEqual(public['text'], 'sanitized preference only')
        self.assertEqual(self.request('/action', data)[0], 409)
        data.update(id=public['id'], action='revoke', confirmation='REVOKE ' + public['id'])
        self.assertEqual(self.request('/action', data)[0], 200)
        self.assertEqual(self.store.query(['public']), [])

    def test_raw_and_foreign_candidates_cannot_publish(self):
        page = self.login()
        csrf = re.search('name="csrf" value="([^"]+)"', page)[1]
        raw = self.store.write('daily', 'raw', 'raw', 'private', 'confirmed', 'chat:test')
        foreign = self.store.write('project:unknown', 'candidate', 'skill', 'method', 'candidate', 'test')
        for record in [raw, foreign]:
            data = dict(csrf=csrf, id=record['id'], action='publish', text=record['text'],
                        confirmation='PUBLISH ' + record['id'])
            self.assertEqual(self.request('/action', data)[0], 409)
        self.assertEqual(self.store.query(['public']), [])


if __name__ == '__main__':
    unittest.main()
