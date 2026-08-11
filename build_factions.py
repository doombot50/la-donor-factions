#!/usr/bin/env python3
"""build_factions.py — the shared-donor network among Louisiana's biggest filers.

Two committees that draw from the *same donors* are, in money terms, allied.
This finds the top filers by lifetime raised, computes how many donors each PAIR
shares plus the Jaccard overlap (which controls for fundraising size, so a giant
committee doesn't look "allied" with everyone just by being big), prunes to each
node's strongest links for readability, and emits a node/edge graph for the
standalone force-directed viz (index.html).

Donor identity uses the campaign-finance project's RESOLVED donor entities
(la_donor_entities.json.gz): nickname-folded names clustered within last-name +
generational-suffix + ZIP, with org spelling-variants merged. So "Bob" and
"Robert Smith" at the same ZIP count once, two different "John Smith"s in
different ZIPs don't collide, and 20 Chevron spellings are one donor. Committee
transfers and filing fees are excluded — these are shared *donors*, not the money
committees pass between themselves.

Reads the campaign-finance repo's .la_cache (override with --cache or $LA_CACHE).
Stdlib only — a small, single-story spin-off, like the pay-to-play tool.

    py build_factions.py
    py build_factions.py --cache "../Claude Code/.la_cache" --top 350
"""
import gzip, json, os, glob, re, sys, time, zlib
from collections import defaultdict, Counter
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))

def _arg(flag, default):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag) + 1
    if i >= len(sys.argv):
        sys.exit(f'{flag} needs a value.')
    try:
        return type(default)(sys.argv[i])
    except ValueError:
        sys.exit(f'{flag} expects {type(default).__name__}, got {sys.argv[i]!r}.')

def _default_cache():
    # Works whether this tool sits inside the CF repo or as a sibling of it.
    for c in (os.path.join(HERE, '..', '.la_cache'),
              os.path.join(HERE, '..', 'Claude Code', '.la_cache'),
              os.path.join(HERE, '..', 'la-campaign-finance', '.la_cache')):
        if os.path.isdir(c):
            return c
    return os.path.join(HERE, '..', '.la_cache')

CACHE = _arg('--cache', '') or os.environ.get('LA_CACHE') or _default_cache()
OUT   = os.path.join(HERE, 'factions.json')

# Defaults reproduce the shipped factions.json (the "widen the network" build).
TOP_N        = _arg('--top', 600)         # filers in the graph (by lifetime raised)
MIN_SHARED   = _arg('--min-shared', 12)   # an edge needs at least this many shared donors
MIN_JACCARD  = _arg('--min-jaccard', 0.05)  # ...and this overlap (controls for size)
MAX_PER_NODE = _arg('--max-per-node', 6)  # keep each node's strongest links
EDGE_DONORS  = _arg('--edge-donors', 12)  # receipts: top shared donors kept per edge
ALLOW_GAPS   = '--allow-gaps' in sys.argv   # build anyway from an incomplete cache

if not os.path.isdir(CACHE):
    sys.exit(f'No .la_cache at {CACHE!r}. Pass --cache <path> or set $LA_CACHE.')

# ── cache completeness ──────────────────────────────────────────────────────
# Checked BEFORE any work, because both failure modes here are silent: an empty
# cache would write an empty factions.json over the committed one, and a cache
# missing a year (an interrupted `gh release upload --clobber` strands assets —
# that is how contributions_yr2003 went missing upstream) would understate every
# lifetime total and every donor overlap while looking perfectly healthy.
# Contributions exist for every year upstream, so the years must be contiguous.
CYCLE_FILES = sorted(glob.glob(os.path.join(CACHE, 'contributions_yr*.json.gz')))
if not CYCLE_FILES:
    sys.exit(f'No contributions_yr*.json.gz in {CACHE!r} — nothing to build. Point '
             f'--cache at the campaign-finance .la_cache (its fetch_cache_assets.py '
             f'seeds one from the data-cache release). Refusing to overwrite {OUT}.')
