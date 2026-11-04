"""구글 API 공통 (OAuth refresh token). 인증값은 환경변수(GitHub Secrets)에서만 읽는다."""
import json, os, base64, urllib.request, urllib.parse, urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header

_TOKEN = None


def _creds():
    p = os.environ.get('GOOGLE_CREDS_FILE')  # 로컬 테스트용
    if p:
        return json.load(open(p))
    return dict(client_id=os.environ['GOOGLE_CLIENT_ID'],
                client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
                refresh_token=os.environ['GOOGLE_REFRESH_TOKEN'])


def token():
    global _TOKEN
    if _TOKEN is None:
        c = _creds()
        d = urllib.parse.urlencode(dict(c, grant_type='refresh_token')).encode()
        _TOKEN = json.load(urllib.request.urlopen('https://oauth2.googleapis.com/token', d, timeout=30))['access_token']
    return _TOKEN


def call(url, body=None, method=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'),
                                 headers={'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'{e.code} {url}: {e.read().decode()[:500]}')
    return b.decode() if raw else json.loads(b or b'{}')


def sheet_values(sid, rng):
    return call(f'https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{urllib.parse.quote(rng)}').get('values', [])


def doc_get(did):
    return call(f'https://docs.googleapis.com/v1/documents/{did}')


def doc_update(did, requests, revision=None):
    body = {'requests': requests}
    if revision:
        body['writeControl'] = {'requiredRevisionId': revision}
    return call(f'https://docs.googleapis.com/v1/documents/{did}:batchUpdate', body)


def drive_export(fid, mime='text/markdown'):
    return call(f'https://www.googleapis.com/drive/v3/files/{fid}/export?mimeType={urllib.parse.quote(mime)}', raw=True)


def send_mail(to, subject, html, text):
    m = MIMEMultipart('alternative')
    m['To'] = to
    m['Subject'] = Header(subject, 'utf-8').encode()
    m.attach(MIMEText(text, 'plain', 'utf-8'))
    m.attach(MIMEText(html, 'html', 'utf-8'))
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
    return call('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', {'raw': raw})
