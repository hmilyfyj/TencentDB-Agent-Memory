#!/usr/bin/env python3
"""Owner-only local review UI. Launch from a human terminal outside an agent run."""
import argparse
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import parse_qs, urlencode, urlsplit

from scoped_memory import Denied, Store


def server(home, port=8126):
    config = json.loads((home / 'scope-config.json').read_text())
    scopes = ['public', 'daily', *('project:' + p for p in config['projects'])]
    password, session, csrf = (secrets.token_urlsafe(32) for _ in range(3))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No record text, passwords or cookies in access logs.

        def send(self, body, status=200, cookie=None):
            page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width"><title>私有记忆审核</title>'
                    '<style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem}'
                    'pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{width:95%;height:12rem}'
                    'input,select,button{font:inherit;margin:.4rem}article{border-top:1px solid #aaa;padding:1rem 0}'
                    '</style><h1>私有记忆审核</h1>' + body + '</html>').encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(page)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy',
                             "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            # Native form submissions need their same-origin Origin header.
            self.send_header('Referrer-Policy', 'same-origin')
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(page)

        def host_ok(self):
            return self.headers.get('Host') in (
                f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def authenticated(self):
            try:
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                return secrets.compare_digest(cookie['scoped_owner'].value.encode(), session.encode())
            except (KeyError, ValueError):
                return False

        def login(self):
            self.send('<p>在启动此服务的本机终端查看一次性密码。模型运行凭据不能登录。</p>'
                      '<form method="post" action="/login"><label>密码 <input type="password" '
                      'name="password" required autocomplete="off"></label><button>登录</button></form>', 401)

        def do_GET(self):
            if not self.host_ok():
                return self.send('Host rejected', 403)
            if not self.authenticated():
                return self.login()
            route = urlsplit(self.path)
            args = parse_qs(route.query)
            store = Store(home / 'overlay.sqlite')
            try:
                if route.path == '/record':
                    record = store.get(args.get('id', [''])[0])
                    if record['scope'] not in scopes:
                        raise Denied('Scope unavailable')
                    history = store.db.execute('SELECT * FROM records WHERE scope=? AND name=? '
                                               'ORDER BY revision DESC', (record['scope'], record['name'])).fetchall()
                    info = escape(json.dumps(dict(record), ensure_ascii=False, indent=2))
                    public = store.latest('public', record['name'])
                    extra = ('<p>同名公共记录：</p><pre>' + escape(json.dumps(public, ensure_ascii=False, indent=2)) + '</pre>') if public else ''
                    self.send('<a href="/">返回列表</a><pre>' + info + '</pre>' + extra +
                        '<p>发布会让此摘要在本人全部项目可见。请删去项目事实和私密原文；方法文档不会自动安装执行。</p>'
                        '<form method="post" action="/action">'
                        f'<input type="hidden" name="csrf" value="{csrf}">'
                        f'<input type="hidden" name="id" value="{escape(record["id"])}">'
                        '<label>摘要或更正内容<textarea name="text">' + escape(record['text']) + '</textarea></label>'
                        '<label>操作<select name="action"><option value="revise">更正</option>'
                        '<option value="revoke">撤销</option><option value="publish">发布公共候选</option></select></label>'
                        '<p>确认框填入：操作英文大写、空格、当前记录 ID（例如 PUBLISH ID）。旧版本操作会被拒绝。</p>'
                        '<label>确认<input name="confirmation" required size="55" autocomplete="off"></label>'
                        '<button>确认操作</button></form><h2>修订历史</h2><pre>' +
                        escape(json.dumps([dict(r) for r in history], ensure_ascii=False, indent=2)) + '</pre>')
                elif route.path == '/':
                    selected = args.get('scope', [''])[0]
                    if selected and selected not in scopes:
                        raise Denied('Scope unavailable')
                    rows = store.query([selected] if selected else scopes,
                                       args.get('q', [''])[0], all_states=True)
                    if args.get('state', [''])[0]:
                        rows = [r for r in rows if r['state'] == args['state'][0]]
                    form = '<form><label>搜索<input name="q"></label><label>范围<select name="scope"><option value="">全部本人范围</option>'
                    form += ''.join(f'<option>{escape(s)}</option>' for s in scopes)
                    form += '</select></label><label>状态<select name="state"><option value="">全部状态</option><option>candidate</option><option>confirmed</option><option>revoked</option></select></label><button>筛选</button></form>'
                    self.send('<p>公共仅限本人跨项目；默认查询不返回候选、旧版和已撤销记录。原文不代表已核实事实。</p>' + form +
                              f'<p>共 {len(rows)} 条，显示前 200 条；可按范围或关键词缩小。</p>' + ''.join(
                                  '<article><a href="/record?' + urlencode({'id': r['id']}) + '">' + escape(r['name']) +
                                  '</a><p>' + escape(f'{r["scope"]} · {r["kind"]} · {r["state"]} · r{r["revision"]} · {r["created_at"]}') +
                                  '</p><pre>' + escape(r['text'][:500]) + '</pre></article>' for r in rows[:200]))
                else:
                    self.send('Not found', 404)
            except Denied as error:
                self.send(escape(str(error)), 409)
            finally:
                store.db.close()

        def do_POST(self):
            origin = f'http://{self.headers.get("Host")}'
            if not self.host_ok() or self.headers.get('Origin') != origin:
                return self.send('Origin rejected', 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > 100000:
                    return self.send('Invalid body size', 413)
                data = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
                value = lambda name: data.get(name, [''])[0]
                if self.path == '/login':
                    if not secrets.compare_digest(value('password').encode(), password.encode()):
                        return self.login()
                    return self.send('<a href="/">打开记忆列表</a>', cookie=f'scoped_owner={session}; HttpOnly; SameSite=Strict; Path=/')
                if self.path != '/action' or not self.authenticated() or not secrets.compare_digest(value('csrf').encode(), csrf.encode()):
                    return self.send('Access rejected', 403)
                store = Store(home / 'overlay.sqlite')
                try:
                    record = store.get(value('id'))
                    action = value('action')
                    if (record['scope'] not in scopes or action not in ('publish', 'revise', 'revoke') or
                            value('confirmation') != action.upper() + ' ' + record['id']):
                        raise Denied('Scope or exact confirmation rejected')
                    if action == 'publish':
                        store.publish(record, value('text'))
                    else:
                        if record['state'] == 'published':
                            raise Denied('Consumed candidate cannot be changed; edit its public record')
                        store.write(record['scope'], record['name'], record['kind'],
                                    record['text'] if action == 'revoke' else value('text'),
                                    'revoked' if action == 'revoke' else record['state'],
                                    'human-reviewed:' + record['id'], record['id'])
                finally:
                    store.db.close()
                self.send('<p>操作已保存。</p><a href="/">返回列表</a>')
            except (Denied, ValueError, UnicodeError) as error:
                self.send(escape(str(error)), 409)

    return HTTPServer(('127.0.0.1', port), Handler), password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8126)
    args = parser.parse_args()
    if os.environ.get('MULTICA_TOKEN') or not sys.stdin.isatty():
        raise SystemExit('Start management from the owner terminal outside a Multica run')
    home = Path(__file__).resolve().parent
    if home.stat().st_mode & 0o077 or (home / 'scope-config.json').stat().st_mode & 0o077:
        raise SystemExit('Management directory/config must be private (0700/0600)')
    httpd, password = server(home, args.port)
    print(f'管理入口：http://127.0.0.1:{httpd.server_port}/\n本次密码：{password}\nCtrl+C 停止；密码只在本次运行有效。', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
