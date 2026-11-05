"""구글드라이브 '경제/Steward' 폴더에 브리핑 시스템 파일·매뉴얼 올리기 (2026-11-05 사용자 요청).
같은 이름 파일이 있으면 내용만 갱신(링크 유지). GitHub Actions steward_sync.yml 에서 실행 (구글 인증 = Secrets)."""
import os, sys, glob, json, uuid, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import google_api as g

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEWARD = '11GxjJi_52o__L9ebgY9VFethEgZy0nuo'   # 내 드라이브 …/경제/Steward
GROUPS = {'': ['STEWARD.md', 'HANDOFF.md'],
          'brief': ['brief/*.py'], 'outfit': ['outfit/*.py'],
          'auction_model': ['auction_model/*.py', 'auction_model/auction_config.json', 'auction_model/README.md'],
          'workflows': ['.github/workflows/*.yml']}
API = 'https://www.googleapis.com/drive/v3/files'


def find(name, parent, folder=False):
    q = f"name = '{name}' and '{parent}' in parents and trashed = false" + (" and mimeType = 'application/vnd.google-apps.folder'" if folder else '')
    r = g.call(API + '?' + urllib.parse.urlencode(dict(q=q, fields='files(id,name)')))
    return (r.get('files') or [None])[0]


def folder(name, parent):
    f = find(name, parent, True)
    return f['id'] if f else g.call(API, dict(name=name, mimeType='application/vnd.google-apps.folder', parents=[parent]))['id']


def upload(path, parent):
    name = os.path.basename(path); data = open(path, 'rb').read()
    mime = 'text/markdown' if name.endswith('.md') else ('application/json' if name.endswith('.json') else 'text/plain')
    ex = find(name, parent)
    meta = {'name': name} if ex else {'name': name, 'parents': [parent]}
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n'
            f'--{b}\r\nContent-Type: {mime}; charset=UTF-8\r\n\r\n').encode() + data + f'\r\n--{b}--'.encode()
    url = ('https://www.googleapis.com/upload/drive/v3/files' + (f'/{ex["id"]}' if ex else '') + '?uploadType=multipart&fields=id,name')
    req = urllib.request.Request(url, data=body, method='PATCH' if ex else 'POST',
                                 headers={'Authorization': 'Bearer ' + g.token(), 'Content-Type': f'multipart/related; boundary={b}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), bool(ex)


if __name__ == '__main__':
    n = 0
    for sub, pats in GROUPS.items():
        parent = folder(sub, STEWARD) if sub else STEWARD
        for pat in pats:
            for p in sorted(glob.glob(os.path.join(ROOT, pat))):
                r, upd = upload(p, parent); n += 1
                print(('갱신' if upd else '추가'), (sub + '/' if sub else '') + r['name'])
    print('완료', n, '개')
