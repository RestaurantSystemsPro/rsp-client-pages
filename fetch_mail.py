"""Pull the Vivio's dispatch for a given log date out of Gmail over IMAP.

Uses an app password, the same way the accounting board does. Reads only:
never marks, moves or deletes anything.
"""
import email
import imaplib
import re
from email.header import decode_header, make_header

HOST = "imap.gmail.com"
SUBJECT_MATCH = "vivio"
TITLE = "Manager Log Details---%s"


def _decode(v):
    try:
        return str(make_header(decode_header(v)))
    except Exception:
        return v or ""


def _html_of(msg):
    if msg.is_multipart():
        best = None
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                best = part
        if best is None:
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    best = part
        if best is None:
            return ""
        payload = best.get_payload(decode=True) or b""
        return payload.decode(best.get_content_charset() or "utf-8", "replace")
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", "replace")


def fetch(address, app_password, log_date, days_back=4, mailbox='"[Gmail]/All Mail"'):
    """Return (html, meta) for the most recent, most complete dispatch whose
    title line matches `log_date`. A later re-dispatch always wins over the
    early automatic send, which is the whole point of looking at several days.
    """
    want = TITLE % log_date
    m = imaplib.IMAP4_SSL(HOST)
    try:
        m.login(address, app_password)
        m.select(mailbox, readonly=True)
        since = (
            __import__("datetime").date.fromisoformat(log_date)
            - __import__("datetime").timedelta(days=days_back)
        ).strftime("%d-%b-%Y")
        typ, data = m.search(None, '(FROM "rsp_admin@restaurantsystemspro.net" '
                                   'SUBJECT "Daily Manager Log" SINCE %s)' % since)
        if typ != "OK":
            return None, {"error": "IMAP search failed"}
        ids = data[0].split()
        best = None
        for i in reversed(ids):                     # newest first
            typ, raw = m.fetch(i, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            subj = _decode(msg.get("Subject", ""))
            if SUBJECT_MATCH not in subj.lower():
                continue
            html = _html_of(msg)
            if want not in html:
                continue
            meta = {"subject": subj, "date": _decode(msg.get("Date", "")),
                    "size": len(html)}
            # prefer the biggest body for this date: a re-dispatch carries
            # the EOD and the populated weekday tables the early send lacks
            if best is None or len(html) > len(best[0]):
                best = (html, meta)
        if best is None:
            return None, {"error": "no dispatch found for %s" % log_date,
                          "candidates": len(ids)}
        return best
    finally:
        try:
            m.logout()
        except Exception:
            pass
