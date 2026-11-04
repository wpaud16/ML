"""취하 예측 백테스트 (2026-11-04, 서브 목표)

질문: 법원 기본 정보(청구금액·임의/강제·중복사건·접수 후 경과)를 더하면, 리치고 정보만 쓸 때보다
'이 사건이 매각되지 않고 취하될지'를 더 잘 맞히는가?

데이터: court_backfill (끝난 사건: 배당종결=매각 / 취하 / 기각 등) + richgo_detail.jsonl (감정가·지역·면적·권리 요약)
대상(y): 법원 종국결과가 '취하' (변형: 취하·기각·각하 = 매각 없이 끝남)
평가: 접수일 순서로 5구간 시간 순 검증(앞 구간으로 학습 → 다음 구간 예측), AUC 와 '위험 상위 10%' 적중
  python3 dev/withdraw_bt.py
"""
import sys, os, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CB = os.path.join(HERE, 'court_backfill')

RICHGO = ['l_appr', 'ot', 'seoul', 'gyeonggi', 'l_area', 'age', 'assume', 'tenant_n', 'uncertain_n',
          'br_mortgage', 'br_seizure', 'br_forced', 'base_age_y']
COURT = ['l_claim_appr', 'forced', 'dup', 'file_to_list_m']


def load():
    t = pd.DataFrame(json.load(open(os.path.join(CB, 'targets_all.json')))['items']).drop_duplicates('auction_id')
    det = {}
    for line in open(os.path.join(CB, 'richgo_detail.jsonl')):
        o = json.loads(line)
        if not o.get('error') and o.get('appraisedPrice'): det[o['auctionId']] = o
    rows = []
    for r in t.itertuples():
        f = os.path.join(CB, 'data', f'{r.case}_{int(r.item_no)}.json')
        if not os.path.exists(f) or r.auction_id not in det: continue
        ci = json.load(open(f)).get('case_info') or {}
        er = ci.get('end_result')
        if not er or er == '미종국': continue
        d = det[r.auction_id]; rg = d.get('rights') or {}; br = (rg.get('baseRight') or {})
        reg = pd.to_datetime(d.get('registrationDate'), errors='coerce')
        rec = pd.to_datetime(ci.get('received_date'), errors='coerce')
        bdt = pd.to_datetime((br.get('date') or '')[:10], errors='coerce')
        kind = ci.get('case_kind') or ''; bt = br.get('type') or ''
        appr = d['appraisedPrice']; claim = ci.get('claim_amount_manwon')
        age = d.get('constructYear')
        rows.append(dict(
            auction_id=r.auction_id, category=d.get('itemType') or r.category, end=er, received=rec,
            y=int(er == '취하'), y_void=int(er in ('취하', '기각', '각하', '기타')),
            l_appr=np.log(appr), ot=int((d.get('itemType') or r.category) == '오피스텔'),
            seoul=int(d.get('sd') == '서울'), gyeonggi=int(d.get('sd') == '경기'),
            l_area=np.log(d['buildingTotalArea']) if d.get('buildingTotalArea') else np.nan,
            age=(age - (2026 - reg.year)) if age is not None and pd.notna(reg) else np.nan,
            assume=int(bool(rg.get('hasAssumption'))) if rg.get('hasRegistryData') else np.nan,
            tenant_n=rg.get('assumedTenantCount'), uncertain_n=rg.get('uncertainTenantCount'),
            br_mortgage=int('저당' in bt), br_seizure=int('압류' in bt), br_forced=int('강제' in bt or '경매개시' in bt),
            base_age_y=((reg - bdt).days / 365.25) if pd.notna(reg) and pd.notna(bdt) else np.nan,
            claim=claim, l_claim_appr=np.log(claim * 1e4 / appr) if claim and claim > 0 else np.nan,
            forced=1.0 if '강제' in kind else 0.0 if '임의' in kind else np.nan,
            dup=float(bool(ci.get('duplicate_cases'))),
            file_to_list_m=((reg - rec).days / 30.4) if pd.notna(reg) and pd.notna(rec) else np.nan))
    df = pd.DataFrame(rows).sort_values('received').reset_index(drop=True)
    return df


