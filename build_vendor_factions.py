#!/usr/bin/env python3
"""build_vendor_factions.py — the shared-VENDOR network among LA committees.

Sibling spike to build_factions.py. Where that tool asks "which committees draw
from the same DONORS", this asks "which committees pay the same VENDORS" — the
media firms, mail houses, pollsters, and consultants that quietly operate a
bloc. Two committees wired to the same boutique consultant are, operationally,
part of the same machine.

The catch that makes this NOT a find-and-replace of build_factions.py: a shared
vendor is two different signals mixed together.
  * Commodity vendors — Office Depot, Walmart, USPS, Facebook, the banks, the
    Secretary of State filing window. Everyone pays these; they carry zero
    factional signal and, left in, bury the graph in fake edges.
  * Signature political-service vendors — a direct-mail house or ad firm that
    serves one faction. THIS is the signal.

So we treat it as a TF-IDF / document-frequency problem: committees are
documents, vendors are terms. A vendor paid by half the committees is a
stopword (dropped by DF cap); a boutique vendor paid by a handful is a rare,
high-IDF term. Edges are an IDF-WEIGHTED Jaccard over the surviving vendors, so
two committees that uniquely share a rare consultant outrank two that merely
both used the post office. Outbound gifts (DONATION / CONTRIBUTION / SPONSOR…)
are excluded — those are money the committee gives away, not a service it buys.

Reads the campaign-finance repo's .la_cache expenditure files (override with
--cache or $LA_CACHE). Stdlib only, like build_factions.py.

    py build_vendor_factions.py
    py build_vendor_factions.py --cache "../la-campaign-finance/.la_cache" --top 300
    Tuning: --top 300 --stopword-df 100 --min-shared 3 --min-wjaccard 0.06 --max-per-node 6
"""
import gzip, json, os, glob, sys, time, re, math
from collections import defaultdict, Counter
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))

