"""구글 refresh token 발급 → C:\\auction_pc\\.env 의 GOOGLE_REFRESH_TOKEN 에 저장 (2026-11-08).
사용: .env 에 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 을 먼저 넣고
      python C:\\auction_pc\\ML\\local_runner\\google_auth.py
브라우저가 열리면 메일 보낼 구글 계정으로 로그인 → 허용. 토큰 값은 화면에 출력하지 않는다."""
import http.server, json, os, re, secrets, sys, threading, urllib.parse, urllib.request, webbrowser

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
SCOPES = ['https://www.googleapis.com/auth/gmail.send',            # 메일 발송
          'https://www.googleapis.com/auth/documents',             # 일정 문서 읽기·쓰기
          'https://www.googleapis.com/auth/spreadsheets.readonly', # 시트 읽기
          'https://www.googleapis.com/auth/drive.readonly']        # 문서 내보내기(트래커)


def read_env():
    d = {}
    for ln in open(ENV, encoding='utf-8-sig'):
        m = re.match(r'\s*([A-Z_]+)\s*=\s*(.*)$', ln)
        if m: d[m.group(1)] = m.group(2).strip()
    return d


def write_env(key, val):
    lines = open(ENV, encoding='utf-8-sig').read().splitlines()
    for i, ln in enumerate(lines):
        if re.match(rf'\s*{key}\s*=', ln):
            lines[i] = f'{key}={val}'; break
    else:
        lines.append(f'{key}={val}')
    open(ENV, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


def main():
    e = read_env()
    cid, csec = e.get('GOOGLE_CLIENT_ID'), e.get('GOOGLE_CLIENT_SECRET')
    if not cid or not csec:
        sys.exit(f'{ENV} 에 GOOGLE_CLIENT_ID 와 GOOGLE_CLIENT_SECRET 을 먼저 넣으세요.')
    got, state = {}, secrets.token_urlsafe(16)

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get('state', [''])[0] == state:
                got.update({k: v[0] for k, v in q.items()})
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers()
            ok = 'code' in got
            self.wfile.write(('<h2>' + ('완료 — 이 창은 닫아도 돼요' if ok else '실패: ' + got.get('error', '?')) + '</h2>').encode())
        def log_message(self, *a): pass

    srv = http.server.HTTPServer(('127.0.0.1', 0), H)
    redirect = f'http://127.0.0.1:{srv.server_port}'
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(dict(
        client_id=cid, redirect_uri=redirect, response_type='code', scope=' '.join(SCOPES),
        access_type='offline', prompt='consent', state=state))
    th = threading.Thread(target=srv.handle_request); th.start()
    print('브라우저에서 구글 로그인 → 허용을 눌러 주세요. (안 열리면 아래 주소를 복사해 여세요)\n' + url)
    webbrowser.open(url)
    th.join(timeout=600); srv.server_close()
    if 'code' not in got:
        sys.exit('승인 코드를 받지 못했어요: ' + got.get('error', '시간 초과') +
                 '\n(redirect_uri_mismatch 오류면 OAuth 클라이언트 유형이 "데스크톱 앱"이어야 해요)')
    body = urllib.parse.urlencode(dict(code=got['code'], client_id=cid, client_secret=csec,
                                       redirect_uri=redirect, grant_type='authorization_code')).encode()
    try:
        r = json.load(urllib.request.urlopen('https://oauth2.googleapis.com/token', body, timeout=30))
    except urllib.error.HTTPError as x:
        sys.exit('토큰 교환 실패: ' + x.read().decode()[:300])
    if not r.get('refresh_token'):
        sys.exit('refresh token 이 오지 않았어요. https://myaccount.google.com/permissions 에서 이 앱 권한을 지우고 다시 실행하세요.')
    write_env('GOOGLE_REFRESH_TOKEN', r['refresh_token'])
    print(f'저장 완료: {ENV} 의 GOOGLE_REFRESH_TOKEN (권한: {r.get("scope", "")})')


if __name__ == '__main__':
    main()
