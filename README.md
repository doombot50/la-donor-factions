# Louisiana's Donor Factions

A small, single-story spin-off of the campaign-finance dashboard — in the spirit
of the pay-to-play tool. It answers one question: **which Louisiana political
committees draw from the same donors?**

Two committees that share donors are, in money terms, allied. This finds the top
filers by lifetime raised, computes how many donors each *pair* shares plus the
**Jaccard overlap** (which controls for fundraising size, so a giant committee
doesn't look "allied" with everyone just by being big), and renders the result as
a force-directed network. Clusters are de-facto money factions.

## What it surfaces

Real structure falls right out, e.g.:

- **North / South / East / West PAC** cluster tightly (~45–49% donor overlap, 700+
  shared donors each) — a coordinated regional-PAC family pooling the same donors.
- **SEAPAC ↔ Crescent River Port Pilots** (41%) — a maritime/port industry bloc.
- **Senate ↔ House Democratic Campaign Committees** — the partisan legislative pool.

Current build: **138 committees, 382 shared-donor links**, top 250 filers by lifetime
raised (2000–2026).

## Donor identity (the important part)

The rows carry no donor ID, so "the same donor" is a matching problem. Rather than
match raw name strings, this reuses the campaign-finance project's **resolved donor
entities** (`la_donor_entities.json.gz`): nickname-folded names clustered within
last-name + generational suffix + ZIP, with organization spelling-variants merged.
So:

- "Bob" and "Robert Smith" at the same ZIP count as **one** donor (less under-counting);
- two different "John Smith"s in **different** ZIPs don't collide (less over-counting);
- 20 spellings of Chevron's PAC are **one** donor.

Committee-to-committee transfers and filing fees are excluded — these are shared
*donors*, not money committees pass between themselves. The figure is **lifetime**:
every cycle 2000–2026.

## Run it

```bash
# 1. Build the graph from the campaign-finance repo's .la_cache.
#    Auto-finds the cache as a sibling dir; override with --cache or $LA_CACHE.
py build_factions.py
#    e.g. from a separate checkout:
#    py build_factions.py --cache "../Claude Code/.la_cache"
#    Tuning: --top 350  --min-shared 25  --min-jaccard 0.04  --max-per-node 6

# 2. Serve the static page (no dependencies, no build step).
py -m http.server 8792 --directory .
# → http://localhost:8792
```

Hover a node for its party, money, and top shared-donor allies; click to isolate
its neighborhood; scroll to zoom, drag to pan. The search box (top right) flies to
a committee by name, and focusing a node puts its filer id in the URL hash, so a
link like `…/#1144` opens with that committee focused — shareable permalinks.

The legend toggles between two colorings: **Party** (registered party of the filer)
and **Faction** — blocs *discovered* from the money itself via Jaccard-weighted
label propagation over the shared-donor graph. A bloc is named for its story when
it has one: if at least half its members hold the same class of office it becomes
"Sheriffs", "Judges", or "Republican legislators" (party prefixed when ≥⅔ share
one; offices come from SoS candidacies joined in by `build_factions.py`).
Otherwise — statewide personalities, PAC networks — it's named for its **hub**,
the member most connected to the rest of the bloc under the active edge weight
(e.g. the John Alario, Jr. bloc), with the hub's surname appended when two blocs
would otherwise share a name. Click a faction row to spotlight just that bloc;
<kbd>Esc</kbd> resets everything.

## Deploy (GitHub Pages)

Pure static — `index.html` + `factions.json` at the repo root. `.github/workflows/pages.yml`
uploads the root on every push to `main`.

1. Create an empty GitHub repo (e.g. `doombot50/la-donor-factions`) and push this.
2. Repo **Settings → Pages → Source: GitHub Actions**.
3. The `CNAME` file pins **factions.charliestephens.xyz**; add a DNS record at
   Porkbun: `CNAME  factions → doombot50.github.io`.

`factions.json` is committed, so the site deploys without the data cache. Regenerate
it (step 1 above) and push whenever the underlying data refreshes.

## Next steps

- **Candidates-only view:** the default includes major PACs and party committees
  (central hubs). A toggle could filter to filers that actually appeared on a ballot
  (join to the SoS election results) for a cleaner politician-only faction map.
- **Weighted overlap:** edges count shared donors equally; weighting by shared
  dollars would surface big-money alliances over small-dollar ones.