def _arg(flag, default):
    return type(default)(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default

def _default_cache():
    for c in (os.path.join(HERE, '..', '.la_cache'),
              os.path.join(HERE, '..', 'la-campaign-finance', '.la_cache'),
              os.path.join(HERE, '..', 'Claude Code', '.la_cache')):
        if os.path.isdir(c):
            return c
    return os.path.join(HERE, '..', '.la_cache')

CACHE = _arg('--cache', '') or os.environ.get('LA_CACHE') or _default_cache()
OUT   = os.path.join(HERE, 'vendor_factions.json')

TOP_N        = _arg('--top', 500)          # committees in the graph (by service spend)
STOPWORD_DF  = _arg('--stopword-df', 100)  # a vendor paid by >= this many committees is commodity → dropped
MIN_SHARED   = _arg('--min-shared', 3)     # an edge needs this many shared non-stopword vendors
MIN_WJACCARD = _arg('--min-wjaccard', 0.06)  # ...and this IDF-weighted overlap
MAX_PER_NODE = _arg('--max-per-node', 6)   # keep each node's strongest links
EDGE_VENDORS = _arg('--edge-vendors', 40)  # shared vendors stored per edge (for the detail panel)
INTEREST_PEAK = 20  # "most interesting" shared vendor serves ~this many committees:
#                     rarer ones are likely one-off noise, common ones near-commodity
#                     (boutique operatives — Littlefield, Baselice — sit around here)

if not os.path.isdir(CACHE):
    sys.exit(f'No .la_cache at {CACHE!r}. Pass --cache <path> or set $LA_CACHE.')

# ── vendor identity (light) ──────────────────────────────────────────────────
# Vendors carry no id (same as donors). Full org-variant resolution is future
# work; for the spike we normalize punctuation + drop corporate suffixes so the
# obvious spellings collapse, and lean on the DF cap + IDF to absorb the rest —
# a commodity vendor split across spellings has each spelling over the cap, so
# fragmentation there is harmless; only boutique-vendor fragmentation costs us.
_SUFFIX = re.compile(r'\b(LLC|L L C|INC|INCORPORATED|CORP|CORPORATION|CO|LTD|LP|LLP|PC|PLLC|USA)\b')
_ALIAS = {   # a few high-value merges the suffix strip misses
    'WAL-MART': 'WALMART', 'WALMART COM': 'WALMART',
    'UNITED STATES POSTAL SERVICE': 'USPS', 'US POSTAL SERVICE': 'USPS',
    'THE UPS STORE': 'UPS', 'META PLATFORMS': 'FACEBOOK', 'META': 'FACEBOOK',
}
def norm_vendor(s):
    s = s.upper()
    s = re.sub(r"[.,'\"/()#]", ' ', s)
    s = re.sub(r"[^A-Z0-9 &-]", ' ', s)
    s = _SUFFIX.sub(' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return _ALIAS.get(s, s)

# Light identity resolution: merge morphological variants of the SAME firm without
# collapsing genuinely different ones. Probing the data showed the signal vendors
# fragment ("LITTLEFIELD CONSULTING" / "CONSULTANTS" / "& ASSOCIATES CONSULTING" =
# one firm split 3 ways), so we fold AND/&, drop a leading THE, and peel only
# trailing FIRM-TYPE words. We deliberately do NOT peel MEDIA/GROUP/PRODUCTIONS —
# those distinguish real siblings ("Arsement Media Group" vs "Arsement
# Productions"), and over-merging would fabricate the false edges we work to avoid.
_GENERIC = {'CONSULTING', 'CONSULTANTS', 'CONSULTANT', 'ASSOCIATES', 'ASSOCIATION',
            'ASSOC', 'PARTNERS', 'PARTNER', 'COMPANY'}
# Domain merges the morphological rules can't know: firms that are the same
# entity under different names. NCC Media (National Cable Communications) is the
# cable-ad rep that rebranded as Ampersand, so its many spellings are one vendor.
_FIRM_CANON = [
    (re.compile(r'^NCC\b'),       'AMPERSAND'),
    (re.compile(r'^AMPERSAND\b'), 'AMPERSAND'),
]
def resolve_key(nv):
    s = nv[4:] if nv.startswith('THE ') else nv
    s = re.sub(r'\b(AND|&)\b', ' ', s)
    toks = re.sub(r'\s+', ' ', s).strip().split()
    while len(toks) > 1 and toks[-1] in _GENERIC:
        toks.pop()
    k = ' '.join(toks) or nv
    for pat, canon in _FIRM_CANON:
        if pat.match(k):
            return canon
    return k

# Resolved key -> most-common original spelling, for readable display labels.
DISPLAY = defaultdict(Counter)
def key_of(raw):
    nv = norm_vendor(raw)
    if not nv or nv == 'UNKNOWN':
        return None
    k = resolve_key(nv)
    DISPLAY[k][nv] += 1
    return k

# ── political-recipient filter (the crucial one) ─────────────────────────────
# The first spike drowned in a false signal: trade-association PACs that all
# *donate to the same politicians* looked "allied" — but a contribution to a
# candidate is not a vendor relationship. Most such rows carry a blank
# description, so the category regex misses them. We instead drop any recipient
# that IS a known committee/candidate (matches la_filer_lookup) or that looks
# like a political committee by name. What's left is money spent on services.
# Honorifics + political titles the ballot/committee names drop but expenditure
# recipients carry ("SENATOR FRANCIS HEITMEIER" vs the filer "FRANCIS HEITMEIER").
_TITLES = (r'DR|MR|MRS|MS|JR|SR|II|III|IV|ESQ|PHD|MD|HON|HONORABLE|SEN|SENATOR|'
           r'REP|REPRESENTATIVE|GOV|GOVERNOR|MAYOR|SHERIFF|JUDGE|JUSTICE|'
           r'COUNCILMAN|COUNCILWOMAN|CONGRESSMAN|CONGRESSWOMAN|ASSESSOR|CLERK|DA')
_TITLE_RE = re.compile(r'\b(' + _TITLES + r')\.?\b')
_NICK = {'CHUCK': 'CHARLES', 'DAN': 'DANIEL', 'BOB': 'ROBERT', 'BOBBY': 'ROBERT',
         'JIM': 'JAMES', 'JIMMY': 'JAMES', 'BILL': 'WILLIAM', 'MIKE': 'MICHAEL',
         'TOM': 'THOMAS', 'JOE': 'JOSEPH', 'STEVE': 'STEPHEN', 'DAVE': 'DAVID',
         'DON': 'DONALD', 'RICK': 'RICHARD', 'TONY': 'ANTHONY', 'ED': 'EDWARD',
         'GREG': 'GREGORY', 'BEN': 'BENJAMIN', 'PAT': 'PATRICK', 'NICK': 'NICHOLAS',
         'ANDY': 'ANDREW', 'JEFF': 'JEFFREY', 'KEN': 'KENNETH', 'RON': 'RONALD',
         'CHRIS': 'CHRISTOPHER', 'MATT': 'MATTHEW', 'LIZ': 'ELIZABETH'}
def _norm_name(s):
    s = _TITLE_RE.sub('', s.upper())
    s = re.sub(r'[^A-Z\s]', ' ', s)
    return ' '.join(s.split())
def _canon(tok):
    return _NICK.get(tok, tok)

# Junk/placeholder recipients — LA Ethics aggregate rows, not real vendors.
_JUNK = re.compile(r'\bNON[ -]?LA\b|UNITEMIZED|AGGREGATE|MISCELLANEOUS|'
                   r'\bVARIOUS\b|NO NAME|NOT (PROVIDED|LISTED|APPLICABLE)|\bN/?A\b')
_POLITICAL = re.compile(
    r'\bPAC\b|POLITICAL ACTION|\bCAMPAIGN\b|COMMITTEE TO (RE-?)?ELECT|'
    r'\bRE-?ELECT\b|FRIENDS OF|CITIZENS FOR|(DEMOCRATIC|REPUBLICAN) (PARTY|'
    r'EXECUTIVE|CAMPAIGN|CAUCUS)|LEGISLATIVE (CAUCUS|BLACK|WOMEN)|'
    r'\bFOR (GOVERNOR|SENATE|SHERIFF|MAYOR|CONGRESS|COUNCIL|ASSESSOR|'
    r'ATTORNEY|LEGISLATURE|STATE|US|U S)\b')

def load_committee_index():
    """Filer universe as (full normalized names, surname -> {given-name tokens}).
    The surname map catches Louisiana's middle-name usage: the ballot files
    'ROBERT BRET ALLAIN' but the check is written to 'BRET ALLAIN' — same person,
    so a surname hit plus ANY shared given token (nickname-folded) counts."""
    for p in (os.path.join(CACHE, '..', 'la_filer_lookup.json'),
              os.path.join(CACHE, 'la_filer_lookup.json')):
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                keys = [_norm_name(k) for k in json.load(f)]
            full = set(keys)
            surname = defaultdict(set)
            for n in keys:
                t = n.split()
                if len(t) >= 2:
                    for tok in t[:-1]:
                        surname[t[-1]].add(_canon(tok))
            return full, surname
    print('  note: la_filer_lookup.json absent — political recipients not filtered')
    return set(), {}

_COMMITTEE_NAMES, _COMMITTEE_SURNAME = load_committee_index()
def _is_vendor(raw):
    """A real service vendor — not a contribution to a committee/candidate, and
    not an Ethics placeholder row."""
    u = raw.upper()
    if _JUNK.search(u) or _POLITICAL.search(u):
        return False
    norm = _norm_name(raw)
    if norm in _COMMITTEE_NAMES:
        return False
    t = norm.split()
    if len(t) >= 2:
        givens = {_canon(x) for x in t[:-1]}
        if givens & _COMMITTEE_SURNAME.get(t[-1], set()):
            return False
    return True

# Outbound gifts / non-service rows: money the committee gives away or pure
# bank/card mechanics — not a vendor relationship. Matched on the description.
_GIFT = re.compile(r'\b(DONATION|CONTRIBUTION|SPONSOR|SPONSORSHIP|SCHOLARSHIP|'
                   r'GIFT|FLOWERS|WREATH|CONDOLENCE|TICKETS?|GALA|BANQUET TABLE)\b')
_FEE  = re.compile(r'\b(BANK (SERVICE )?(CHARGE|FEE)|SERVICE CHARGE|CREDIT CARD|'
                   r'PROCESSING FEE|MERCHANT FEE|WIRE FEE|INTEREST|NSF|OVERDRAFT)\b')
def _is_service(desc):
    d = (desc or '').upper()
    return not (_GIFT.search(d) or _FEE.search(d))

def _rows():
    for path in sorted(glob.glob(os.path.join(CACHE, 'expenditures_yr*.json.gz'))):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    yield json.loads(line)
                except Exception:
                    continue

t0 = time.time()
# ── Pass 1: per-vendor document frequency + per-committee service spend ───────
vendor_filers = defaultdict(set)   # vendor -> {filerNumber}
spend         = defaultdict(float) # filer -> service $ (picks the top N)
for r in _rows():
    if not _is_service(r.get('description')):
        continue
    fn  = (r.get('filerNumber') or '').strip()
    raw = (r.get('contributor') or '').strip()
    if not fn or not raw or not _is_vendor(raw):
        continue
    v = key_of(raw)
    if not v:
        continue
    amt = float(r.get('amount') or 0)
    if amt <= 0:
        continue
    spend[fn] += amt
    vendor_filers[v].add(fn)

N_COM = len(spend)
df    = {v: len(fs) for v, fs in vendor_filers.items()}
idf   = {v: math.log(N_COM / d) for v, d in df.items()}          # rarity weight
stop  = {v for v, d in df.items() if d >= STOPWORD_DF}           # commodity stopwords
top   = {fn for fn, _ in sorted(spend.items(), key=lambda x: -x[1])[:TOP_N]}
print(f'Pass 1: {N_COM:,} committees, {len(df):,} vendors; '
      f'{len(stop)} commodity stopwords (DF>={STOPWORD_DF}); kept top {len(top)} by spend '
      f'({time.time()-t0:.0f}s)')

# ── Pass 2: per-committee vendor sets (non-stopword) + name/party ─────────────
vend   = defaultdict(set)     # filer -> {vendor}
names  = defaultdict(Counter) # filer -> {candidate spelling: count}
parties= defaultdict(Counter) # filer -> {party: count}
vend_to_filers = defaultdict(set)
for r in _rows():
    fn = (r.get('filerNumber') or '').strip()
    if fn not in top:
        continue
    if r.get('candidate'): names[fn][r['candidate']] += 1
    if r.get('party'):     parties[fn][r['party']] += 1
    if not _is_service(r.get('description')):
        continue
    raw = (r.get('contributor') or '').strip()
    if not raw or not _is_vendor(raw):
        continue
    v = key_of(raw)
    if not v or v in stop:
        continue
    vend[fn].add(v)
    vend_to_filers[v].add(fn)
print(f'Pass 2: vendor sets for {len(vend)} committees ({time.time()-t0:.0f}s)')

# ── Pairwise shared vendors via co-occurrence (sparse) ───────────────────────
shared = defaultdict(list)   # (a,b) -> [shared vendor,...]
for v, fset in vend_to_filers.items():
    if len(fset) < 2:
        continue
    for a, b in combinations(sorted(fset), 2):
        shared[(a, b)].append(v)

# Edges: IDF-weighted Jaccard = Σidf(shared) / Σidf(union). Controls for size
# like plain Jaccard, but a rare shared consultant outweighs a shared commonplace.
def _idf_sum(vs):
    return sum(idf.get(v, 0.0) for v in vs)

cand = []
for (a, b), sv in shared.items():
    if len(sv) < MIN_SHARED:
        continue
    union = vend[a] | vend[b]
    wj = _idf_sum(sv) / _idf_sum(union) if union else 0.0
    if wj >= MIN_WJACCARD:
        j = len(sv) / len(union)
        cand.append((a, b, sv, wj, j))

# Prune to each node's strongest links (by weighted Jaccard) for readability.
by_node = defaultdict(list)
for a, b, sv, wj, j in cand:
    by_node[a].append((wj, a, b, sv, j))
    by_node[b].append((wj, a, b, sv, j))
keep = {}
for lst in by_node.values():
    for wj, a, b, sv, j in sorted(lst, key=lambda x: -x[0])[:MAX_PER_NODE]:
        keep[(a, b)] = (sv, wj, j)

def _party(fn):
    p = parties[fn].most_common(1)[0][0] if parties[fn] else 'OTH'
    return p if p in ('DEM', 'REP', 'IND', 'LBT', 'GRN') else 'OTH'

# Resolved key -> readable label (the most-common original spelling), except a
# firm-canon target shows under its canonical name (Ampersand, not "NCC Media").
disp = {k: c.most_common(1)[0][0] for k, c in DISPLAY.items()}
for _pat, _canon in _FIRM_CANON:
    if _canon in disp:
        disp[_canon] = _canon
def _disp(v):
    return disp.get(v, v)

# Rank a pair's shared vendors for display. Primary signal: graph-GLUE — how many
# kept committee-pairs a vendor ties together. An operative (Littlefield, Baselice)
# glues many pairs; a hotel or a burrito shop two committees happened to share
# glues none, so it sinks. DF alone can't tell a media firm from a caterer, but
# "does this vendor connect the graph" can. Ties break by an interestingness band
# peaking at INTEREST_PEAK committees, then name. Store [label, DF] so the panel
# can disclose how common each vendor is.
glue_ct = Counter()
for _k, (sv, _wj, _j) in keep.items():
    for v in sv:
        glue_ct[v] += 1
def _interest(v):
    d = df.get(v, 0)
    return d if d <= INTEREST_PEAK else 2 * INTEREST_PEAK - d
edges = []
for (a, b), (sv, wj, j) in keep.items():
    ranked = sorted(sv, key=lambda v: (-glue_ct[v], -_interest(v), _disp(v)))[:EDGE_VENDORS]
    top_sv = [[_disp(v), df.get(v, 0)] for v in ranked]
    edges.append({'a': a, 'b': b, 'shared': len(sv), 'jaccard': round(j, 4),
                  'wjaccard': round(wj, 4), 'topVendors': top_sv})

node_ids = {e['a'] for e in edges} | {e['b'] for e in edges}
nodes = []
for fn in sorted(node_ids, key=lambda f: -spend[f]):
    name = names[fn].most_common(1)[0][0] if names[fn] else f'Filer {fn}'
    nodes.append({'id': fn, 'name': name, 'party': _party(fn),
                  'spend': round(spend[fn]), 'nVendors': len(vend[fn])})

out = {
    'generated': time.strftime('%Y-%m-%d'),
    'params': {'top': TOP_N, 'stopword_df': STOPWORD_DF, 'min_shared': MIN_SHARED,
               'min_wjaccard': MIN_WJACCARD, 'max_per_node': MAX_PER_NODE},
    'nodes': nodes,
    'edges': edges,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, separators=(',', ':'), ensure_ascii=False)
print(f'\nWrote {OUT}: {len(nodes)} nodes, {len(edges)} edges ({time.time()-t0:.0f}s)')

# ── Diagnostics: is the signal real? ─────────────────────────────────────────
nm = {n['id']: n['name'] for n in nodes}
print('\nStrongest shared-vendor links (weighted Jaccard):')
for e in sorted(edges, key=lambda e: -e['wjaccard'])[:14]:
    print(f"  {nm[e['a']][:26]:<26} <-> {nm[e['b']][:26]:<26}  "
          f"{e['shared']:>3} shared  wJ={e['wjaccard']:.2f}")
    print(f"        via: {', '.join(tv[0][:26] for tv in e['topVendors'][:6])}")

# Connected components over kept edges = candidate vendor blocs; name each by the
# vendor that glues it (most-shared across the bloc's internal edges).
adj = defaultdict(set)
for e in edges:
    adj[e['a']].add(e['b']); adj[e['b']].add(e['a'])
seen, comps = set(), []
for fn in node_ids:
    if fn in seen:
        continue
    stack, comp = [fn], []
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x); comp.append(x)
        stack.extend(adj[x] - seen)
    comps.append(comp)
# Operative hubs: rank vendors by how many KEPT committee-pairs they glue. Raw
# "serves the most committees" just re-finds commodity (a caterer touches 15
# unrelated committees); the connective signal is a vendor shared across pairs
# that the whole graph already judged tightly linked — that's a real operative.
print('\nVendors gluing the most committee-pairs in the graph (operative hubs):')
def _nm(f):
    return names[f].most_common(1)[0][0] if names[f] else f'Filer {f}'
glue_pairs = Counter()
glue_where = defaultdict(set)
for (a, b), (sv, wj, j) in keep.items():
    for v in sv:
        glue_pairs[v] += 1
        glue_where[v].add(a); glue_where[v].add(b)
for v, c in sorted(glue_pairs.items(), key=lambda x: (-x[1], -idf.get(x[0], 0)))[:18]:
    who = ', '.join(_nm(f)[:18] for f in sorted(glue_where[v], key=lambda f: -spend[f])[:4])
    print(f'  {c:>2} pairs / {len(glue_where[v]):>2} committees  DF={df.get(v,0):>4}  '
          f'{_disp(v)[:26]:<26} e.g. {who}')

print(f'\n{len(comps)} connected components; largest first:')
for comp in sorted(comps, key=len, reverse=True)[:10]:
    if len(comp) < 2:
        continue
    glue = Counter()
    for e in edges:
        if e['a'] in comp and e['b'] in comp:
            for tv in e['topVendors']:
                glue[tv[0]] += 1
    gl = ', '.join(f'{v}' for v, _ in glue.most_common(4))
    members = ', '.join(nm[f][:22] for f in sorted(comp, key=lambda f: -spend[f])[:5])
    print(f'  [{len(comp):>2} committees] glue: {gl}')
    print(f'        e.g. {members}')
