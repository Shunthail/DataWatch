import hashlib
import re
from urllib.parse import urlsplit

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(
    r"(?<!\w)(?:(?:\+33|0033)[ .-]?[1-9]|0[1-9])(?:[ .-]?\d{2}){4}(?!\d)"
)
SECRET = re.compile(
    r"""(?i)\b(api[_-]?key|access[_-]?token|secret|password|passwd|mot de passe)\b[\s"']*[:=]\s*(?:"[^"\r\n]+"|'[^'\r\n]+'|[^\s"'<>,;]+)"""
)

TOKEN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})\b"
)
LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def mask(text):
    text = SECRET.sub(lambda match: match.group(1) + "=[masqué]", text)
    text = TOKEN.sub("[jeton masqué]", text)
    text = EMAIL.sub(
        lambda match: match.group(0)[0] + "***@" + match.group(0).split("@")[1], text
    )
    return PHONE.sub("[téléphone masqué]", text)


def matches(rule, text):
    value = rule["value"]
    if rule["kind"] == "keyword":
        return re.search(re.escape(value), text, re.I)
    if rule["kind"] == "email":
        return re.search(r"(?<![\w.+-])" + re.escape(value) + r"(?![\w.-])", text, re.I)
    return re.search(
        r"(?<![\w.-])(?:[\w-]+\.)*" + re.escape(value) + r"(?![\w.-])", text, re.I
    )


def safe_link(value, fallback):
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and mask(value) == value
        ):
            return value
    except ValueError:
        pass
    return fallback


def detect(source, entries, rules):
    results = []
    for entry in entries:
        text = entry["title"] + "\n" + entry["text"]
        for rule in rules:
            if not rule["enabled"]:
                continue
            match = matches(rule, text)
            if match is None:
                continue
            signals = []
            if EMAIL.search(text):
                signals.append("Adresse e-mail")
            if PHONE.search(text):
                signals.append("Numéro de téléphone")
            severity = rule["severity"]
            secret = SECRET.search(text)
            if secret or TOKEN.search(text):
                signals.append("Identifiant ou secret potentiel")
                severity = (
                    "critical"
                    if TOKEN.search(text)
                    or (secret and "pass" not in secret.group(1).lower())
                    else max((severity, "high"), key=LEVELS.get)
                )
            elif signals:
                severity = max((severity, "medium"), key=LEVELS.get)
            # Mask before cropping so a truncated secret cannot bypass masking.
            safe_text = mask(text)
            prefix = len(mask(text[: match.start()]))
            start = max(0, prefix - 90)
            excerpt = ("…" if start else "") + safe_text[start : start + 280]
            if start + 280 < len(safe_text):
                excerpt += "…"
            fingerprint = hashlib.sha256(
                f"{source['id']}:{rule['id']}:{entry['key']}:{text}".encode()
            ).hexdigest()
            results.append(
                dict(
                    fingerprint=fingerprint,
                    rule_id=rule["id"],
                    rule_label=rule["label"],
                    title=mask(entry["title"])[:180],
                    excerpt=excerpt,
                    url=safe_link(entry["url"], source["url"]),
                    severity=severity,
                    signals=signals or ["Expression surveillée"],
                )
            )
    return results