YEARS = sorted(int(m.group(1)) for m in
               (re.search(r'contributions_yr(\d{4})', os.path.basename(p)) for p in CYCLE_FILES)
               if m)
GAPS = [y for y in range(YEARS[0], YEARS[-1] + 1) if y not in YEARS] if YEARS else []
if GAPS:
    msg = (f'Cache is missing contribution year(s) {GAPS} inside {YEARS[0]}–{YEARS[-1]}. '
           f'Lifetime totals and donor overlaps would be understated. Re-fetch the '
           f'data-cache release assets, or pass --allow-gaps to build anyway.')
    if not ALLOW_GAPS:
        sys.exit(msg)
    print(f'  WARNING: {msg}')

# ── resolved donor identity ─────────────────────────────────────────────────
# Invert la_donor_entities: raw contributor spelling (UPPER) -> cluster id.
# Single-variant clusters store their lone raw as `name`; multi list every raw.
def load_donor_map():
    p = os.path.join(CACHE, 'la_donor_entities.json.gz')
    if not os.path.exists(p):
        print('  note: la_donor_entities.json.gz absent — falling back to raw names')
        return None
    # An ABSENT artifact is a legitimate cold cache (raw-name fallback, disclosed
    # in the output). A PRESENT but unreadable one — half-written, truncated by an
    # interrupted download — must not quietly downgrade donor identity: that would
    # silently change every overlap figure in the graph. Fail and say so.
    try:
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            donors = json.load(f)['donors']
    except (OSError, EOFError, zlib.error, ValueError, KeyError) as e:
        sys.exit(f'Unreadable donor-entity artifact {p}: {e!r}\nRe-fetch it (the '
                 f'campaign-finance data-cache release), or delete it to build with '
                 f'raw-name donor identity.')
    raw2cid = {}
    for cid, d in donors.items():
        # Multi-variant clusters list every raw spelling; single-variant ones
        # store their lone raw as `name`.
        for raw in (d.get('variants') or ([d['name']] if d.get('name') else [])):
            raw2cid[raw] = cid
    if not raw2cid:
        sys.exit(f'{p} resolved 0 donor spellings — the artifact looks empty or partial.')
    return raw2cid

raw2cid = load_donor_map()
def donor_id(raw_upper):
    return raw2cid.get(raw_upper, raw_upper) if raw2cid else raw_upper

# Bulk-data placeholders that are not nameable donors: LA Ethics aggregate and
# adjustment rows ("UNITEMIZED CONTRIBUTIONS", "ANONYMOUS", "MISCELLANEOUS",
# "NON LA TRANSACTIONS"...). The upstream resolver drops them, so they are absent
# from la_donor_entities and would fall through donor_id() to their raw string —
# where each reads as one REAL donor shared by nearly every committee that files
# such a line, manufacturing edges out of nothing and inflating the dollar-
# weighted overlap (unitemized rows carry large sums). Kept identical to
# _NONDONOR in the campaign-finance repo's build_donor_entities.py: the two must
# stay in lockstep so every raw either resolves or is excluded here.
_NONDONOR = re.compile(
    r'\bNON LA\b|NEGATIVE DISBURSE|UNITEMIZED|\bAGGREGATE\b|\bANONYMOUS\b|'
    r'MISCELLANEOUS|NO NAME (GIVEN|PROVIDED|LISTED)|NOT (PROVIDED|LISTED|APPLICABLE)', re.I)

# ── office lookup ───────────────────────────────────────────────────────────
# SoS candidacies (campaign-finance repo, committed at its root — the cache's
# parent) tell us what office a committee's candidate ran for. The viz names
# factions by their dominant office class ("Sheriffs", "Republican
# legislators"), which beats naming a bloc after whichever member raised most.
def _norm_name(name):
    n = name.upper()
    n = re.sub(r'\b(DR|MR|MRS|MS|JR|SR|II|III|IV|ESQ|PHD|MD)\.?\b', '', n)
    n = re.sub(r'[^A-Z\s]', ' ', n)
    return ' '.join(n.split())

