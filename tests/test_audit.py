import datetime as dt
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, "scripts")
import audit

NOW = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc)


def meta(**kw):
    base = {"full_name": "o/r", "archived": False, "disabled": False, "license": {"spdx_id": "MIT"}}
    base.update(kw)
    return base


class Parse(unittest.TestCase):
    def test_entries(self):
        text = "- [A](https://github.com/o/a) - x.\n- [B](https://jetty.io) - y.\nprose [C](https://github.com/o/c)\n"
        self.assertEqual(
            audit.parse(text),
            [("A", "https://github.com/o/a", ("o", "a")), ("B", "https://jetty.io", None)],
        )

    def test_toc_anchors_are_not_entries(self):
        self.assertEqual(audit.parse("- [Section](#section)\n"), [])

    def test_subpath_url(self):
        (e,) = audit.parse("- [S](https://github.com/o/community/blob/main/p.md) - z.\n")
        self.assertEqual(e[2], ("o", "community"))


class Judge(unittest.TestCase):
    def j(self, m, age=10):
        return audit.judge("n", "o", "r", m, NOW - dt.timedelta(days=age), NOW)

    def test_clean(self):
        self.assertEqual(self.j(meta()), [])

    def test_archived(self):
        self.assertIn("remove", [s for s, _ in self.j(meta(archived=True))])

    def test_renamed(self):
        self.assertEqual(self.j(meta(full_name="new/r"))[0][0], "fix")

    def test_stale_and_watch(self):
        self.assertEqual(self.j(meta(), age=400)[0][0], "remove")
        self.assertEqual(self.j(meta(), age=300)[0][0], "watch")
        self.assertEqual(self.j(meta(), age=365), [("watch", "last commit 365 days ago; goes stale in 0 days")])

    def test_no_license(self):
        self.assertEqual(self.j(meta(license=None))[0][0], "check")



def fake_fetch(responses):
    """Return a fetch(url, method) that answers from {(url, method): (status, location)}.

    A missing GET falls back to the HEAD answer; no network is used.
    """
    calls = []

    def fetch(url, method):
        calls.append((url, method))
        if (url, method) in responses:
            return responses[(url, method)]
        return responses[(url, "HEAD")]

    fetch.calls = calls
    return fetch


