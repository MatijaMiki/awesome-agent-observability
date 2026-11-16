#!/usr/bin/env python3
"""Mechanical health check for every entry in README.md.

GitHub-hosted entries are checked through the GitHub API: gone, archived,
renamed or transferred, past the 12-month bar, or without a license. Other
entries get an HTTP check of their link: dead, erroring, or permanently
redirected (reported with the new URL). A non-GitHub entry that also links a
GitHub repository in the same line gets the repository checks too. It cannot
judge quality or whether a description is still accurate; that is the
hands-on re-audit.

Usage: GITHUB_TOKEN=... python3 scripts/audit.py [README.md] [--status-file PATH]
Prints a Markdown report. With --status-file, writes "actionable" or "clean"
to PATH so the workflow knows whether to open, update, or close the issue.
Exit code is 0 unless the GitHub API is unreachable for every repository.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

STALE_DAYS = 365
WARN_DAYS = 270
# The comparison table carries a "Last verified YYYY-MM-DD" note; past this age
# the audit asks for it to be re-verified.
TABLE_MAX_AGE_DAYS = 90
TABLE_VERIFIED = re.compile(r"Last verified (?P<date>\d{4}-\d{2}-\d{2})")

HTTP_TIMEOUT_SECONDS = 20
GITHUB_TIMEOUT_SECONDS = 30
MAX_REDIRECTS = 5
USER_AGENT = "awesome-list-audit"
HTTP_OK = 200
HTTP_MULTIPLE_CHOICES = 300
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_GONE = 410
PERMANENT_REDIRECTS = {301, 308}
TEMPORARY_REDIRECTS = {302, 303, 307}
# Some sites refuse HEAD; retry those with GET before judging the link.
RETRY_WITH_GET = {HTTP_FORBIDDEN, HTTP_METHOD_NOT_ALLOWED}
DEAD = {HTTP_NOT_FOUND, HTTP_GONE}
NETWORK_ERROR = None  # status returned by fetch when no HTTP response arrived

SEVERITY_ORDER = ["remove", "fix", "check", "watch", "manual"]
# Severities that need someone to act; "manual" is informational only.
ACTIONABLE = {"remove", "fix", "check", "watch"}
STATUS_ACTIONABLE = "actionable"
STATUS_CLEAN = "clean"

ENTRY = re.compile(r"^- \[(?P<name>[^\]]+)\]\((?P<url>https?://[^)]+)\)")
REPO = re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+)")
LINK = re.compile(r"\]\((?P<url>https?://[^)]+)\)")
# Repositories with no repo-level license whose listed entry is a folder that
# carries its own LICENSE file. Reported as "manual" so the weekly issue does
# not stay open; re-read the folder's license at each hands-on pass.
PER_FOLDER_LICENSE = {
    "anthropics/skills": "no repo-level license; skills/skill-creator/LICENSE.txt is Apache-2.0",
}


def repo_of(url):
    r = REPO.match(url)
    return (r["owner"], r["repo"]) if r else None


def parse(text):
    """Return [(name, url, (owner, repo) or None)] for each list entry."""
    return [(name, url, repo) for name, url, repo, _ in parse_entries(text)]


def parse_entries(text):
    """Return [(name, url, repo, extra_repos)] for each list entry.

    extra_repos lists the GitHub repositories linked later in the line of a
    non-GitHub entry (for example MLflow Tracing's docs link plus mlflow/mlflow).
    """
    out = []
    for line in text.splitlines():
        m = ENTRY.match(line)
        if not m:
            continue
        repo = repo_of(m["url"])
        extra = []
        if repo is None:
            for link in LINK.finditer(line[m.end():]):
                r = repo_of(link["url"])
                if r and r not in extra:
                    extra.append(r)
        out.append((m["name"], m["url"], repo, extra))
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_fetch(url, method):
    """Return (status, Location header) for one request, without following redirects."""
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    try:
        with _OPENER.open(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            return resp.status, resp.headers.get("Location")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location")
    except (urllib.error.URLError, OSError):
        return NETWORK_ERROR, None


def check_url(url, fetch=http_fetch):
    """Return a list of (severity, message) findings for one non-GitHub link.

    fetch(url, method) -> (status or None, location) does one request without
    following redirects; tests pass a fake so no network is used.
    """
    current, permanent = url, False
    for _ in range(MAX_REDIRECTS + 1):
        status, location = fetch(current, "HEAD")
        if status in RETRY_WITH_GET:
            status, location = fetch(current, "GET")
        if status is NETWORK_ERROR:
            return [("check", f"{current} did not respond")]
        if status in PERMANENT_REDIRECTS | TEMPORARY_REDIRECTS and location:
            permanent = permanent or status in PERMANENT_REDIRECTS
            current = urllib.parse.urljoin(current, location)
            continue
        if HTTP_OK <= status < HTTP_MULTIPLE_CHOICES:
            if permanent and current != url:
                return [("fix", f"permanently redirects to {current}; update the link")]
            return []
        if status in DEAD:
            return [("remove", f"{current} returns {status}")]
        return [("check", f"{current} returns {status}")]
    return [("check", f"{url} redirects more than {MAX_REDIRECTS} times")]


def table_age(text, now):
    """Return findings when the comparison table's verification date is too old."""
    m = TABLE_VERIFIED.search(text)
    if not m:
        return []
    verified = dt.datetime.strptime(m["date"], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    age = (now - verified).days
    if age > TABLE_MAX_AGE_DAYS:
        return [("check", f"comparison table last verified {age} days ago ({m['date']}); re-verify and update the date")]
    return []


def is_actionable(report):
    return any(sev in ACTIONABLE for sev, _, _ in report)


def gh_get(path):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", ""),
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=GITHUB_TIMEOUT_SECONDS) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, None


def judge(name, owner, repo, meta, last_commit, now):
    """Return a list of (severity, message) findings for one entry."""
    found = []
    full = meta["full_name"]
    if full.lower() != f"{owner}/{repo}".lower():
        found.append(("fix", f"moved to `{full}`; update the link"))
    if meta.get("archived"):
        found.append(("remove", "repository is archived"))
    if meta.get("disabled"):
        found.append(("remove", "repository is disabled"))
    if last_commit is None:
        found.append(("check", "could not read the last commit"))
    else:
        age = (now - last_commit).days
        if age > STALE_DAYS:
            found.append(("remove", f"last commit {age} days ago ({last_commit:%Y-%m-%d})"))
        elif age > WARN_DAYS:
            found.append(("watch", f"last commit {age} days ago; goes stale in {STALE_DAYS - age} days"))
    if not (meta.get("license") or {}).get("spdx_id"):
        note = PER_FOLDER_LICENSE.get(f"{owner}/{repo}".lower())
        if note:
            found.append(("manual", note))
        else:
            found.append(("check", "no license detected by GitHub"))
    return found


def last_commit_date(owner, repo):
    status, data = gh_get(f"/repos/{owner}/{repo}/commits?per_page=1")
    if status != HTTP_OK or not data:
        return None
    return dt.datetime.fromisoformat(data[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))


def check_repo(name, owner, repo, now):
    """Return (findings, api_failed) for one GitHub repository."""
    status, meta = gh_get(f"/repos/{owner}/{repo}")
    if status == HTTP_NOT_FOUND:
        return [("remove", f"https://github.com/{owner}/{repo} returns 404")], False
    if status != HTTP_OK:
        return [("check", f"GitHub API returned {status} for {owner}/{repo}")], True
    return judge(name, owner, repo, meta, last_commit_date(owner, repo), now), False


def audit(text, now, repo_check=check_repo, url_check=check_url):
    """Return (entries, report, api_failures, repos_checked)."""
    report, api_failures, repos_checked = [], 0, 0
    entries = parse_entries(text)
    for name, url, repo, extra in entries:
        if repo is None:
            report.extend((sev, name, msg) for sev, msg in url_check(url))
        for owner, rname in [repo] if repo else extra:
            repos_checked += 1
            found, failed = repo_check(name, owner, rname, now)
            api_failures += failed
            report.extend((sev, name, msg) for sev, msg in found)
    report.extend((sev, "Comparison table", msg) for sev, msg in table_age(text, now))
    return entries, report, api_failures, repos_checked


def render(entries, report, now):
    lines = [f"# Entry audit, {now:%Y-%m-%d}", "", f"{len(entries)} entries checked, {len(report)} findings.", ""]
    for sev in SEVERITY_ORDER:
        rows = [r for r in report if r[0] == sev]
        if rows:
            lines += [f"## {sev}", ""] + [f"- **{name}**: {msg}" for _, name, msg in rows] + [""]
    return "\n".join(lines)


def main(argv):
    args = list(argv)
    status_file = None
    if "--status-file" in args:
        i = args.index("--status-file")
        status_file = args[i + 1]
        del args[i : i + 2]
    path = args[0] if args else "README.md"
    now = dt.datetime.now(dt.timezone.utc)
    with open(path) as f:
        entries, report, api_failures, repos_checked = audit(f.read(), now)
    print(render(entries, report, now))
    if status_file:
        with open(status_file, "w") as f:
            f.write(STATUS_ACTIONABLE if is_actionable(report) else STATUS_CLEAN)
    return 1 if repos_checked and api_failures == repos_checked else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