_OFFICE_RULES = [   # first match wins; checked against the uppercased office
    ('LIEUTENANT GOVERNOR', 'Lt. Governor'), ('GOVERNOR', 'Governor'),
    ('ATTORNEY GENERAL', 'Atty. General'), ('SECRETARY OF STATE', 'Sec. of State'),
    ('TREASURER', 'Treasurer'), ('AGRICULTURE', 'Ag. Commissioner'),
    ('INSURANCE', 'Ins. Commissioner'), ('ELECTIONS', 'Elections Comm.'),
    ('PUBLIC SERVICE', 'PSC'), ('BESE', 'BESE'), ('ELEMENTARY AND SECONDARY', 'BESE'),
    ('U. S. SENAT', 'U.S. Senate'), ('US SENAT', 'U.S. Senate'),
    ('U. S. REP', 'U.S. House'), ('US REP', 'U.S. House'), ('CONGRESS', 'U.S. House'),
    ('STATE SENATOR', 'State Senate'), ('STATE REPRESENTATIVE', 'State House'),
    ('SHERIFF', 'Sheriff'), ('DISTRICT ATTORNEY', 'DA'),
    ('JUSTICE', 'Judge'), ('JUDGE', 'Judge'), ('MAYOR', 'Mayor'),
]
# Committee names carry middle initials the ballot drops (and vice versa):
# "John Alario, Jr." vs "JOHN A. ALARIO, JR.". A (canonical first, last) key
# bridges them — used only when it maps to exactly one ballot name.
_NICK = {
    'CHUCK': 'CHARLES', 'CHARLIE': 'CHARLES', 'DAN': 'DANIEL', 'DANNY': 'DANIEL',
    'BOB': 'ROBERT', 'BOBBY': 'ROBERT', 'ROB': 'ROBERT', 'JIM': 'JAMES', 'JIMMY': 'JAMES',
    'BILL': 'WILLIAM', 'BILLY': 'WILLIAM', 'WILL': 'WILLIAM', 'MIKE': 'MICHAEL',
    'TOM': 'THOMAS', 'TOMMY': 'THOMAS', 'JOE': 'JOSEPH', 'JOEY': 'JOSEPH',
    'STEVE': 'STEPHEN', 'DAVE': 'DAVID', 'DON': 'DONALD', 'DONNIE': 'DONALD',
    'RICK': 'RICHARD', 'RICKY': 'RICHARD', 'RITCHIE': 'RICHARD', 'DICK': 'RICHARD',
    'TONY': 'ANTHONY', 'ED': 'EDWARD', 'EDDIE': 'EDWARD', 'GREG': 'GREGORY',
    'BEN': 'BENJAMIN', 'SAM': 'SAMUEL', 'SAMMY': 'SAMUEL', 'PAT': 'PATRICK',
    'NICK': 'NICHOLAS', 'ANDY': 'ANDREW', 'DREW': 'ANDREW', 'JEFF': 'JEFFREY',
    'KEN': 'KENNETH', 'KENNY': 'KENNETH', 'RON': 'RONALD', 'RONNIE': 'RONALD',
    'LARRY': 'LAWRENCE', 'JERRY': 'GERALD', 'GERRY': 'GERALD', 'WALT': 'WALTER',
    'ALEX': 'ALEXANDER', 'CHRIS': 'CHRISTOPHER', 'MATT': 'MATTHEW',
    'FRED': 'FREDERICK', 'FREDDIE': 'FREDERICK', 'STEVEN': 'STEPHEN',
    'LIZ': 'ELIZABETH', 'BETH': 'ELIZABETH', 'BETSY': 'ELIZABETH',
}
def _canon_first(tok):
    return _NICK.get(tok, tok)

