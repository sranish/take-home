# 100 apps: how ready are they to become agent toolkits?

Integration research on 100 apps for the Composio AI Product Ops take-home: auth, access, API surface, vendor MCP server and a buildability verdict for each, with evidence links and a verification log.

The deployed page is `out/index.html`.

## Deploy

The site is static and already built. `vercel.json` points Vercel at `out/`.

```
vercel --prod
```

Or import the repo at vercel.com/new with framework preset "Other". No build command is needed.

## Add the live and repo links to the page

Put your two URLs in `links.json`, then rebuild:

```
{
  "live_url": "https://your-project.vercel.app",
  "repo_url": "https://github.com/you/your-repo"
}
```

```
python3 build.py
```

This writes a "Live page" and "Source repo" line into the page header and makes the JSON and CSV links absolute, so they work when the HTML file is opened on its own. Leave a value empty to skip that link.

## Files

| File | What it is |
|---|---|
| `out/index.html` | The case study page, self-contained |
| `out/apps.json`, `out/apps.csv` | The dataset, machine-readable |
| `rows.psv` | Source of truth: one row per app with evidence URLs, status and flags |
| `pass1_priors.tsv` | First-pass answers from model memory, written before any lookup |
| `audit_sample.txt` | The 20 apps drawn for the blind audit (seeded random, two per category) |
| `audit_before.psv` | Main-run codes for that sample, frozen before corrections |
| `audit.psv` | The blind audit's answers, as returned |
| `audit_resolution.psv` | How each audit disagreement was settled, or that it is still open |
| `build.py` | Computes every number on the page and writes `out/` |
| `links.json` | Optional live and repo URLs for the page header |

`build.py` needs Python 3.9 or later and only the standard library.

## How the research was run

The research ran as an AI agent session with web search and page fetch, following this protocol:

1. Intake: the 100 rows from the brief (number, name, hint).
2. First pass with no browsing, saved to `pass1_priors.tsv`.
3. Identity check: confirm the official domain, flag look-alikes and legacy doc sites.
4. Docs-grounded pass: fetch the vendor auth page, the pricing or signup page, and the MCP page. Each fetch used a prompt of this shape:
   `From this page only; NOT STATED if absent: 1) auth methods 2) how to get credentials + free/trial/plan/approval gate 3) REST/GraphQL + breadth 4) official MCP server?`
5. Validation: vendor evidence links and a status on every row. A non-vendor source never makes a row Verified.
6. Recheck loop on conflicts, deprecations and non-vendor MCP claims.
7. Blind audit: a separate agent with no access to the findings re-researched the sample in `audit_sample.txt`. `build.py` compares codes by exact match.
8. MCP sweep: the audit showed "none found" was the weakest answer, so every row marked none, unchecked or unconfirmed (40 rows) was re-researched. 17 turned out to have a vendor MCP server.
9. Spot check: every sampled field checked twice against vendor pages, mismatches settled or flagged.
10. Synthesis by `build.py`.

## Known limits

- `build.py` rebuilds the page from the dataset. It does not re-run the research; that means running the protocol again in an agent session.
- No accounts were created and no live API calls were made, so "self-serve" means the vendor page says so.
- Pages were read through a fetch tool that summarises them and cuts very long ones.
- Three apps stayed unclear: fanbasis, Paygent Connect and iPayX.
