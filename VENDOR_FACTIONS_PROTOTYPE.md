# Vendor Factions — prototype spike

A sibling to the donor-factions graph. Donor-factions asks *which committees
draw from the same **donors***; this asks *which committees pay the same
**vendors*** — the media firms, pollsters, mail houses, and compliance shops
that quietly operate a bloc. It maps the **operative layer** the donor tool
can't see.

Status: **proof-of-concept**. `build_vendor_factions.py` produces the graph
(`vendor_factions.json`) and prints diagnostics; `vendor-factions.html` renders
it as an interactive force-directed network (a sibling of donor-factions'
`index.html` — same canvas engine, party/bloc coloring, search, zoom/pan). Its
hover card names the *vendors* two committees share, and **clicking a committee
opens a full shared-vendor sheet** — every operative it shares and with whom,
each vendor tagged with how many committees use it. Neither is possible on the
donor graph.

Each edge stores up to `EDGE_VENDORS` (40) shared vendors, ranked by **graph-glue**
(how many committee-pairs a vendor ties together) so recognizable operatives lead
over one-off local vendors; the exact shared *count* is always kept, and the sheet
discloses "+N more" for pairs past the cap.

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

Net effect across iterations: at the top 300, 58 nodes / 120 edges (naive) →
**39–42 nodes / ~35 edges**, every surviving edge a real operational tie.
Widening to the **top 500** committees (the current default) yields **~78 nodes /
63 edges** and surfaces regional machines invisible at 300 (below).

## What falls out (top 500 committees by service spend, 2000–2026)

- **The independent-expenditure air war (12–15 committees).** Gumbo PAC, RGA,
  Louisiana Federation for Children, Education Reform Now, Elizabeth Murrill,
  Protect Louisiana's Children, First Principles PAC, Keep the Lights On, Make
  Louisiana Great Again — glued by shared **TV-station ad buys** (WGNO, WVUE,
  WDSU, WBRZ, WAFB, KADN…) plus Public Policy Polling and Ampersand. These groups
  run the same air war.
- **The education-reform / business bloc (6–8 committees).** Stand for Children,
  The Fund for Louisiana's Future, Alliance for Better Classrooms, Lane Grigsby,
  David Mancuso LA Water — glued by pollster **Baselice & Associates** and
  **Innovative Advertising**.
- **The Landry / state-GOP bloc.** Jeff Landry, Republican Party of Louisiana,
  Cajun PAC II — glued by **Littlefield Consulting**, **Integram**, **Spartan
  Public Affairs**.
- **The Democratic legislative back office (pair).** House & Senate Democratic
  Campaign Committees — glued by **Michelle Brister's compliance consulting** and
  **Political CFOs**. (Donor-factions found this same pair on the *donor* side;
  here it's explained by shared back-office vendors.)
- **New at top 500 — regional machines:** a **Jefferson Parish bloc** (~11
  committees: Dominick Impastato, Arita Bohannan, John Fortunato, Deborah Villio,
  Keith Conley) glued by local shops (Christy Cannella, Pelican/Vivid Ink
  graphics, RSVP Decorating); a **Shreveport conservative cluster** (Robert Mills,
  John Nickelson) glued by **AX Media** + **WPA Intelligence** (a national GOP
  pollster) + KEEL-AM; and a **Lafourche officialdom cluster** (Sheriff Craig
  Webre, DA Kristine Russell), though that one leans on shared *civic
  sponsorships* (schools, the Chamber) more than paid operatives.
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

## Vendor identity resolution (conservative)

`resolve_key()` merges morphological variants of the same firm without collapsing
distinct ones — the balance the data demands. Probing showed the signal vendors
fragment (`LITTLEFIELD CONSULTING` / `CONSULTANTS` / `& ASSOCIATES CONSULTING` =
one firm split three ways, which weakened the flagship Landry-bloc edge), while
same-surname *different* firms sit right next to them (`ARSEMENT MEDIA GROUP` vs
`ARSEMENT PRODUCTIONS`; `SPARTAN PUBLIC AFFAIRS` vs the high-school
`SPARTANETTES`). So the rule folds `AND`/`&`, strips a leading `THE`, and peels
only trailing **firm-type** words (`CONSULTING`, `ASSOCIATES`, `PARTNERS`,
`COMPANY`…) — deliberately *not* `MEDIA`/`GROUP`/`PRODUCTIONS`, which distinguish
real siblings. Each cluster keeps its most-common spelling as the display label.
A tiny curated `_FIRM_CANON` handles same-entity/different-name cases the rules
can't infer (NCC Media rebranded as **Ampersand** → one vendor). Net effect:
Littlefield consolidates and pulls in Elizabeth Murrill; no false edges appear.

## Known limitations / next steps

- **Resolution is intentionally shallow.** It won't merge a firm that changed
  names or a genuine typo cluster beyond the `_FIRM_CANON` list. Extending toward
  a `build_donor_entities.py`-style resolver (with city/state corroboration) is
  the next accuracy lever if the graph is widened past the top 300.
- **Residual noise** is a few same-person committee pairs (a candidate's campaign
  + their PAC) and local caterer/venue pairs among co-located candidates. Minor;
  contained by `MIN_SHARED` + IDF.
- **Deploy wiring.** The viz reads `window.__GRAPH_DATA__` if present, else
  fetches `./vendor_factions.json` — so it works both as a standalone file (data
  inlined) and as a Pages/served page. If this graduates from prototype, add it
  to `pages.yml`'s uploaded root (or its own workflow) like `index.html`.
- **Category weighting** (favor `ADVERTISING`/`CONSULTING`/`POLLING` descriptions)
  could sharpen the operative signal further, but DF + IDF already do most of it.
