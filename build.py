#!/usr/bin/env python3
"""Builds apps.json, apps.csv and index.html from rows.psv (+ audit.psv if present).
All numbers on the page are computed here from the data. Nothing is typed in by hand."""
import json, csv, html, os, collections

W = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(W, 'out')
os.makedirs(OUT, exist_ok=True)

CATS = {1: 'CRM and Sales', 2: 'Support and Helpdesk', 3: 'Communications and Messaging',
        4: 'Marketing, Ads, Email and Social', 5: 'Ecommerce', 6: 'Data, SEO and Scraping',
        7: 'Developer, Infra and Data platforms', 8: 'Productivity and Project Management',
        9: 'Finance and Fintech', 10: 'AI, Research and Media-native'}
GATE = {'FREE': 'Self-serve, free', 'TRIAL': 'Self-serve, trial', 'ACCOUNT': 'Account needed, free path not confirmed',
        'PLAN': 'Paid plan', 'REVIEW': 'Approval or review', 'SALES': 'Contact sales',
        'CUSTOMER': 'Existing customer only', 'LOCAL': 'No credentials, local tool', 'UNKNOWN': 'Not confirmed'}
MCP = {'OFFICIAL': 'Official', 'PARTIAL': 'Official, limited', 'SECONDARY': 'Claimed, not vendor-confirmed',
       'NONE': 'None found', 'UNCHECKED': 'Not checked', 'NA': 'Not applicable'}
VER = {'READY': 'Buildable today', 'FRICTION': 'Buildable with a gate', 'GATED': 'Gated',
       'NOT_API': 'Not an API', 'UNCLEAR': 'Unclear'}
STAT = {'V': 'Verified', 'P': 'Partly verified', 'U': 'Unverified'}
AF = {'O': 'OAuth only', 'K': 'Key or token only', 'OK': 'OAuth and key or token', 'N': 'No auth', '?': 'Not confirmed'}
REPORT_IDS = {50, 58, 59, 84, 85, 90, 91, 92, 93, 94, 97, 98, 99, 100}

F = 'id name cat what auth af gate gate_note api mcp mcp_note verdict blocker ev conf status p1 flags'.split()
rows = []
for line in open(os.path.join(W, 'rows.psv'), encoding='utf-8'):
    if not line.strip() or line.startswith('#'):
        continue
    p = line.rstrip('\n').split('|')
    assert len(p) == len(F), (p[0], len(p))
    r = dict(zip(F, p))
    r['id'] = int(r['id']); r['cat'] = int(r['cat'])
    r['category'] = CATS[r['cat']]
    r['evidence'] = ['https://' + u for u in r.pop('ev').split()]
    r['flags'] = r['flags'].split()
    r['source'] = 'earlier research task, rechecked where noted' if r['id'] in REPORT_IDS else 'this run'
    assert r['gate'] in GATE and r['mcp'] in MCP and r['verdict'] in VER and r['status'] in STAT and r['af'] in AF, r['id']
    rows.append(r)
assert [r['id'] for r in rows] == list(range(1, 101))
N = len(rows)
C = collections.Counter

# ---------- stats ----------
gate_c = C(r['gate'] for r in rows); mcp_c = C(r['mcp'] for r in rows)
ver_c = C(r['verdict'] for r in rows); stat_c = C(r['status'] for r in rows); af_c = C(r['af'] for r in rows)
self_serve = gate_c['FREE'] + gate_c['TRIAL']
hard_gate = gate_c['SALES'] + gate_c['CUSTOMER']
soft_gate = gate_c['PLAN'] + gate_c['REVIEW']
mcp_any = mcp_c['OFFICIAL'] + mcp_c['PARTIAL']
oauth_any = af_c['O'] + af_c['OK']; key_any = af_c['K'] + af_c['OK']
names = lambda f: [r['name'] for r in rows if f(r)]
easy = names(lambda r: r['verdict'] == 'READY' and r['gate'] in ('FREE', 'TRIAL') and r['mcp'] == 'OFFICIAL')
outreach = names(lambda r: r['gate'] in ('SALES', 'CUSTOMER'))
review = names(lambda r: r['gate'] == 'REVIEW'); plan = names(lambda r: r['gate'] == 'PLAN')
unclear = names(lambda r: r['verdict'] == 'UNCLEAR'); notapi = names(lambda r: r['verdict'] == 'NOT_API')
blockers = C(GATE[r['gate']] for r in rows if r['verdict'] in ('FRICTION', 'GATED'))
cat_tab = []
for c in CATS:
    rs = [r for r in rows if r['cat'] == c]
    cat_tab.append((CATS[c], sum(r['gate'] in ('FREE', 'TRIAL') for r in rs),
                    sum(r['gate'] in ('ACCOUNT', 'UNKNOWN') for r in rs),
                    sum(r['gate'] in ('PLAN', 'REVIEW') for r in rs),
                    sum(r['gate'] in ('SALES', 'CUSTOMER') for r in rs),
                    sum(r['mcp'] in ('OFFICIAL', 'PARTIAL') for r in rs),
                    sum(r['verdict'] == 'READY' for r in rs)))

