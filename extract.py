#!/usr/bin/env python3
"""Extract PHPStan baseline size history from drupal/drupal main first-parent history.

Usage: python3 extract.py <path-to-drupal-clone> <out.json>
"""
import json
import re
import subprocess
import sys
from collections import Counter

REPO = sys.argv[1]
OUT = sys.argv[2]
REF = "origin/main"
BASELINES = ["core/phpstan-baseline.neon", "core/.phpstan-baseline.php"]


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, check=True).stdout


def show(rev, path):
    r = subprocess.run(["git", "-C", REPO, "show", f"{rev}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


NEON_ENTRY = re.compile(r"^\t\t-\s*$", re.M)


def unescape_neon(s):
    # neon double-quoted string -> regex string (only backslash escapes matter here)
    return s.replace("\\\\", "\\")


def parse_neon(text):
    """Return Counter keyed by (identifier, message, path) -> count."""
    entries = Counter()
    for block in NEON_ENTRY.split(text)[1:]:
        msg = re.search(r"^\t\t\tmessage:\s*(.*)$", block, re.M)
        cnt = re.search(r"^\t\t\tcount:\s*(\d+)", block, re.M)
        path = re.search(r"^\t\t\tpath:\s*(.*)$", block, re.M)
        ident = re.search(r"^\t\t\tidentifier:\s*(.*)$", block, re.M)
        m = msg.group(1).strip() if msg else ""
        if m.startswith('"') or m.startswith("'"):
            m = m[1:-1]
        m = unescape_neon(m)
        entries[(ident.group(1).strip() if ident else None, m, path.group(1).strip() if path else "")] += int(cnt.group(1)) if cnt else 1
    return entries


PHP_ENTRY = re.compile(r"\$ignoreErrors\[\] = \[(.*?)\n\];", re.S)


def php_field(block, name):
    # One field per line; the last field in a block has no trailing newline.
    m = re.search(r"^\s*'" + name + r"' => (.*?),?$", block, re.M)
    return m.group(1) if m else None


# 2024-03 to 2025-03 baselines put the identifier in a comment instead of a field.
PHP_IDENT_COMMENT = re.compile(r"^\s*// identifier: (\S+)", re.M)


def parse_php(text):
    entries = Counter()
    for block in PHP_ENTRY.findall(text):
        msg = php_field(block, "message") or php_field(block, "rawMessage") or ""
        msg = msg.strip("'").replace("\\\\", "\\").replace("\\'", "'")
        ident = php_field(block, "identifier")
        if ident:
            ident = ident.strip("'")
        else:
            c = PHP_IDENT_COMMENT.search(block)
            ident = c.group(1) if c else None
        cnt = php_field(block, "count")
        path = php_field(block, "path") or ""
        # __DIR__ is core/, so this gives core-relative paths like the neon baseline ("modules/x/...", "../composer/...").
        path = re.sub(r"^__DIR__ \. '/", "", path).strip("'")
        entries[(ident, msg, path)] += int(cnt) if cnt else 1
    return entries


def area(path):
    parts = path.split("/")
    if parts[0] == ".." and len(parts) > 2:
        return "/".join(parts[:2])
    if parts[0] == "modules" and len(parts) > 1:
        return "modules/" + parts[1]
    if parts[0] == "lib" and len(parts) > 2:
        return "/".join(parts[:3])
    if parts[0] == "tests" and len(parts) > 2:
        return "/".join(parts[:3])
    return parts[0] if len(parts) > 1 else path


def message_key(msg):
    """Collapse a regex message into a rough category for neon-era entries."""
    m = msg.strip("#^$")
    m = m.replace("\\", "")
    m = re.sub(r"[A-Z][\w]*(?:\\[\w]+)+", "X", m)
    m = re.sub(r"\$\w+", "$x", m)
    m = re.sub(r"\b[\w]+::\w+\(\)", "X::m()", m)
    m = re.sub(r"\b\w+\(\)", "f()", m)
    return m[:90]


def version_of(rev):
    txt = show(rev, "core/lib/Drupal.php") or ""
    m = re.search(r"const VERSION = '([^']+)'", txt)
    return m.group(1) if m else None


def level_of(rev):
    txt = show(rev, "core/phpstan.neon.dist") or show(rev, "core/phpstan.neon") or ""
    m = re.search(r"^\s*level:\s*(\d+)", txt, re.M)
    return int(m.group(1)) if m else None


ISSUE_RE = re.compile(r"(?:Issue\s*)?#(\d{5,8})")


def main():
    log = git("log", "--first-parent", "--reverse", "--format=%H%x00%cI%x00%aI%x00%s", REF, "--", *BASELINES)
    rows = []
    prev = Counter()
    prev_fmt = None
    for line in log.splitlines():
        h, cdate, adate, subject = line.split("\x00")
        text = show(h, BASELINES[1])
        fmt = "php"
        if text is None:
            text = show(h, BASELINES[0])
            fmt = "neon"
        if text is None:
            entries = Counter()
            fmt = None
        else:
            entries = parse_php(text) if fmt == "php" else parse_neon(text)
        total = sum(entries.values())
        delta = total - sum(prev.values())

        # Breakdown of change. Skip on format switches (messages are re-escaped).
        by_ident, by_area = Counter(), Counter()
        if fmt == prev_fmt and fmt is not None:
            diff = Counter(entries)
            diff.subtract(prev)
            for (ident, msg, path), n in diff.items():
                if n == 0:
                    continue
                by_ident[ident or message_key(msg)] += n
                by_area[area(path)] += n
        top = lambda c: [[k, v] for k, v in sorted(c.items(), key=lambda kv: -abs(kv[1])) if v][:6]

        issue = ISSUE_RE.search(subject)
        rows.append({
            "hash": h,
            "date": cdate,
            "authored": adate,
            "subject": subject,
            "issue": int(issue.group(1)) if issue else None,
            "total": total,
            "delta": delta,
            "format": fmt,
            "version": version_of(h),
            "level": level_of(h),
            "byIdentifier": top(by_ident),
            "byArea": top(by_area),
        })
        prev, prev_fmt = entries, fmt
        print(f"{cdate[:10]} {total:6d} {delta:+6d} {subject[:80]}", file=sys.stderr)

    # Minor release tags: X.Y.0 plus the first alpha/beta of each minor if present.
    tags = []
    for t in git("tag", "-l").split():
        m = re.fullmatch(r"(\d+)\.(\d+)\.0", t)
        if m and int(m.group(1)) >= 9:
            d = git("log", "-1", "--format=%cI", t).strip()
            tags.append({"tag": t, "date": d})
    tags.sort(key=lambda t: t["date"])

    # Current overall stats
    head_ids = Counter()
    last = show(REF, BASELINES[1])
    if last:
        for (ident, msg, path), n in parse_php(last).items():
            head_ids[ident or "(none)"] += n

    json.dump({
        "generated": git("log", "-1", "--format=%cI", REF).strip(),
        "ref": REF,
        "commits": rows,
        "tags": tags,
        "currentByIdentifier": head_ids.most_common(),
    }, open(OUT, "w"), indent=1)


main()