def load_offices():
    for p in (os.path.join(CACHE, '..', 'la_candidacies_raw.json.gz'),
              os.path.join(CACHE, 'la_candidacies_raw.json.gz')):
        if os.path.exists(p):
            with gzip.open(p, 'rt', encoding='utf-8') as f:
                cand = json.load(f)
            exact = {_norm_name(k): v for k, v in cand.items()}
            fl = {}
            for k in exact:
                t = k.split()
                if len(t) >= 2:
                    fl.setdefault((_canon_first(t[0]), t[-1]), set()).add(k)
            return exact, fl
    print('  note: la_candidacies_raw.json.gz absent — nodes ship without offices')
    return None

def _classify(office):
    o = (office or '').split('--')[0].strip().upper()
    if 'PRESIDENT' in o:
        return None
    for pat, label in _OFFICE_RULES:
        if pat in o:
            return label
    return 'Local office'

def office_of(display_name, offices):
    """Each stage falls through when it yields no *classifiable* office — an
    exact ballot-name hit that only holds party-committee posts must not mask
    a middle-initial variant that carries the real office."""
    if not offices:
        return None
    exact, fl = offices
    norm = _norm_name(display_name)
    cls = _office_class(exact.get(norm) or [])
    if cls:
        return cls
    # ballots use nicknames: "John L. (Jay) Dardenne" appears as "Jay Dardenne"
    m = re.match(r'^.*?\(([^)]+)\)(.*)$', display_name)
    if m:
        cls = _office_class(exact.get(_norm_name(m.group(1) + ' ' + m.group(2))) or [])
        if cls:
            return cls
    # middle-initial / nickname drift: match on (canonical first, last).
    # Several ballot spellings may share the key (one person's variants, or
    # rarely two people) — accept when they all classify the same anyway.
    t = norm.split()
    if len(t) >= 2:
        ks = fl.get((_canon_first(t[0]), t[-1]))
        if ks:
            classes = {_office_class(exact[k]) for k in ks}
            classes.discard(None)
            if len(classes) == 1:
                return classes.pop()
    return None

def _office_class(rows):
    dated = []
    for r in rows:
        if r.get('party_office'):
            continue
        cls = _classify(r.get('office'))
        if not cls:
            continue
        mdy = (r.get('date') or '').split('/')
        key = (mdy[2], mdy[0], mdy[1]) if len(mdy) == 3 else ('', '', '')
        dated.append((key, cls))
    # the most recent run is who they are now (legislator -> judge => Judge)
    return max(dated)[1] if dated else None

_scan = {'bad': 0}      # unparseable lines seen in the current pass

def _rows():
    for path in CYCLE_FILES:
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        _scan['bad'] += 1
        except (OSError, EOFError, zlib.error) as e:
            # A truncated/corrupt .json.gz is a partial download. Silently
            # returning its readable prefix would drop part of a year from every
            # total; name the file and stop instead.
            sys.exit(f'Corrupt or truncated cache file {path}: {e!r}\nRe-fetch it '
                     f'(the campaign-finance data-cache release).')

def _report_scan(pass_name):
    if _scan['bad']:
        print(f'  WARNING: {pass_name} skipped {_scan["bad"]:,} unparseable line(s)')
    _scan['bad'] = 0

def _is_donor_gift(r):
    # A real outside donation — not a committee-to-committee transfer or filing fee.
    return not (r.get('isTransfer') or r.get('isFilingFee'))

t0 = time.time()
# Pass 1: lifetime donor money per filer — to pick the top N.
raised = defaultdict(float)
for r in _rows():
    fn = (r.get('filerNumber') or '').strip()
    if fn and _is_donor_gift(r):
        raised[fn] += float(r.get('amount') or 0)
top = {fn for fn, _ in sorted(raised.items(), key=lambda x: -x[1])[:TOP_N]}
print(f'Pass 1: {len(raised):,} filers; kept top {len(top)} by raised ({time.time()-t0:.0f}s)')
_report_scan('pass 1')