class CheckUrl(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(audit.check_url("https://a.dev/x", fake_fetch({("https://a.dev/x", "HEAD"): (200, None)})), [])

    def test_permanent_redirect_names_new_url(self):
        fetch = fake_fetch({
            ("https://www.a.dev/docs", "HEAD"): (308, "https://docs.a.dev/docs"),
            ("https://docs.a.dev/docs", "HEAD"): (200, None),
        })
        self.assertEqual(
            audit.check_url("https://www.a.dev/docs", fetch),
            [("fix", "permanently redirects to https://docs.a.dev/docs; update the link")],
        )

    def test_relative_permanent_redirect(self):
        fetch = fake_fetch({
            ("https://a.dev/old", "HEAD"): (301, "/new"),
            ("https://a.dev/new", "HEAD"): (200, None),
        })
        self.assertEqual(audit.check_url("https://a.dev/old", fetch)[0][1], "permanently redirects to https://a.dev/new; update the link")

    def test_temporary_redirect_is_clean(self):
        fetch = fake_fetch({
            ("https://a.dev/latest", "HEAD"): (302, "https://a.dev/v2"),
            ("https://a.dev/v2", "HEAD"): (200, None),
        })
        self.assertEqual(audit.check_url("https://a.dev/latest", fetch), [])

    def test_dead_link(self):
        fetch = fake_fetch({("https://a.dev/x", "HEAD"): (404, None)})
        self.assertEqual(audit.check_url("https://a.dev/x", fetch), [("remove", "https://a.dev/x returns 404")])

    def test_any_head_error_retries_with_get(self):
        for code in (400, 404, 501):
            fetch = fake_fetch({("https://a.dev/x", "HEAD"): (code, None), ("https://a.dev/x", "GET"): (200, None)})
            self.assertEqual(audit.check_url("https://a.dev/x", fetch), [], code)

    def test_mixed_chain_suggests_last_permanent_target(self):
        fetch = fake_fetch({
            ("https://a.dev/old", "HEAD"): (301, "https://a.dev/new"),
            ("https://a.dev/new", "HEAD"): (302, "https://a.dev/new?session=1"),
            ("https://a.dev/new?session=1", "HEAD"): (200, None),
        })
        self.assertEqual(
            audit.check_url("https://a.dev/old", fetch),
            [("fix", "permanently redirects to https://a.dev/new; update the link")],
        )

    def test_head_refused_retries_with_get(self):
        fetch = fake_fetch({("https://a.dev/x", "HEAD"): (405, None), ("https://a.dev/x", "GET"): (200, None)})
        self.assertEqual(audit.check_url("https://a.dev/x", fetch), [])
        self.assertEqual(fetch.calls, [("https://a.dev/x", "HEAD"), ("https://a.dev/x", "GET")])

    def test_server_error_and_no_response(self):
        self.assertEqual(audit.check_url("https://a.dev/x", fake_fetch({("https://a.dev/x", "HEAD"): (503, None)}))[0][0], "check")
        self.assertEqual(audit.check_url("https://a.dev/x", fake_fetch({("https://a.dev/x", "HEAD"): (None, None)}))[0][0], "check")

    def test_redirect_loop(self):
        fetch = fake_fetch({("https://a.dev/x", "HEAD"): (301, "https://a.dev/x")})
        self.assertEqual(audit.check_url("https://a.dev/x", fetch)[0][0], "check")


class Audit(unittest.TestCase):
    TEXT = (
        "- [Gh](https://github.com/o/gh) - x.\n"
        "- [Docs](https://docs.a.dev/t) - Tracing in [Lib](https://github.com/o/lib).\n"
    )

    def run_audit(self, text, url_findings=(), repo_findings=()):
        seen = {"repos": [], "urls": []}

        def repo_check(name, owner, repo, now):
            seen["repos"].append((name, owner, repo))
            return list(repo_findings), False

        def url_check(url):
            seen["urls"].append(url)
            return list(url_findings)

        _, report, _, _ = audit.audit(text, NOW, repo_check=repo_check, url_check=url_check)
        return report, seen

    def test_non_github_entry_gets_http_and_linked_repo_checks(self):
        _, seen = self.run_audit(self.TEXT)
        self.assertEqual(seen["urls"], ["https://docs.a.dev/t"])
        self.assertEqual(seen["repos"], [("Gh", "o", "gh"), ("Docs", "o", "lib")])

    def test_no_manual_finding_for_non_github_entries(self):
        report, _ = self.run_audit(self.TEXT)
        self.assertEqual(report, [])
        self.assertFalse(audit.is_actionable(report))

    def test_redirect_is_reported_under_entry_name(self):
        report, _ = self.run_audit(self.TEXT, url_findings=[("fix", "permanently redirects to https://n; update the link")])
        self.assertEqual(report, [("fix", "Docs", "permanently redirects to https://n; update the link")])
        self.assertTrue(audit.is_actionable(report))

    def test_manual_only_is_not_actionable(self):
        self.assertFalse(audit.is_actionable([("manual", "skill-creator", "note")]))

    def test_render_clean(self):
        self.assertEqual(audit.render([], [], NOW), "# Entry audit, 2026-10-05\n\n0 entries checked, 0 findings.\n")


class TableAge(unittest.TestCase):
    def test_fresh_and_absent(self):
        self.assertEqual(audit.table_age("Last verified 2026-09-01.", NOW), [])
        self.assertEqual(audit.table_age("no table", NOW), [])

    def test_stale(self):
        (f,) = audit.table_age("Last verified 2026-06-01.", NOW)
        self.assertEqual(f[0], "check")
        self.assertIn("126 days", f[1])


class CrashSafety(unittest.TestCase):
    README = "- [Gh](https://github.com/o/gh) - x.\n"

    def run_main(self, prior_status=None):
        with tempfile.TemporaryDirectory() as d:
            readme, status = os.path.join(d, "README.md"), os.path.join(d, "status.txt")
            with open(readme, "w") as f:
                f.write(self.README)
            if prior_status:
                with open(status, "w") as f:
                    f.write(prior_status)
            with self.assertRaises(RuntimeError), mock.patch("sys.stdout"):
                audit.main([readme, "--status-file", status])
            return open(status).read() if os.path.exists(status) else None

    def test_crash_never_yields_clean(self):
        with mock.patch.object(audit, "check_repo", side_effect=RuntimeError("boom")):
            self.assertIsNone(self.run_main())
            self.assertIsNone(self.run_main(prior_status=audit.STATUS_CLEAN))

    def test_api_timeout_is_a_check_finding_not_a_crash(self):
        for exc in (TimeoutError("timed out"), urllib.error.URLError("unreachable")):
            with mock.patch("urllib.request.urlopen", side_effect=exc):
                findings, failed = audit.check_repo("Gh", "o", "gh", NOW)
            self.assertEqual(findings, [("check", "GitHub API returned None for o/gh")])
            self.assertTrue(failed)


if __name__ == "__main__":
    unittest.main()
