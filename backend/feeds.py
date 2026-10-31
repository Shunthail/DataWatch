import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, urljoin, urlsplit

MAX_BYTES = 1_000_000


def validate_url(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 1500
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Indiquer une URL HTTP ou HTTPS valide.")
    target = urlsplit(value.strip())
    if (
        target.scheme not in ("http", "https")
        or not target.hostname
        or target.username is not None
        or target.password is not None
    ):
        raise ValueError(
            "Utiliser une source publique HTTP ou HTTPS, sans identifiants."
        )
    if target.port is not None and not 1 <= target.port <= 65535:
        raise ValueError("Port invalide.")
    if any(
        key.lower() in {"key", "token", "password", "secret", "api_key", "access_token"}
        for key, _ in parse_qsl(target.query)
    ):
        raise ValueError("La source doit être publique, sans clé ni jeton dans l’URL.")
    return target._replace(fragment="").geturl()


def resolve_public(host):
    addresses = sorted(
        {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    )
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise ValueError("La source doit être hébergée sur des adresses IP publiques.")
    return addresses[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, port):
        super().__init__(
            host, port=port, timeout=8, context=ssl.create_default_context()
        )
        self.address = address

    def connect(self):
        connection = socket.create_connection(
            (self.address, self.port), timeout=self.timeout
        )
        try:
            self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
        except Exception:
            connection.close()
            raise


def fetch_text(url):
    for _ in range(4):
        url = validate_url(url)
        target = urlsplit(url)
        host = target.hostname.encode("idna").decode("ascii")
        address = resolve_public(host)
        port = target.port or (443 if target.scheme == "https" else 80)
        connection = (
            PinnedHTTPSConnection(host, address, port)
            if target.scheme == "https"
            else http.client.HTTPConnection(address, port, timeout=8)
        )
        host_header = f"[{host}]" if ":" in host else host
        if target.port:
            host_header += f":{target.port}"
        path = quote(target.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if target.query:
            path += "?" + quote(target.query, safe="%=&/?@:!$'()*+,;~-._")
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Host": host_header,
                    "User-Agent": "DataWatch/1.0",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Redirection sans destination.")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f"La source renvoie HTTP {response.status}.")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("La source dépasse la limite de 1 Mo.")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ValueError(
                    "La source impose une compression non prise en charge."
                )
            encoding = response.headers.get_content_charset() or "utf-8-sig"
            try:
                return body.decode(encoding, errors="replace")
            except LookupError as error:
                raise ValueError("Encodage de source non pris en charge.") from error
        finally:
            connection.close()
    raise ValueError("La source redirige trop de fois.")


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.ignored:
            self.ignored -= 1

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def plain(value):
    parser = TextParser()
    parser.feed(str(value))
    return " ".join(unescape(" ".join(parser.parts)).split())[:20_000]


def entry(title, text, link, key):
    title, text = plain(title), plain(text)
    return dict(
        title=title or "Publication sans titre",
        text=text,
        url=str(link or ""),
        key=str(key or hashlib.sha256((title + text).encode()).hexdigest()),
    )


def parse_entries(content, format, source_url):
    if format == "text":
        return [entry("Publication publique", content, source_url, "")]
    if format == "json":
        payload = json.loads(content)
        if isinstance(payload, dict):
            payload = payload.get("items", payload.get("entries", [payload]))
        if not isinstance(payload, list):
            raise ValueError(
                "JSON attendu : liste de publications ou objet avec items/entries."
            )
        return [
            entry(
                item.get("title", ""),
                item.get("content", item.get("text", item.get("description", ""))),
                urljoin(source_url, str(item.get("url", item.get("link", source_url)))),
                item.get("id", ""),
            )
            for item in payload[:100]
            if isinstance(item, dict)
        ]
    # Reject DTDs; the collector only needs regular RSS and Atom documents.
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise ValueError("Les flux contenant une DTD ou des entités sont refusés.")
    root = ET.fromstring(content)
    items = root.findall(".//item") or root.findall(
        "{http://www.w3.org/2005/Atom}entry"
    )
    if not items and root.tag not in (
        "rss",
        "{http://www.w3.org/2005/Atom}feed",
        "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF",
    ):
        raise ValueError("Ce document ne ressemble pas à un flux RSS ou Atom.")
    entries = []
    for item in items[:100]:
        fields = {child.tag.split("}")[-1]: child for child in item}

        def field(name):
            node = fields.get(name)
            return "".join(node.itertext()) if node is not None else ""

        link_node = fields.get("link")
        link = link_node.get("href", "") if link_node is not None else ""
        link = urljoin(source_url, link or field("link") or source_url)
        entries.append(
            entry(
                field("title"),
                field("encoded")
                or field("content")
                or field("description")
                or field("summary"),
                link,
                field("guid") or field("id"),
            )
        )
    return entries