# Pass 2: resolved-donor sets + per-donor dollars for the top filers + display name/party.
donors  = defaultdict(set)        # filer -> {donor cluster id}
dollars = defaultdict(dict)       # filer -> {donor cluster id: total $ given}
names   = defaultdict(Counter)    # filer -> {candidate spelling: count}
parties = defaultdict(Counter)    # filer -> {party: count}
donor_to_filers = defaultdict(set)
# Per cluster, the AS-IN-ROWS contributor spelling carrying the most dollars.
# The edge receipts link each shared donor to the finance portal's #/donor/
# profile, and that route matches the row's contributor string EXACTLY (original
# case) — the uppercased cluster variants in la_donor_entities would miss. The
# top-dollar spelling also shows the biggest slice of a merged cluster there.
spellings = defaultdict(Counter)  # donor cluster id -> {original spelling: $}
for r in _rows():
    fn = (r.get('filerNumber') or '').strip()
    if fn not in top:
        continue
    if r.get('candidate'): names[fn][r['candidate']] += 1
    if r.get('party'):     parties[fn][r['party']] += 1
    if not _is_donor_gift(r):
        continue
    orig = (r.get('contributor') or '').strip()
    raw = orig.upper()
    if not raw or raw == 'UNKNOWN' or _NONDONOR.search(raw):
        continue
    cid = donor_id(raw)
    amt = float(r.get('amount') or 0)
    donors[fn].add(cid)
    d = dollars[fn]
    d[cid] = d.get(cid, 0.0) + amt
    donor_to_filers[cid].add(fn)
    spellings[cid][orig] += amt
print(f'Pass 2: donor sets built for {len(donors)} filers ({time.time()-t0:.0f}s)')
_report_scan('pass 2')

# Pairwise shared-donor counts via co-occurrence (sparse: a donor giving to k of
# the top filers contributes to C(k,2) pairs).
shared = defaultdict(int)
for fset in donor_to_filers.values():
    if len(fset) < 2:
        continue
    for a, b in combinations(sorted(fset), 2):
        shared[(a, b)] += 1

# Edges: Jaccard overlap, thresholded, then pruned to each node's strongest links.
cand = []
for (a, b), sc in shared.items():
    if sc < MIN_SHARED:
        continue
    j = sc / (len(donors[a]) + len(donors[b]) - sc)
    if j >= MIN_JACCARD:
        cand.append((a, b, sc, round(j, 4)))

by_node = defaultdict(list)
for a, b, sc, j in cand:
    by_node[a].append((j, a, b, sc))
    by_node[b].append((j, a, b, sc))
keep = set()
for lst in by_node.values():
    for j, a, b, sc in sorted(lst, reverse=True)[:MAX_PER_NODE]:
        keep.add((a, b, sc, j))

# Dollar-weighted Jaccard for surviving edges: Σ min($ to A, $ to B) over shared
# donors, and Σ max over the donor union = total_A + total_B − Σ min. Weights the
# overlap by how much money flows through it, so a bloc of small shared donors
# doesn't read the same as a shared big-money base.
dtotal = {fn: sum(d.values()) for fn, d in dollars.items()}
def _dollar_weight(a, b):
    da, db = dollars[a], dollars[b]
    if len(db) < len(da):
        da, db = db, da
    smin = sum(min(v, db[cid]) for cid, v in da.items() if cid in db)
    smax = dtotal.get(a, 0.0) + dtotal.get(b, 0.0) - smin
    return smin, (smin / smax if smax > 0 else 0.0)

# Edge receipts: the top shared donors behind each surviving link, so the viz
# can show WHO an overlap is instead of only how big it is. Ranked by
# min($ to A, $ to B) — the same quantity sharedDollars sums — so "top" means
# the donors carrying the most money through the overlap itself, not donors
# who mostly fund one side. Names are deduped through one artifact-level table
# (a big donor recurs across many edges) and referenced by index.
donor_names = []                  # artifact-level display-name table
_name_ix = {}                     # donor cluster id -> index into donor_names
def _donor_ix(cid):
    ix = _name_ix.get(cid)
    if ix is None:
        sp = spellings.get(cid)
        name = max(sp.items(), key=lambda kv: kv[1])[0] if sp else str(cid)
        ix = _name_ix[cid] = len(donor_names)
        donor_names.append(name)
    return ix

