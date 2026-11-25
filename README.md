# Drupal core PHPStan baseline history

Charts the size of Drupal core's PHPStan baseline on the development branch over time, with minor
release tags, PHPStan level changes and links to the drupal.org issues behind large changes.
It also breaks down the current baseline by error identifier.

**Live site: https://mstrelan.github.io/drupal-phpstan-baseline/** (rebuilt daily)

## Build locally

```sh
./build.sh   # clone/fetch drupal/drupal, extract, write app/data.js (~35 s)
```

Then open `app/index.html` in a browser. No server is needed: the data is loaded as a plain script.

Needs `git` and `python3` (standard library only). The first run makes a blobless clone of
github.com/drupal/drupal in `data/drupal/`; later runs only fetch new history.

## How it works

- `build.sh` lists every commit on the first-parent history of `origin/main` that touched a baseline
  file, fetches all the needed file versions in one `git fetch --stdin`, and runs the extractor.
- `extract.py` parses `core/phpstan-baseline.neon` (until 2024-03) or `core/.phpstan-baseline.php`
  (after), sums the `count` values, diffs each commit against the previous one, and writes
  `app/data.json` / `app/data.js`.
- `app/index.html` is the whole UI: plain JS and ECharts, no build step.

## Deployment

`.github/workflows/pages.yml` rebuilds the data daily (and on push to `main`) and deploys `app/` to
GitHub Pages. In the repository settings, set **Pages → Source** to **GitHub Actions**.
