import unittest
from unittest.mock import patch

from backend.feeds import parse_entries, resolve_public, validate_url


class FeedTests(unittest.TestCase):
    def test_rss_cdata_and_relative_link(self):
        content = "<rss><channel><item><guid>12</guid><title>Message</title><link>/posts/12</link><description><![CDATA[<p>Acme &amp; tools</p>]]></description></item></channel></rss>"
        item = parse_entries(content, "rss", "https://forum.example.org/feed")[0]
        self.assertEqual(item["text"], "Acme & tools")
        self.assertEqual(item["url"], "https://forum.example.org/posts/12")
        self.assertEqual(item["key"], "12")

    def test_atom(self):
        content = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>1</id><title>New</title><link href="https://example.org/1"/><summary>Acme</summary></entry></feed>'
        item = parse_entries(content, "rss", "https://example.org/feed")[0]
        self.assertEqual(item["url"], "https://example.org/1")
        self.assertEqual(item["text"], "Acme")

    def test_json_and_text(self):
        items = parse_entries(
            '{"items":[{"id":12,"title":"Acme","content":"Hello"}]}',
            "json",
            "https://example.org/feed",
        )
        self.assertEqual(items[0]["text"], "Hello")
        self.assertEqual(
            len(parse_entries("Some public text", "text", "https://example.org")), 1
        )

    def test_script_content_is_not_analyzed(self):
        item = parse_entries(
            "<p>Hello</p><script>secretvalue</script>", "text", "https://example.org"
        )[0]
        self.assertEqual(item["text"], "Hello")

    def test_xml_entities_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_entries(
                '<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss/>',
                "rss",
                "https://example.org",
            )

    def test_non_feed_and_bad_json_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_entries(
                "<html><body>not a feed</body></html>", "rss", "https://example.org"
            )
        with self.assertRaises(ValueError):
            parse_entries("{invalid", "json", "https://example.org")

    def test_private_or_mixed_dns_answers_are_rejected(self):
        for addresses in (
            ["127.0.0.1"],
            ["10.0.0.1"],
            ["169.254.169.254"],
            ["::1"],
            ["93.184.216.34", "192.168.1.1"],
        ):
            records = [(2, 1, 6, "", (address, 0)) for address in addresses]
            with self.subTest(addresses=addresses), patch(
                "socket.getaddrinfo", return_value=records
            ), self.assertRaises(ValueError):
                resolve_public("example.org")

    def test_authenticated_or_non_http_urls_are_rejected(self):
        for url in (
            "file:///etc/passwd",
            "ftp://example.org",
            "https://user:pass@example.org",
            "https://@example.org",
            "https://example.org/\nInjected",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_urls_containing_authentication_tokens_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_url("https://example.org/feed?access_token=private-value")