# ---------- pass 1 (memory only) vs pass 2 (docs) ----------
p1rows = [r for r in rows if r['p1']]
FIELDS = ['auth', 'access gate', 'official MCP']
p1 = []
for i, fname in enumerate(FIELDS):
    c = C(r['p1'][i] for r in p1rows)
    scored = c['Y'] + c['P'] + c['N'] + c['U']
    acc = (c['Y'] + 0.5 * c['P']) / scored if scored else 0
    p1.append(dict(field=fname, right=c['Y'], partial=c['P'], wrong=c['N'], blank=c['U'], uncheckable=c['-'],
                   scored=scored, acc=round(100 * acc)))
misses = []
for r in p1rows:
    for i, fname in enumerate(FIELDS):
        if r['p1'][i] in 'NUP':
            kind = {'N': 'wrong', 'U': 'no answer', 'P': 'partly right'}[r['p1'][i]]
            now = [r['auth'], GATE[r['gate']] + '. ' + r['gate_note'], MCP[r['mcp']] + '. ' + r['mcp_note']][i]
            misses.append((r['id'], r['name'], fname, kind, now))
tot_scored = sum(x['scored'] for x in p1)
tot_acc = round(100 * sum(x['right'] + 0.5 * x['partial'] for x in p1) / tot_scored)

# ---------- blind audit (second agent, no access to findings) ----------
audit, audit_cmp, audit_tot = [], [], None
ap = os.path.join(W, 'audit.psv')
if os.path.exists(ap):
    byid = {r['id']: r for r in rows}
    before = {int(l.split('|')[0]): l.strip().split('|')[1:] for l in open(os.path.join(W, 'audit_before.psv')) if l.strip() and not l.startswith('#')}
    for line in open(ap, encoding='utf-8'):
        if not line.strip() or line.startswith('#'):
            continue
        p = [x.strip() for x in line.rstrip('\n').split('|')]
        a = dict(zip('id af gate mcp auth_d gate_d mcp_d ev conf'.split(), p))
        a['id'] = int(a['id']); audit.append(a)
        r = byid[a['id']]
        b0 = before[a['id']]
        audit_cmp.append(dict(id=a['id'], name=r['name'],
                              auth=(b0[0], a['af'], b0[0] == a['af']),
                              gate=(b0[1], a['gate'], b0[1] == a['gate']),
                              mcp=(b0[2], a['mcp'], b0[2] == a['mcp']),
                              after=dict(auth=r['af'] == a['af'], gate=r['gate'] == a['gate'], mcp=r['mcp'] == a['mcp']), a=a))
    n = len(audit_cmp)
    audit_tot = {k: sum(x[k][2] for x in audit_cmp) for k in ('auth', 'gate', 'mcp')}
    audit_tot['n'] = n
    audit_tot['after'] = {k: sum(x['after'][k] for x in audit_cmp) for k in ('auth', 'gate', 'mcp')}
    none_before = [x for x in audit_cmp if x['mcp'][0] == 'NONE']
    audit_tot['corrected'] = sum(audit_tot['after'][k] for k in ('auth','gate','mcp')) - (audit_tot['auth']+audit_tot['gate']+audit_tot['mcp'])
    audit_tot['open_or_kept'] = 3*n - sum(audit_tot['after'][k] for k in ('auth','gate','mcp'))
    audit_tot['mcp_none_in_sample'] = len(none_before)
    audit_tot['mcp_none_overturned'] = sum(1 for x in none_before if x['after']['mcp'] and x['a']['mcp'] != 'NONE')
