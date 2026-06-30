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
import gzip, json, os, glob, sys, time
from collections import defaultdict, Counter
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))

def _arg(flag, default):
    return type(default)(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default

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

TOP_N        = _arg('--top', 250)         # filers in the graph (by lifetime raised)
MIN_SHARED   = _arg('--min-shared', 25)   # an edge needs at least this many shared donors
MIN_JACCARD  = _arg('--min-jaccard', 0.04)  # ...and this overlap (controls for size)
MAX_PER_NODE = _arg('--max-per-node', 6)  # keep each node's strongest links

if not os.path.isdir(CACHE):
    sys.exit(f'No .la_cache at {CACHE!r}. Pass --cache <path> or set $LA_CACHE.')

# ── resolved donor identity ─────────────────────────────────────────────────
# Invert la_donor_entities: raw contributor spelling (UPPER) -> cluster id.
# Single-variant clusters store their lone raw as `name`; multi list every raw.
def load_donor_map():
    p = os.path.join(CACHE, 'la_donor_entities.json.gz')
    if not os.path.exists(p):
        print('  note: la_donor_entities.json.gz absent — falling back to raw names')
        return None
    with gzip.open(p, 'rt', encoding='utf-8') as f:
        donors = json.load(f)['donors']
    raw2cid = {}
    for cid, d in donors.items():
        if d.get('variants'):
            for raw in d['variants']:
                raw2cid[raw] = cid
        else:
            raw2cid[d['name']] = cid
    return raw2cid

raw2cid = load_donor_map()
def donor_id(raw_upper):
    return raw2cid.get(raw_upper, raw_upper) if raw2cid else raw_upper

def _rows():
    for path in sorted(glob.glob(os.path.join(CACHE, 'contributions_yr*.json.gz'))):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    yield json.loads(line)
                except Exception:
                    continue

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

# Pass 2: resolved-donor sets for the top filers + display name/party.
donors  = defaultdict(set)        # filer -> {donor cluster id}
names   = defaultdict(Counter)    # filer -> {candidate spelling: count}
parties = defaultdict(Counter)    # filer -> {party: count}
donor_to_filers = defaultdict(set)
for r in _rows():
    fn = (r.get('filerNumber') or '').strip()
    if fn not in top:
        continue
    if r.get('candidate'): names[fn][r['candidate']] += 1
    if r.get('party'):     parties[fn][r['party']] += 1
    if not _is_donor_gift(r):
        continue
    raw = (r.get('contributor') or '').strip().upper()
    if not raw or raw == 'UNKNOWN':
        continue
    cid = donor_id(raw)
    donors[fn].add(cid)
    donor_to_filers[cid].add(fn)
print(f'Pass 2: donor sets built for {len(donors)} filers ({time.time()-t0:.0f}s)')

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
edges = [{'a': a, 'b': b, 'shared': sc, 'jaccard': j} for (a, b, sc, j) in keep]

# Nodes that survive in at least one edge, with metadata for the viz.
node_ids = {e['a'] for e in edges} | {e['b'] for e in edges}
def _party(fn):
    p = parties[fn].most_common(1)[0][0] if parties[fn] else 'OTH'
    return p if p in ('DEM', 'REP', 'IND', 'LBT', 'GRN') else 'OTH'
nodes = [{
    'id': fn,
    'name': (names[fn].most_common(1)[0][0] if names[fn] else f'Filer {fn}'),
    'party': _party(fn),
    'raised': round(raised[fn]),
    'nDonors': len(donors[fn]),
} for fn in sorted(node_ids, key=lambda f: -raised[f])]

out = {
    'generated': time.strftime('%Y-%m-%d'),
    'donor_identity': 'resolved' if raw2cid else 'raw-name',
    'params': {'top': TOP_N, 'min_shared': MIN_SHARED,
               'min_jaccard': MIN_JACCARD, 'max_per_node': MAX_PER_NODE},
    'nodes': nodes,
    'edges': edges,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, separators=(',', ':'), ensure_ascii=False)

print(f'\nWrote {OUT}: {len(nodes)} nodes, {len(edges)} edges '
      f'[{out["donor_identity"]} donors] ({time.time()-t0:.0f}s)')
nm = {n['id']: n['name'] for n in nodes}
print('Strongest shared-donor links:')
for e in sorted(edges, key=lambda e: -e['jaccard'])[:8]:
    print(f"  {nm[e['a']][:28]:<28} <-> {nm[e['b']][:28]:<28}  {e['shared']:>4} shared  J={e['jaccard']:.2f}")
