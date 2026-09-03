"""Parse an RSP Daily Manager Log dispatch into structured data.

Pure stdlib. No model involved: everything here is deterministic so the
same email always yields the same numbers.
"""
import re
from html.parser import HTMLParser


def _money(s):
    if s is None:
        return None
    s = re.sub(r"[^0-9.\-]", "", str(s).replace(",", ""))
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


class _Tables(HTMLParser):
    """Collect every table as {caption, rows}.

    A table nested inside a cell is attached to its parent row as a
    {"__child__": table} entry, so paid-out category rows and order
    confirmation rows stay bound to the line they belong to.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []          # top level only
        self._stack = []          # open tables
        self._cells = []          # open cell buffers, parallel to nesting
        self._cap = None
        self._in_cap = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append({"caption": None, "rows": []})
        elif tag == "caption" and self._stack:
            self._in_cap = True
            self._cap = []
        elif tag == "tr" and self._stack:
            self._stack[-1]["rows"].append([])
        elif tag in ("td", "th") and self._stack:
            self._cells.append([])

    def handle_endtag(self, tag):
        if tag == "table" and self._stack:
            t = self._stack.pop()
            if self._stack:
                rows = self._stack[-1]["rows"]
                if not rows:
                    rows.append([])
                rows[-1].append({"__child__": t})
            else:
                self.tables.append(t)
        elif tag == "caption" and self._stack:
            self._in_cap = False
            self._stack[-1]["caption"] = " ".join("".join(self._cap or []).split())
            self._cap = None
        elif tag in ("td", "th") and self._stack and self._cells:
            text = " ".join("".join(self._cells.pop()).split())
            rows = self._stack[-1]["rows"]
            if not rows:
                rows.append([])
            rows[-1].append(text)   # keep empties: cell position is meaningful

    def handle_data(self, data):
        if self._in_cap and self._cap is not None:
            self._cap.append(data)
        elif self._cells:
            self._cells[-1].append(data)


def _text_cells(row):
    return [c for c in row if isinstance(c, str)]


def _children(row):
    return [c["__child__"] for c in row if isinstance(c, dict)]


def _tables(html):
    p = _Tables()
    p.feed(html)
    return p.tables


def _by_caption(tables, name):
    name = name.lower()
    for t in tables:                      # exact first, so "MANAGER LOG" does not
        cap = (t["caption"] or "").lower()  # match the "Manager Log Details" banner
        if cap == name:
            return t
    for t in tables:
        cap = (t["caption"] or "").lower()
        if cap.startswith(name):
            return t
    for t in tables:
        cap = (t["caption"] or "").lower()
        if name in cap:
            return t
    return None


def _empty(rows):
    flat = " ".join(" ".join(_text_cells(r)) for r in rows).lower()
    return "no line items available" in flat


def log_date(html):
    m = re.search(r"Manager Log Details---(\d{4}-\d{2}-\d{2})", html)
    return m.group(1) if m else None


def parse(html):
    """Return a dict of everything the rules need from one dispatch."""
    tables = _tables(html)
    out = {
        "log_date": log_date(html),
        "questions": [],
        "duty_tables": {},
        "invoices": [],
        "invoices_empty": True,
        "paid_outs": [],
        "paid_outs_empty": True,
        "eod": {},
        "cash": {},
        "tenders": {},
        "reverse_labor": {},
        "price_history": [],
        "new_products": [],
        "orders": [],
    }

    ml = _by_caption(tables, "MANAGER LOG")
    if ml:
        for row in ml["rows"][1:]:
            r = _text_cells(row)
            if len(r) >= 2 and r[0] and r[0].lower() != "question":
                ans = r[1]
                who = None
                if "--" in ans:
                    ans, who = ans.rsplit("--", 1)
                out["questions"].append(
                    {"q": r[0], "a": ans.strip(), "by": (who or "").strip() or None}
                )

    for day in ("Daily", "Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday", "CADENCE"):
        t = _by_caption(tables, day + " Duties" if day != "CADENCE" else "CADENCE")
        if t is None:
            out["duty_tables"][day] = None          # table absent entirely
        else:
            body = [_text_cells(r) for r in t["rows"][1:]]
            body = [r for r in body if any(c for c in r)]
            out["duty_tables"][day] = [] if (not body or _empty(body)) else body

    inv = _by_caption(tables, "INVOICE LOGS")
    if inv:
        rows = inv["rows"][1:]
        out["invoices_empty"] = _empty(rows) or not rows
        if not out["invoices_empty"]:
            for row in rows:
                r = _text_cells(row)
                if len(r) >= 3:
                    out["invoices"].append(
                        {"vendor": r[0], "number": r[1], "amount": _money(r[2])}
                    )

    po = _by_caption(tables, "PAID OUT LOGS")
    if po:
        rows = po["rows"][1:]
        out["paid_outs_empty"] = _empty(rows) or not rows
        if not out["paid_outs_empty"]:
            for row in rows:
                r = _text_cells(row)
                if len(r) >= 3 and _money(r[2]) is not None:
                    out["paid_outs"].append(
                        {"store": r[0], "receipt": r[1], "amount": _money(r[2]),
                         "categories": []}
                    )
                elif out["paid_outs"]:
                    for ch in _children(row):     # category / description subtable
                        for cr in ch["rows"][1:]:
                            c = _text_cells(cr)
                            if len(c) >= 4:
                                out["paid_outs"][-1]["categories"].append(
                                    {"category": c[0], "code": c[1],
                                     "description": c[2], "amount": _money(c[3])}
                                )

    def _row_by_header(t):
        """{header: value} for a two row table, header names lower cased."""
        if not t or len(t["rows"]) < 2:
            return {}
        hdr = [h.lower().strip() for h in _text_cells(t["rows"][0])]
        val = _text_cells(t["rows"][1])
        return {h: val[i] for i, h in enumerate(hdr) if i < len(val)}

    eod = _by_caption(tables, "EOD REPORT")
    if eod:
        r = _row_by_header(eod)
        if r:
            out["eod"] = {
                "date": r.get("date"), "day": r.get("day"),
                "over_short": _money(r.get("over/short")),
                "gross": _money(r.get("gross sales")),
                "net": _money(r.get("net sales")),
                "paid_out": _money(r.get("paid out")),
            }
            # the full dispatch also carries the sales mix on the same row
            mix = {}
            for k, v in r.items():
                if k not in ("date", "day", "over/short", "gross sales", "net sales", "paid out"):
                    mv = _money(v)
                    if mv is not None:
                        mix[k] = mv
            if mix:
                out["eod"]["mix"] = mix

    # The Total Cash / Proof table has no caption. In the early dispatch it
    # is four columns; in the full dispatch it is ten. Find it by header and
    # read by header, which is why the surcharge column can no longer be
    # mistaken for cash.
    for t in tables:
        r = _row_by_header(t)
        if "total cash" in r and "proof" in r:
            out["cash"] = {"total_cash": _money(r["total cash"]), "proof": _money(r["proof"])}
            for k in ("credit card surcharge", "gift card sold", "sales tax",
                      "tips collected", "employee discounts", "guest discounts"):
                if k in r:
                    out["cash"][k.replace(" ", "_")] = _money(r[k])
            break
    for t in tables:
        r = _row_by_header(t)
        if "credit cards" in r and "date" in r and "proof" not in r:
            out["tenders"] = {k: _money(v) for k, v in r.items()
                              if k not in ("date", "day") and _money(v) is not None}
            break

    rl = _by_caption(tables, "REVERSE LABOR")
    if rl and rl["rows"]:
        days = [c for c in _text_cells(rl["rows"][0]) if c]
        for row in rl["rows"][1:]:
            r = _text_cells(row)
            if not r or not r[0]:
                continue
            key = r[0].lower().strip()
            vals = r[1:]
            rec = {}
            for i, d in enumerate(days):
                if i < len(vals):
                    v = vals[i]
                    if "/" in v:
                        a, b = v.split("/", 1)
                        rec[d] = (_money(a), _money(b))
                    else:
                        rec[d] = _money(v)
            out["reverse_labor"][key] = rec

    ph = _by_caption(tables, "Product Price History")
    if ph:
        rows = ph["rows"][1:]
        if not _empty(rows):
            for row in rows:
                r = _text_cells(row)
                if len(r) >= 6:
                    old, new = _money(r[4]), _money(r[5])
                    pct = None
                    if old and new is not None and old != 0:
                        pct = (new - old) / old * 100.0
                    out["price_history"].append({
                        "vendor": r[0], "product": r[2], "date": r[3],
                        "old": old, "new": new, "pct": pct,
                    })

    npt = _by_caption(tables, "New Product Added Today")
    if npt:
        rows = npt["rows"][1:]
        if not _empty(rows):
            for row in rows:
                r = _text_cells(row)
                if len(r) >= 5:
                    out["new_products"].append(
                        {"vendor": r[0], "product": r[2], "date": r[3], "price": _money(r[4])}
                    )

    op = _by_caption(tables, "ORDERS PLACED")
    if op:
        cur = None
        for row in op["rows"][1:]:
            r = _text_cells(row)
            if len(r) >= 4 and r[0] and r[0].lower() != "order name":
                cur = {"name": r[0], "order_date": r[1], "delivery_date": r[2],
                       "placed_date": None, "vendor": None}
                out["orders"].append(cur)
            for ch in _children(row):          # vendor confirmation subtable
                if cur is None:
                    continue
                for cr in ch["rows"][1:]:
                    c = _text_cells(cr)
                    if c and c[0].lower() != "vendor name":
                        cur["vendor"] = cur["vendor"] or c[0]
                    for cell in c:
                        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", cell):
                            cur["placed_date"] = cell
    return out