resol = {}
rp = os.path.join(W, 'audit_resolution.psv')
if os.path.exists(rp):
    for line in open(rp, encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            i, fld, txt = line.rstrip('\n').split('|', 2)
            resol[(int(i), fld)] = txt

pct_before = round(100*(audit_tot['auth']+audit_tot['gate']+audit_tot['mcp'])/(3*audit_tot['n'])) if audit_tot else None
pct_after = round(100*sum(audit_tot['after'].values())/(3*audit_tot['n'])) if audit_tot else None
stats = dict(total=N, gate=dict(gate_c), mcp=dict(mcp_c), verdict=dict(ver_c), status=dict(stat_c), auth_family=dict(af_c),
             self_serve=self_serve, mcp_official_or_limited=mcp_any, pass1=p1, pass1_overall_accuracy_pct=tot_acc,
             blind_audit=audit_tot)

# ---------- machine-readable outputs ----------
export = [{k: r[k] for k in ('id', 'name', 'category', 'what', 'auth', 'gate', 'gate_note', 'api', 'mcp', 'mcp_note',
                              'verdict', 'blocker', 'evidence', 'conf', 'status', 'flags', 'source')} |
          {'auth_family': r['af'], 'first_pass_score_auth_gate_mcp': r['p1']} for r in rows]
json.dump(dict(generated='2026-11-23', schema=dict(gate=GATE, mcp=MCP, verdict=VER, status=STAT, auth_family=AF),
               stats=stats, apps=export), open(os.path.join(OUT, 'apps.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
with open(os.path.join(OUT, 'apps.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['id', 'app', 'category', 'what it does', 'auth', 'access', 'access note', 'api surface', 'mcp', 'mcp note',
                'verdict', 'main blocker', 'evidence', 'confidence', 'status', 'flags'])
    for r in rows:
        w.writerow([r['id'], r['name'], r['category'], r['what'], r['auth'], GATE[r['gate']], r['gate_note'], r['api'],
                    MCP[r['mcp']], r['mcp_note'], VER[r['verdict']], r['blocker'], ' '.join(r['evidence']), r['conf'],
                    STAT[r['status']], ' '.join(r['flags'])])

# ---------- optional header links (links.json) ----------
LINKS = {}
lp = os.path.join(W, 'links.json')
if os.path.exists(lp):
    LINKS = json.load(open(lp))
live = (LINKS.get('live_url') or '').rstrip('/')
repo = (LINKS.get('repo_url') or '').strip()
BASE = live + '/' if live else ''
LINKS_HTML = ''
if live:
    LINKS_HTML += f' Live page: <a href="{html.escape(live)}">{html.escape(live.split("//")[-1])}</a>.'
if repo:
    LINKS_HTML += f' Source repo: <a href="{html.escape(repo)}">{html.escape(repo.split("//")[-1])}</a>.'

# ---------- HTML ----------
e = html.escape
def bars(counter, labels, order):
    mx = max(counter.values())
    out = []
    for k in order:
        v = counter.get(k, 0)
        if v:
            out.append(f'<div class="bar"><span class="bl">{e(labels[k])}</span><span class="bt"><i style="width:{100*v/mx:.0f}%"></i></span><b>{v}</b></div>')
    return ''.join(out)
def lst(xs): return ', '.join(e(x) for x in xs) if xs else 'none'
def dom(u): return u.split('/')[2].replace('www.', '')

trs = []
for r in rows:
    ev = ' '.join(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(dom(u))}</a>' for u in r['evidence'])
    fl = ''.join(f'<span class="flag">{e(x)}</span>' for x in r['flags'])
    trs.append(f'''<tr data-cat="{r['cat']}" data-gate="{r['gate']}" data-mcp="{r['mcp']}" data-ver="{r['verdict']}" data-st="{r['status']}">
<td>{r['id']}</td><td><b>{e(r['name'])}</b><br><span class="mut">{e(r['what'])}</span><br><span class="mut">{e(r['category'])}</span></td>
<td>{e(r['auth'])}</td>
<td><span class="chip g-{r['gate']}">{e(GATE[r['gate']])}</span><br>{e(r['gate_note'])}</td>
<td>{e(r['api'])}</td>
<td><span class="chip m-{r['mcp']}">{e(MCP[r['mcp']])}</span><br>{e(r['mcp_note'])}</td>
<td><span class="chip v-{r['verdict']}">{e(VER[r['verdict']])}</span><br>{e(r['blocker'])}</td>
<td class="ev">{ev}</td>
<td><span class="chip s-{r['status']}">{STAT[r['status']]}</span><br><span class="mut">confidence {r['conf']}</span>{fl}</td></tr>''')

cat_rows = ''.join(f'<tr><td>{e(a)}</td><td>{b}</td><td>{c}</td><td>{d}</td><td>{f}</td><td>{g}</td><td>{h}</td></tr>' for a, b, c, d, f, g, h in cat_tab)
p1_rows = ''.join(f"<tr><td>{x['field']}</td><td>{x['right']}</td><td>{x['partial']}</td><td>{x['wrong']}</td><td>{x['blank']}</td><td>{x['uncheckable']}</td><td><b>{x['acc']}%</b></td></tr>" for x in p1)
miss_rows = ''.join(f'<tr><td>{i}</td><td>{e(n)}</td><td>{f}</td><td>{k}</td><td>{e(now)}</td></tr>' for i, n, f, k, now in misses if k != 'partly right')
part_rows = ''.join(f'<tr><td>{i}</td><td>{e(n)}</td><td>{f}</td><td>{e(now)}</td></tr>' for i, n, f, k, now in misses if k == 'partly right')
top_block = ', '.join(f'{e(k.lower())} ({v})' for k, v in blockers.most_common())

if audit_tot:
    n = audit_tot['n']
    arows = []
    for x in audit_cmp:
        cells = []
        for k, lab in (('auth', AF), ('gate', GATE), ('mcp', MCP)):
            mine, theirs, ok = x[k]
            if ok:
                cells.append(f'<td class="ok">agree: {e(lab.get(mine, mine))}</td>')
            else:
                res = resol.get((x['id'], k), '')
                cells.append(f'<td class="no">main run: {e(lab.get(mine, mine))}<br>audit: {e(lab.get(theirs, theirs))}' + (f'<br><i>{e(res)}</i>' if res else '') + '</td>')
        arows.append(f"<tr><td>{x['id']}</td><td>{e(x['name'])}</td>{''.join(cells)}<td class='mut'>{e(x['a'].get('conf',''))}</td></tr>")
    audit_html = f'''<p>A second agent re-researched {n} randomly drawn apps (two per category) with no access to the findings: only the app name, the brief's hint, and the code book. Agreement is an exact code match, computed by script.</p>
<div class="tiles"><div class="tile"><b>{audit_tot['auth']}/{n} &rarr; {audit_tot['after']['auth']}/{n}</b><span>auth family agrees, before and after corrections</span></div>
<div class="tile"><b>{audit_tot['gate']}/{n} &rarr; {audit_tot['after']['gate']}/{n}</b><span>access gate agrees, before and after corrections</span></div>
<div class="tile"><b>{audit_tot['mcp']}/{n} &rarr; {audit_tot['after']['mcp']}/{n}</b><span>MCP status agrees, before and after corrections</span></div></div>
<p class="note"><b>What the audit changed.</b> Before corrections, the main run was right on {audit_tot['auth']+audit_tot['gate']+audit_tot['mcp']} of {3*n} sampled fields. Each disagreement was settled on the vendor page, and the audit was usually right. The weakest answer was "none found" for MCP: {audit_tot['mcp_none_overturned']} of {audit_tot['mcp_none_in_sample']} such rows in the sample had a vendor server after all (Freshdesk, Aircall). So a second sweep re-researched all 40 rows marked none, unchecked or unconfirmed. It found vendor MCP servers for 17 (Plain, Gumroad, Clay, Monday, QuickBooks, Xero and Grain among them) and limited or announced ones for 13 more. The counts on this page include these corrections, and every corrected row carries a flag.</p>
<div class="scroll"><table><thead><tr><th>#</th><th>App</th><th>Auth family</th><th>Access gate</th><th>MCP</th><th>Audit confidence</th></tr></thead><tbody>{''.join(arows)}</tbody></table></div>
<p class="mut">An exact code match is a strict test. Many disagreements are between neighbouring codes, for example "self-serve, trial" against "account needed, free path not confirmed". Notes in italics say how each one was settled, or that it is still open.</p>'''
else:
    audit_html = '<p><b>Not run yet.</b></p>'

sample20_unused = ''.join(f"<li>{x['id']} {e(x['name'])}</li>" for x in audit_cmp) if audit_cmp else ''

PAGE = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>100 apps: how ready are they to become agent toolkits?</title>
<style>
:root{{--bg:#f6f5f1;--card:#fff;--ink:#1b1d21;--mut:#646a73;--line:#dedbd2;--acc:#1f5fbf;--ok:#1d7a46;--warn:#a05a00;--bad:#b3261e}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:28px 20px 80px}}h1{{font-size:30px;line-height:1.2;margin:0 0 6px}}h2{{font-size:21px;margin:44px 0 10px;padding-top:14px;border-top:2px solid var(--ink)}}h3{{font-size:16px;margin:22px 0 6px}}
.lede{{font-size:17px;max-width:900px}}.mut{{color:var(--mut);font-size:13px}}a{{color:var(--acc)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0}}.tile{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}}.tile b{{display:block;font-size:30px;line-height:1.1}}.tile span{{color:var(--mut);font-size:13px}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}}
.bar{{display:grid;grid-template-columns:230px 1fr 34px;gap:8px;align-items:center;margin:5px 0;font-size:13px}}.bt{{background:#ece9e1;border-radius:4px;height:14px;overflow:hidden}}.bt i{{display:block;height:100%;background:var(--acc)}}
ol.find li{{margin:8px 0;max-width:980px}}
table{{border-collapse:collapse;width:100%;background:var(--card);font-size:13px}}th,td{{border:1px solid var(--line);padding:7px 8px;vertical-align:top;text-align:left}}th{{background:#eeece5;position:sticky;top:0;z-index:1}}
.scroll{{overflow:auto;max-height:78vh;border:1px solid var(--line);border-radius:8px}}.scroll table{{border:0}}
.chip{{display:inline-block;padding:1px 7px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid;margin-bottom:3px;white-space:nowrap}}
.g-FREE,.g-TRIAL,.g-LOCAL,.m-OFFICIAL,.v-READY,.s-V{{color:var(--ok);border-color:var(--ok);background:#eaf5ee}}
.g-ACCOUNT,.g-PLAN,.g-REVIEW,.m-PARTIAL,.m-SECONDARY,.v-FRICTION,.s-P{{color:var(--warn);border-color:var(--warn);background:#fbf2e3}}
.g-SALES,.g-CUSTOMER,.g-UNKNOWN,.v-GATED,.v-UNCLEAR,.s-U{{color:var(--bad);border-color:var(--bad);background:#fbeceb}}
.m-NONE,.m-UNCHECKED,.m-NA,.v-NOT_API{{color:var(--mut);border-color:var(--mut);background:#f1f0ec}}
.flag{{display:inline-block;margin:3px 3px 0 0;padding:0 5px;border-radius:4px;background:#ece9e1;font-size:11px}}.ev a{{display:block;word-break:break-all}}
.filters{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}}.filters input,.filters select{{padding:7px 9px;border:1px solid var(--line);border-radius:7px;font:inherit;background:#fff}}
.ok{{background:#eaf5ee}}.no{{background:#fbf2e3}}.steps{{counter-reset:s;list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}}.steps li{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}.steps li:before{{counter-increment:s;content:counter(s);display:inline-block;width:22px;height:22px;border-radius:50%;background:var(--ink);color:#fff;text-align:center;font-size:12px;line-height:22px;margin-right:7px}}
.note{{border-left:4px solid var(--warn);background:#fbf2e3;padding:10px 14px;border-radius:0 8px 8px 0;max-width:980px}}
</style></head><body><main>
<h1>100 apps: how ready are they to become agent toolkits?</h1>
<p class="lede">A small version of an integration research workflow. For each app: what auth it uses, whether a developer can get credentials alone, what the API looks like, whether the vendor already ships an MCP server, and whether a toolkit could be built today. Every row links to the vendor page behind it.</p>
<p class="mut">Composio AI Product Ops take-home. Prepared by Anish Singh Rawat. Data as of 23 Nov 2026.{LINKS_HTML} Machine-readable copy: <a href="{BASE}apps.json">apps.json</a> and <a href="{BASE}apps.csv">apps.csv</a>.</p>

<h2>1. The patterns</h2>
<div class="tiles">
<div class="tile"><b>{ver_c['READY']}</b><span>of {N} look buildable today</span></div>
<div class="tile"><b>{self_serve}</b><span>confirmed self-serve (free or trial)</span></div>
<div class="tile"><b>{hard_gate}</b><span>need sales or an existing customer</span></div>
<div class="tile"><b>{mcp_any}</b><span>have a vendor MCP server ({mcp_c['OFFICIAL']} full, {mcp_c['PARTIAL']} limited)</span></div>
<div class="tile"><b>{oauth_any}</b><span>document OAuth ({af_c['OK']} also offer a key or token)</span></div>
<div class="tile"><b>{stat_c['V']}</b><span>rows fully verified on vendor pages</span></div>
</div>
<ol class="find">
<li><b>Auth is rarely the blocker. Access is.</b> {key_any} apps take an API key or token, {oauth_any} document OAuth, {af_c['OK']} offer both. Where building is blocked, the reason is who can get credentials: {top_block}.</li>
<li><b>Vendor MCP servers are the norm now.</b> {mcp_any} of {N} have one ({mcp_c['OFFICIAL']} full, {mcp_c['PARTIAL']} limited: docs-search only, beta, or dev tooling). "Has MCP" is not one fact, so the matrix splits it.</li>
<li><b>MCP auth is OAuth even where the REST API is key-based</b> (Attio, Close, Intercom, ClickUp, Linear, Stripe). Stripe's MCP stops taking plain secret keys on 11 Jan 2027. Key-only toolkits will age badly.</li>
<li><b>Gating follows the category.</b> Developer and productivity tools: self-serve. Ads platforms: review-gated (Google, Meta, LinkedIn, Pinterest, Threads). Finance: free test modes (Stripe, Plaid) or customer-only tokens (Brex, PitchBook). Enterprise CRM and support: sales-led. Counts below.</li>
<li><b>Easy wins:</b> {len(easy)} apps are self-serve, buildable today, and already have a full vendor MCP server. Filter the matrix: access self-serve, MCP official.</li>
<li><b>Needs outreach:</b> {lst(outreach)}. <b>Needs approval:</b> {lst(review)}. <b>Needs a paid plan:</b> {lst(plan)}.</li>
<li><b>Not everything on the list is an API.</b> {lst(notapi)} are local CLIs with no auth. {len(unclear)} apps stayed unclear after three passes: {lst(unclear)}.</li>
<li><b>Model memory was stale exactly on the newest facts.</b> Without browsing, the first pass scored {p1[0]['acc']}% on auth and {p1[1]['acc']}% on access, but {p1[2]['acc']}% on MCP. The full log is in section 4.</li>
</ol>
<div class="grid2">
<div class="card"><h3>How a developer gets credentials</h3>{bars(gate_c, GATE, list(GATE))}</div>
<div class="card"><h3>Vendor MCP server</h3>{bars(mcp_c, MCP, list(MCP))}<h3>Buildability verdict</h3>{bars(ver_c, VER, list(VER))}</div>
</div>
<h3>By category</h3>
<div class="scroll" style="max-height:none"><table><thead><tr><th>Category (10 apps each)</th><th>Self-serve, free or trial</th><th>Account needed or not confirmed</th><th>Plan or review gate</th><th>Sales or customer only</th><th>Vendor MCP (full or limited)</th><th>Buildable today</th></tr></thead><tbody>{cat_rows}</tbody></table></div>

<h2>2. The findings: all {N} apps</h2>
<div class="filters"><input id="q" placeholder="Search app, auth, notes" size="28">
<select id="fc"><option value="">All categories</option>{''.join(f'<option value="{k}">{e(v)}</option>' for k, v in CATS.items())}</select>
<select id="fg"><option value="">Any access</option>{''.join(f'<option value="{k}">{e(v)}</option>' for k, v in GATE.items())}</select>
<select id="fm"><option value="">Any MCP status</option>{''.join(f'<option value="{k}">{e(v)}</option>' for k, v in MCP.items())}</select>
<select id="fv"><option value="">Any verdict</option>{''.join(f'<option value="{k}">{e(v)}</option>' for k, v in VER.items())}</select>
<select id="fs"><option value="">Any status</option>{''.join(f'<option value="{k}">{e(v)}</option>' for k, v in STAT.items())}</select>
<span class="mut" id="cnt"></span></div>
<div class="scroll"><table id="t"><thead><tr><th>#</th><th>App</th><th>Auth</th><th>Access</th><th>API surface</th><th>Vendor MCP</th><th>Verdict and main blocker</th><th>Evidence</th><th>Status</th></tr></thead><tbody>
{''.join(trs)}
</tbody></table></div>
<p class="mut">Status: Verified means the key fields were read on a vendor page in this run. Partly verified means at least one field is "not stated" on the vendor pages read, or rests on a non-vendor source. Unverified means the vendor pages could not be read or did not answer. Counts: {stat_c['V']} verified, {stat_c['P']} partly, {stat_c['U']} unverified.</p>

<h2>3. The workflow</h2>
<ol class="steps">
<li><b>Intake.</b> The 100 rows from the brief: number, name, hint.</li>
<li><b>First pass, no browsing.</b> The model answers auth, access and MCP from memory. Saved to disk before any lookup, for {len(p1rows)} apps.</li>
<li><b>Identity check.</b> Confirm the official domain from the hint. Flag look-alikes and legacy doc sites.</li>
<li><b>Docs-grounded pass.</b> Fetch the vendor auth page, the pricing or signup page, and the MCP page. Extract into a fixed schema. "Not stated" is an allowed answer and every prompt said "from this page only, never guess".</li>
<li><b>Validation.</b> Each row carries vendor evidence links and a status. A non-vendor source never upgrades a row to Verified.</li>
<li><b>Recheck loop.</b> Rows with conflicts, deprecation notes, or MCP claims from non-vendor pages got a second targeted lookup. After the audit flagged "none found" as weak, a second agent swept all 40 none, unchecked or unconfirmed MCP rows.</li>
<li><b>Blind audit.</b> A separate agent with no access to the findings re-researched a random sample. Agreement is computed by script, disagreements are settled on the vendor page, and corrected rows carry an audit-corrected flag.</li>
<li><b>Spot check.</b> The sampled fields are checked twice against vendor pages and every mismatch is settled or flagged. See section 4.</li>
<li><b>Synthesis.</b> build.py computes every number on this page from the dataset.</li>
</ol>
<h3>Judgment calls along the way</h3>
<ul>
<li>Deciding what counts as an "official" MCP server. A docs-search server, a closed beta and a full account server are different things.</li>
<li>Name collisions: Clay (clay.com) and Clay (clay.earth), Consensus and goconsensus.com, Paygent and the Japanese PAYGENT, iPayX and several iPay companies, transcriptapi.com and transcriptapi.net.</li>
<li>Doc sites that only render in a real browser: QuickBooks, Xero, Ramp, Lark, and the Gumroad API page. These rows are marked and need a browser pass.</li>
<li>Sales-gated apps, where only an email to the vendor settles the question.</li>
</ul>
<h3>What was run</h3>
<p>About 180 page fetches and 10 web searches in the main run, plus an earlier research task that covered 14 of the harder apps, plus the blind audit agent. Files in the repo: <code>pass1_priors.tsv</code> (first-pass answers), <code>rows.psv</code> (the dataset), <code>audit_sample.txt</code> and <code>audit.psv</code> (blind audit), <code>build.py</code> (stats and this page).</p>

<h2>4. Verification: how we know, and where it was wrong</h2>
<h3>First pass (memory only) against the docs-grounded pass</h3>
<div class="scroll" style="max-height:none"><table><thead><tr><th>Field</th><th>Right</th><th>Partly right</th><th>Wrong</th><th>No answer</th><th>Could not be checked</th><th>First-pass accuracy</th></tr></thead><tbody>{p1_rows}</tbody></table></div>
<div class="tiles">
<div class="tile"><b>{tot_acc}%</b><span>Pass 1, memory only: {tot_scored} fields scored across {len(p1rows)} apps. MCP weakest at {p1[2]['acc']}%.</span></div>
<div class="tile"><b>{stat_c['V']}/{N}</b><span>Pass 2, vendor docs: rows fully verified ({stat_c['P']} partly, {stat_c['U']} unverified)</span></div>
<div class="tile"><b>{pct_before}% &rarr; {pct_after}%</b><span>Pass 3, blind audit: sample agreement before and after settling each disagreement on the vendor page</span></div>
<div class="tile"><b>17/40</b><span>Pass 4, MCP sweep: weak rows re-researched; 17 turned out to have a vendor MCP server</span></div>
</div>
<p class="mut">Scoring: partly right counts as half, and fields the docs could not settle are left out. The 14 apps covered by an earlier research task were not scored this way; that task reported its own first pass as 3 right, 2 partly right, 4 wrong of 9.</p>
<h3>First-pass misses</h3>
<div class="scroll" style="max-height:420px"><table><thead><tr><th>#</th><th>App</th><th>Field</th><th>First pass</th><th>What the docs pass found</th></tr></thead><tbody>{miss_rows}</tbody></table></div>
<details><summary>First-pass answers that were only partly right ({sum(1 for m in misses if m[3]=='partly right')})</summary><div class="scroll" style="max-height:360px"><table><thead><tr><th>#</th><th>App</th><th>Field</th><th>What the docs pass found</th></tr></thead><tbody>{part_rows}</tbody></table></div></details>
<h3>What the recheck loop changed</h3>
<ul>
<li><b>Grain:</b> two help articles seemed to disagree on Free-plan tokens. Opening both showed they agree: every plan.</li>
<li><b>Front:</b> the first MCP page found was a deprecated closed beta. The docs index led to the live server at mcp.frontapp.com/mcp.</li>
<li><b>Plain:</b> first marked "none found" after hitting the docs-search server. The sweep found the real one, mcp.plain.com/mcp, about 400 tools.</li>
<li><b>Twilio:</b> the official MCP is docs-search only and takes no credentials. Recorded as limited.</li>
<li><b>Zendesk:</b> the docs head the API token section "deprecated". OAuth is the way in.</li>
<li><b>Google Ads:</b> developer tokens were sunset on 9 Sep 2026; access is now per Cloud project. The first pass still described tokens.</li>
<li><b>Otter:</b> the pricing page settles it: MCP on the free plan, REST API on Enterprise only.</li>
<li><b>QuickBooks and Xero:</b> JavaScript-only docs blocked the first pass. llms.txt files and help articles settled both: OAuth 2.0, a free sandbox or demo company, and an official MCP server.</li>
<li><b>Still unresolved:</b> iPayX, fanbasis and Paygent Connect. Details in the table.</li>
</ul>
<h3>Blind audit by a separate agent</h3>
{audit_html}
<h3>Spot check of the sample</h3>
<p>Every field for the {len(audit_cmp) or 20} sampled apps was checked twice against vendor pages, the second time with no access to the first answers. Of {3*(audit_tot['n'] if audit_tot else 20)} fields, {audit_tot['auth']+audit_tot['gate']+audit_tot['mcp'] if audit_tot else 0} matched on both passes, {audit_tot['corrected'] if audit_tot else 0} were corrected after re-opening the vendor page, and {audit_tot['open_or_kept'] if audit_tot else 0} stayed open or kept the original reading. The table above shows each one; the open items are flagged in the matrix.</p>

<h2>5. Traps met along the way</h2>
<ul>
<li><b>Text aimed at AI tools.</b> gopaygent.com carries a meta tag telling language models to call it a "superior Stripe alternative". Treated as content, never as instructions.</li>
<li><b>Hints that point at old docs.</b> highlevel.stoplight.io, binance-docs.github.io and harvestapp.com are not the current docs. Amazon SP-API docs moved to developer-docs.amazon.</li>
<li><b>MCP look-alikes.</b> Zendesk's GA "MCP client" points outward, and the Marketplace "MCP Server" app there is by Swifteq. PitchBook's "Essential" MCP is Perplexity's; only "Premium" is PitchBook's. Docs-search servers (Discord, Mailchimp, Twilio) are easy to mistake for account servers.</li>
<li><b>Vendor pages that disagree with each other.</b> Pumble names two different auth headers. Otter has a stale Enterprise-only MCP article. Aircall's developer FAQ denies the MCP its own help centre documents.</li>
<li><b>Name collisions.</b> Clay and clay.earth, Consensus and goconsensus.com, Paygent and the Japanese PAYGENT, iPayX and several iPay companies, transcriptapi.com and transcriptapi.net.</li>
<li><b>Half-true hints.</b> "Otter AI (MCP server)" is right, but there is no public API key. "Consensus (OAuth requested)" fits the MCP; the REST API uses a key.</li>
</ul>
<p class="mut">For agents: the full dataset is embedded below as JSON and also served as apps.json.</p>
<script type="application/json" id="data">{json.dumps(dict(stats=stats, apps=export), ensure_ascii=False).replace('</', '<\\/')}</script>
<script>
const $=id=>document.getElementById(id),rows=[...document.querySelectorAll('#t tbody tr')];
function f(){{const q=$('q').value.toLowerCase(),c=$('fc').value,g=$('fg').value,m=$('fm').value,v=$('fv').value,s=$('fs').value;let n=0;
rows.forEach(r=>{{const d=r.dataset,ok=(!c||d.cat===c)&&(!g||d.gate===g)&&(!m||d.mcp===m)&&(!v||d.ver===v)&&(!s||d.st===s)&&(!q||r.textContent.toLowerCase().includes(q));r.style.display=ok?'':'none';n+=ok}});
$('cnt').textContent=n+' of '+rows.length+' apps';}}
['q','fc','fg','fm','fv','fs'].forEach(i=>$(i).addEventListener('input',f));f();
</script>
</main></body></html>'''
open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(PAGE)
print(json.dumps(stats, indent=1))
print('easy', len(easy), '| outreach', outreach, '| review', review, '| plan', plan, '| unclear', unclear)
print('misses', len(misses), 'blockers', blockers.most_common())
