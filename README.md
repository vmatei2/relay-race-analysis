# Relay race analysis

An interactive report for **Tracklife London vs Run for Will-Being** at Endure Relays London,
3 October 2026. Python extracts and validates the official timing data, then generates a
portable static webpage. The browser handles chart interaction; no Python server is required
for hosting.

## Run locally

The project uses **Python 3.14.8**, the latest stable release at creation, with `uv` and a
project-local `.venv`. Python 3.15 is still a prerelease as of 4 October 2026.
[Python release list](https://www.python.org/downloads/).

```sh
uv sync --locked
uv run relay-race-analysis build
uv run relay-race-analysis serve
```

Open <http://127.0.0.1:8765>. You can also open `site/index.html` directly in your browser;
data is embedded and Plotly is bundled locally, so the report works offline. Keep the
generated `site/` folder together when moving it.

Chrome or Chromium is required **during the build** to generate the PNG downloads with
Kaleido. The report itself needs only a browser. If Chrome is not installed, run
`uv run plotly_get_chrome` to install the version used for image generation.

If an older `uv` cannot discover Python 3.14.8, install it using current official metadata:

```sh
uv python install 3.14.8 --python-downloads-json-url https://raw.githubusercontent.com/astral-sh/uv/main/crates/uv-python/download-metadata.json
```

The checked-in HTML snapshots let builds reproduce the analysis without contacting the
timing website. To fetch an updated official result deliberately:

```sh
uv run relay-race-analysis build --refresh
```

`race.toml` records the result URLs, team identities, lap distance, date and four-hour cutoff.
This first-edition report and its editorial narrative are specific to this race and these teams.

## What the report shows

- An animated race replay with playback controls, runner handovers and recorded split gaps.
- Cumulative lead at the same completed lap: how the 73-second margin developed.
- A lap explorer linked to the lead chart and the complete timing table.
- Runner averages, pacing consistency and first-to-last changes, using all laps.
- Downloadable lap CSV, head-to-head CSV and analysis JSON.

The race story highlights Tracklife leading at every completed lap, gaining time on 21
of the 29 laps, reaching a 97-second lead after lap 23 and winning by 73 seconds.
Omar’s lap 13 gained 19 seconds; his final lap added another 18 seconds to the lead.

The lead chart’s PNG download shows the complete race, independently of browser zoom
or lap selection. Replay movement assumes steady speed within each recorded lap; the
positions and distances between lap finishes are estimates.

## Timing conventions

Published cumulative times are the source of truth for reconciliation. Individual lap
durations are successive differences from those times; the first lap starts at elapsed zero.
The provider's separately displayed leg durations sometimes differ by one second, likely
because of rounding or truncation. Both values are retained in the full CSV and JSON.

Positive gain and positive lead favour Tracklife. The gap compares teams at equal distances,
not their physical separation at the same instant. Summing the separately displayed leg
times instead would fail to reproduce the official total.

Both teams completed 29 laps (72.5 km at the supplied 2.5 km distance). At four hours,
both had completed 28 laps and were on lap 29; the report includes that lap as the official
result does. The team confirmed that the opening lap was the same route and distance.

Runner attribution comes from the source, including Will-Being's irregular rotation.
No assumption is made that corresponding team laps represent the same runner matchup.
Last-to-first time change is descriptive: this dataset cannot separate fatigue, tactics,
handover delays, congestion, or within-lap pacing.

## Publish with GitHub Pages

The workflow in `.github/workflows/pages.yml` validates the data, builds the report and
publishes the generated `site/` directory. Only generated report assets and exports are
served; the raw timing-page snapshots remain in the repository.

1. Create a GitHub repository and push this local repository to its `main` branch.
2. In the repository's **Settings → Pages**, select **GitHub Actions** as the build source.
3. Run **Publish race report** from the Actions tab, or push a subsequent commit to `main`.
4. Open the deployment URL shown by the workflow.

A public repository can use GitHub Pages on GitHub Free. Private-repository support depends
on your GitHub plan. [GitHub Pages documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

For a quick alternative, upload the generated `site/` folder through
[Netlify Drop](https://docs.netlify.com/start/quickstarts/netlify-drop-quickstart/).

## Checks

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests
```

Tests cover source attribution, incomplete/missing laps, timing inconsistencies,
the 73-second reconciliation, the pivotal lap-8 loss, the cutoff, differing runner outing
counts and the comparison's sign convention. Browser verification checks the replay, chart rendering, lap selection, runner statistics
and mobile layout. The replay timing test uses Node when available.

## Files

- `src/relay_race_analysis/`: scraper, timing analysis, report generation, static assets and CLI.
- `data/raw/`: original result snapshots and fetch provenance.
- `data/laps.json`: normalised timing records, including reported and derived durations.
- `tests/`: checks against the saved real results.
- `site/`: generated report (ignored by Git; reproducibly generated in deployment).

Source results: [overall](https://mytime.kronosports.uk/results.aspx?CId=20177&RId=758&EId=1),
[Tracklife](https://mytime.kronosports.uk/myresults.aspx?uid=20177-758-1-502028),
[Will-Being](https://mytime.kronosports.uk/myresults.aspx?uid=20177-758-1-502014).
