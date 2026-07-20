# Vendor Factions — prototype spike

A sibling to the donor-factions graph. Donor-factions asks *which committees
draw from the same **donors***; this asks *which committees pay the same
**vendors*** — the media firms, pollsters, mail houses, and compliance shops
that quietly operate a bloc. It maps the **operative layer** the donor tool
can't see.

Status: **proof-of-concept**. `build_vendor_factions.py` produces the graph
(`vendor_factions.json`) and prints diagnostics. No viz yet — the next step is
to point donor-factions' `index.html` force-directed renderer at this output.

## Why it isn't a find-and-replace of build_factions.py

A shared vendor is two different signals mixed together, and the naive version
drowns in the wrong one:

1. **Commodity vendors** — Office Depot (1,765 committees), Walmart, USPS,
   Facebook, the banks, the Secretary of State filing window. Everyone pays
   these; they carry no factional signal and, left in, bury the graph.
2. **Outbound contributions disguised as expenditures** — ~18% of expenditure
   rows are the committee giving money *away* (to candidates, other PACs,
   charities). Most carry a blank description, so a category filter misses them.
   Left in, trade-association PACs that merely *donate to the same legislators*
   look "allied" — a huge false signal that dominated the first run.

The build handles both:

- **TF-IDF framing.** Committees are documents, vendors are terms. Vendors paid
  by ≥ `STOPWORD_DF` (100) committees are dropped as stopwords; edges are an
  **IDF-weighted Jaccard**, so a rare shared consultant outweighs a shared post
  office.
- **Political-recipient filter.** Any recipient that *is* a known
  committee/candidate is dropped — matched against `la_filer_lookup.json` by
  full name, by a committee-name regex (`PAC`, `CAMPAIGN`, `FRIENDS OF`, `FOR
  SENATE`…), and — crucially — by **surname + given-token overlap**, which
  catches Louisiana's middle-name usage (the ballot files `ROBERT BRET ALLAIN`
  but the check is written to `BRET ALLAIN`). This single fix collapsed the
  trade-association false cluster from the graph.

Net effect across iterations: 58 nodes / 120 edges (naive) → **39 nodes / 30
edges**, and every surviving edge is a real operational tie.

## What falls out (top 300 committees by service spend, 2000–2026)

- **The independent-expenditure air war (12 committees).** Gumbo PAC, RGA,
  Louisiana Federation for Children, Louisiana Kids Matter, Protect Louisiana's
  Children, First Principles PAC, Keep the Lights On, Make Louisiana Great
  Again — glued by shared **TV-station ad buys** (WGNO, WVUE, WDSU, WBRZ, WAFB,
  KADN…) plus Public Policy Polling and NCC Media. These groups run the same air
  war.
- **The education-reform / business bloc (6 committees).** Stand for Children,
  The Fund for Louisiana's Future, Alliance for Better Classrooms, Lane Grigsby
  — glued by pollster **Baselice & Associates** and **Innovative Advertising**.
- **The Landry / state-GOP bloc (3 committees).** Jeff Landry, Republican Party
  of Louisiana, Cajun PAC II — glued by **Littlefield Consultants**, **Integram**,
  **Spartan Public Affairs**.
- **The Democratic legislative back office (pair).** House & Senate Democratic
  Campaign Committees — glued by **Michelle Brister's compliance consulting** and
  **Political CFOs**. (Donor-factions found this same pair on the *donor* side;
  here it's explained by shared back-office vendors.)
- Named vendors like **Huckaby Davis Lisker** (GOP compliance), **Go Big Media**,
  **People Who Think**, **Arsement Media Group** surface as genuine shared
  operatives.

## Run it

```bash
# Needs the campaign-finance repo's expenditure cache (auto-found as a sibling;
# override with --cache or $LA_CACHE). Stdlib only.
python3 build_vendor_factions.py
python3 build_vendor_factions.py --top 300 --stopword-df 100 --min-shared 3 --min-wjaccard 0.06
```

Prints: strongest shared-vendor links (with the vendors that glue each), the
vendors gluing the most committee-pairs (the operative hubs), and the connected
components (candidate blocs). Writes `vendor_factions.json` (nodes + edges).

## Known limitations / next steps

- **Vendor identity is only lightly normalized** (punctuation + corporate-suffix
  strip + a tiny alias map). `USPS` vs `UNITED STATES POSTAL SERVICE` don't merge
  — harmless here because both are commodity stopwords, but a *boutique* vendor
  split across spellings undercounts. A small org-variant resolver (modeled on
  `build_donor_entities.py`) is the main accuracy lever.
- **Residual noise** is a few same-person committee pairs (a candidate's campaign
  + their PAC) and local caterer/venue pairs among co-located candidates. Minor;
  contained by `MIN_SHARED` + IDF.
- **No viz yet.** Reuse donor-factions' `index.html` renderer; the node/edge
  schema is intentionally close (`id, name, party, spend, nVendors` / `a, b,
  shared, jaccard, wjaccard, topVendors`). `topVendors` on each edge lets a hover
  card name *why* two committees are tied — a feature the donor graph lacks.
- **Category weighting** (favor `ADVERTISING`/`CONSULTING`/`POLLING` descriptions)
  could sharpen the operative signal further, but DF + IDF already do most of it.
