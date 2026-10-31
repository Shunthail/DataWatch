import unittest

from backend.detection import detect, mask


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": 1,
            "name": "Forum",
            "url": "https://forum.example.org/feed",
        }
        self.rule = {
            "id": 1,
            "label": "Entreprise",
            "kind": "domain",
            "value": "acme.test",
            "enabled": True,
            "severity": "low",
        }

    def detect(self, text, **changes):
        rule = dict(self.rule, **changes)
        return detect(
            self.source,
            [
                {
                    "key": "1",
                    "title": "Publication",
                    "text": text,
                    "url": "https://forum.example.org/post/1",
                }
            ],
            [rule],
        )

    def test_email_is_masked_and_increases_severity(self):
        results = self.detect("Contact : alice@acme.test")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["severity"], "medium")
        self.assertNotIn("alice@", results[0]["excerpt"])
        self.assertIn("a***@acme.test", results[0]["excerpt"])

    def test_domain_boundaries_prevent_false_matches(self):
        for text in ("notacme.test", "acme.test.evil.org", "acme.test-example.org"):
            with self.subTest(text=text):
                self.assertEqual(self.detect(text), [])
        self.assertEqual(len(self.detect("portal.acme.test")), 1)

    def test_keyword_is_literal_and_case_insensitive(self):
        self.assertEqual(
            len(self.detect("ACME [OPS]", kind="keyword", value="Acme [ops]")), 1
        )
        self.assertEqual(
            self.detect("Acme ops", kind="keyword", value="Acme [ops]"), []
        )

    def test_exact_email_does_not_match_other_users(self):
        self.assertEqual(
            self.detect("notalice@acme.test", kind="email", value="alice@acme.test"), []
        )

    def test_password_and_phone_are_never_in_excerpt(self):
        results = self.detect(
            "acme.test password=correct-horse-battery +33 6 12 34 56 78"
        )
        excerpt = results[0]["excerpt"]
        self.assertNotIn("correct-horse", excerpt)
        self.assertNotIn("12 34 56 78", excerpt)
        self.assertEqual(results[0]["severity"], "high")

    def test_tokens_are_critical_and_masked(self):
        token = "ghp_" + "a" * 36
        result = self.detect(f"acme.test {token}")[0]
        self.assertEqual(result["severity"], "critical")
        self.assertNotIn(token, result["excerpt"])

    def test_masking_happens_before_excerpt_truncation(self):
        secret = "x" * 250
        result = self.detect("acme.test " + "padding " * 25 + "api_key=" + secret)[0]
        self.assertNotIn("x" * 8, result["excerpt"])
        self.assertEqual(result["severity"], "critical")

    def test_disabled_rules_produce_no_alert(self):
        self.assertEqual(self.detect("acme.test", enabled=False), [])

    def test_unsafe_links_fall_back_to_source(self):
        result = detect(
            self.source,
            [
                {
                    "key": "1",
                    "title": "acme.test",
                    "text": "hello",
                    "url": "javascript:alert(1)",
                }
            ],
            [self.rule],
        )[0]
        self.assertEqual(result["url"], self.source["url"])

    def test_severity_never_drops_below_configured_level(self):
        self.assertEqual(
            self.detect("acme.test alice@acme.test", severity="critical")[0][
                "severity"
            ],
            "critical",
        )

    def test_quoted_secrets_with_spaces_are_fully_masked(self):
        for text in (
            'password="correct horse battery staple"',
            "'password': 'correct horse battery staple'",
        ):
            result = self.detect("acme.test " + text)[0]
            self.assertNotIn("horse", result["excerpt"])
            self.assertNotIn("staple", result["excerpt"])
            self.assertIn("[masqué]", result["excerpt"])