def fit_pred(kind, cols, tr, te, target):
    Xtr, Xte = tr[cols], te[cols]
    med = Xtr.median(); Xtr, Xte = Xtr.fillna(med).fillna(0), Xte.fillna(med).fillna(0)
    if kind == 'gb':
        m = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.04, max_depth=3, min_samples_leaf=30,
                                           l2_regularization=2.0, random_state=0)
        return m.fit(Xtr, tr[target]).predict_proba(Xte)[:, 1]
    sc = StandardScaler().fit(Xtr)
    m = LogisticRegression(C=0.5, max_iter=2000)
    return m.fit(sc.transform(Xtr), tr[target]).predict_proba(sc.transform(Xte))[:, 1]


def time_cv(df, cols, target, kind, k=5):
    n = len(df); edges = [int(n * i / (k + 1)) for i in range(k + 2)]
    p = pd.Series(np.nan, index=df.index)
    for i in range(1, k + 1):
        tr = df.iloc[:edges[i]]; te = df.iloc[edges[i]:edges[i + 1]]
        if tr[target].sum() < 15: continue
        p[te.index] = fit_pred(kind, cols, tr, te, target)
    return p


def top_hit(y, p, q=0.10):
    m = p.notna(); y, p = y[m], p[m]
    cut = p.quantile(1 - q); sel = p >= cut
    return y[sel].mean() * 100, y[sel].sum() / max(y.sum(), 1) * 100


def main():
    df = load()
    print(f'끝난 사건 {len(df)}건 · 취하 {df.y.sum()}건 ({df.y.mean() * 100:.1f}%) · 매각 없이 종료 {df.y_void.sum()}건 · '
          f'접수 {df.received.min().date()} ~ {df.received.max().date()}')
    print('카테고리별 취하율', df.groupby('category').y.agg(['size', 'mean']).round(3).to_dict('index'))

    # 직관 표: 청구금액 ÷ 감정가 구간별 취하율
    b = pd.cut(np.exp(df.l_claim_appr), [0, .05, .1, .2, .4, .7, 1.0, 100], right=False)
    tb = df.groupby(b).agg(건수=('y', 'size'), 취하율=('y', 'mean'), 매각없이종료=('y_void', 'mean'))
    print('\n청구금액 ÷ 감정가 구간별'); print((tb.assign(취하율=tb.취하율 * 100, 매각없이종료=tb.매각없이종료 * 100)).round(1).to_string())
    for col, lab in (('forced', '강제(1)/임의(0)'), ('dup', '중복사건')):
        g = df.groupby(col).agg(건수=('y', 'size'), 취하율=('y', 'mean'))
        print(f'\n{lab}'); print((g.assign(취하율=g.취하율 * 100)).round(1).to_string())

    res = []
    for target, tl in (('y', '취하'), ('y_void', '매각 없이 종료')):
        for kind in ('gb', 'lr'):
            for lab, cols in (('리치고만', RICHGO), ('법원만', COURT), ('리치고+법원', RICHGO + COURT)):
                p = time_cv(df, cols, target, kind)
                m = p.notna()
                auc = roc_auc_score(df[target][m], p[m])
                prec, rec = top_hit(df[target], p)
                res.append(dict(대상=tl, 모델=kind, 정보=lab, AUC=round(auc, 3), 상위10_적중률=round(prec, 1),
                                상위10_포착률=round(rec, 1), 평가건수=int(m.sum())))
    r = pd.DataFrame(res)
    print('\n시간 순 검증 (앞 구간으로 학습 → 다음 구간 예측)'); print(r.to_string(index=False))

    # 해석용: 로지스틱 계수 (전체 학습, 표준화)
    cols = RICHGO + COURT; X = df[cols]; X = X.fillna(X.median()).fillna(0)
    lr = LogisticRegression(C=0.5, max_iter=2000).fit(StandardScaler().fit_transform(X), df.y)
    print('\n로지스틱 계수 (표준화, +면 취하 쪽)'); print(pd.Series(lr.coef_[0], index=cols).sort_values().round(2).to_string())
    df.to_csv(os.path.join(CB, 'withdraw_data.csv'), index=False); r.to_csv(os.path.join(CB, 'withdraw_bt_result.csv'), index=False)


if __name__ == '__main__':
    main()