def _top_shared(a, b):
    da, db = dollars[a], dollars[b]
    if len(db) < len(da):
        da, db = db, da
    ranked = sorted(((min(va, db[cid]), va + db[cid], cid)
                     for cid, va in da.items() if cid in db and min(va, db[cid]) > 0),
                    key=lambda t: (-t[0], -t[1], t[2]))[:EDGE_DONORS]
    # da may be either side after the swap above — report $ per FILER, not per dict
    return [[_donor_ix(cid), round(dollars[a].get(cid, 0.0)), round(dollars[b].get(cid, 0.0))]
            for _, _, cid in ranked]

edges = []
for (a, b, sc, j) in sorted(keep):      # sorted: `keep` is a set, so iterating it
                                        # would reorder the artifact run to run
    sd, wj = _dollar_weight(a, b)
    edges.append({'a': a, 'b': b, 'shared': sc, 'jaccard': j,
                  'sharedDollars': round(sd), 'wjaccard': round(wj, 4),
                  'top': _top_shared(a, b)})

# Nodes that survive in at least one edge, with metadata for the viz.
node_ids = {e['a'] for e in edges} | {e['b'] for e in edges}

# Hand corrections for filers the raw contribution rows mislabel (the source
# data tags each gift with a party and we take the most common, but a handful
# of filers are recorded under the wrong one). Keyed by filerNumber.
PARTY_OVERRIDE = {
    '2009': 'REP',   # John C. (Jay) Morris, III — Republican LA state senator
}
def _party(fn):
    if fn in PARTY_OVERRIDE:
        return PARTY_OVERRIDE[fn]
    p = parties[fn].most_common(1)[0][0] if parties[fn] else 'OTH'
    return p if p in ('DEM', 'REP', 'IND', 'LBT', 'GRN') else 'OTH'
offices = load_offices()
nodes = []
for fn in sorted(node_ids, key=lambda f: (-raised[f], f)):   # filer breaks ties so
                                                            # equal-raised nodes keep
                                                            # a stable order (node_ids
                                                            # is a set)
    name = names[fn].most_common(1)[0][0] if names[fn] else f'Filer {fn}'
    n = {
        'id': fn,
        'name': name,
        'party': _party(fn),
        'raised': round(raised[fn]),
        'nDonors': len(donors[fn]),
    }
    office = office_of(name, offices)
    if office:
        n['office'] = office
    nodes.append(n)

out = {
    'generated': time.strftime('%Y-%m-%d'),
    'donor_identity': 'resolved' if raw2cid else 'raw-name',
    'params': {'top': TOP_N, 'min_shared': MIN_SHARED,
               'min_jaccard': MIN_JACCARD, 'max_per_node': MAX_PER_NODE,
               'edge_donors': EDGE_DONORS},
    'donors': donor_names,
    'nodes': nodes,
    'edges': edges,
}
# factions.json is the committed, deployed artifact and the page renders nothing
# without it, so never leave it empty or half-written.
if not nodes or not edges:
    sys.exit(f'Refusing to write {OUT}: built {len(nodes)} nodes / {len(edges)} edges '
             f'from {len(CYCLE_FILES)} year file(s) and {len(raised):,} filers. '
             f'Thresholds too high, or the cache is incomplete.')
tmp = OUT + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(out, f, separators=(',', ':'), ensure_ascii=False)
os.replace(tmp, OUT)

print(f'\nWrote {OUT}: {len(nodes)} nodes, {len(edges)} edges, '
      f'{len(donor_names)} named receipt donors '
      f'[{out["donor_identity"]} donors] ({time.time()-t0:.0f}s)')
nm = {n['id']: n['name'] for n in nodes}
print('Strongest shared-donor links:')
for e in sorted(edges, key=lambda e: -e['jaccard'])[:8]:
    print(f"  {nm[e['a']][:28]:<28} <-> {nm[e['b']][:28]:<28}  {e['shared']:>4} shared  J={e['jaccard']:.2f}")
