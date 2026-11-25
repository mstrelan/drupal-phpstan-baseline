#!/usr/bin/env bash
# Refresh data: update the blobless clone, fetch baseline blobs in one batch, extract, write app/data.js.
set -euo pipefail
cd "$(dirname "$0")"
[ -d data/drupal ] || git clone --filter=blob:none --no-checkout https://github.com/drupal/drupal.git data/drupal
git -C data/drupal fetch -q --tags origin
FILES=(core/phpstan-baseline.neon core/.phpstan-baseline.php core/lib/Drupal.php core/phpstan.neon core/phpstan.neon.dist)
git -C data/drupal log --first-parent --format=%H origin/main -- core/phpstan-baseline.neon core/.phpstan-baseline.php core/phpstan.neon core/phpstan.neon.dist \
  | while read -r c; do for f in "${FILES[@]}"; do git -C data/drupal rev-parse -q --verify "$c:$f" 2>/dev/null || true; done; done \
  | sort -u | git -C data/drupal -c fetch.negotiationAlgorithm=noop fetch -q --no-tags --no-write-fetch-head --filter=blob:none origin --stdin
python3 extract.py data/drupal app/data.json
{ printf 'window.BASELINE_DATA = '; cat app/data.json; echo ';'; } > app/data.js
echo "Done. Open app/index.html in a browser."
