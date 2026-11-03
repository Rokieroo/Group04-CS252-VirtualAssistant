# Data Directory

This directory stores datasets and lookup tables used by the Virtual Assistant.

## Datasets

### `offices.csv`
Contains directory information for campus offices:
- **`name`**: Office name (e.g., `Training Office`, `Student Affairs`, `Library`, `IT Helpdesk`).
- **`room`**: Location room code (e.g., `I.101`, `B.201`).
- **`hours`**: Operating hours (e.g., `Mon-Fri 07:30-16:30`).

### `catalog/*.yaml`
Curated internal resources used by `app.search.CatalogSearch` (spec 11.2).
`CatalogSearch` accepts a top-level list or a mapping with `resources`, `items`,
`entries`, or `catalog`. Each resource needs at least `title` and `url`; the
optional `kind`, `lang`, `provider`, `snippet`, and `tags` fields improve
matching. The catalog is always available, so it remains the fallback when an
external search provider fails or runs out of quota.

### `policy/*.txt`
Domain policy used by `app.vetting` (spec 11.3-11.4, safeguard 4). One domain
per line, `#` starts a comment, and an entry also covers its subdomains
(`edu.vn` matches `fit.hcmus.edu.vn`). `name.*` matches the name under any
suffix, for mirrors that keep changing TLD (`libgen.*`).
- **`blocklist.txt`**: never shown or fetched (pirated material, answer dumps).
  It wins over both allowlists.
- **`allowlist_tier1.txt`**: authority 1.0 (universities, OER, official docs).
- **`allowlist_tier2.txt`**: authority 0.7 (publishers, vetted platforms).
- **`paywall.txt`**: login/paywall sites; their pages never pass the fetch check.

The lists are read once per process, so restart the API after editing them.
