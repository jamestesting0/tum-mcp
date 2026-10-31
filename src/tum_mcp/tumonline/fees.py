"""Semester fee status from TUMonline's fee page, which has no JSON endpoint."""

import re
from html.parser import HTMLParser
from typing import Final

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.tumonline.auth import Get

# English labels keep the parse independent of the account's language preference.
FEE_STATUS: Final = "/tumonline/pl/ui/$ctx;lang=en/wbstudienbeitragstatus.show"
DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
AMOUNT = re.compile(r"-?\d{1,3}(?:,\d{3})*\.\d{2}")


class FeeItem(Frozen):
    name: str
    amount_eur: str


class FeePayment(Frozen):
    date: str
    kind: str
    amount_eur: str


class FeeStatus(Frozen):
    semester: str
    items: tuple[FeeItem, ...]
    total_eur: str
    payment_deadline: str | None
    payments: tuple[FeePayment, ...]
    outstanding_eur: str | None


class FeePage(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.subtitle = ""
        self.rows: list[tuple[str, list[str]]] = []
        self._section = ""
        self._legend: list[str] | None = None
        self._heading: list[str] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "legend":
            self._legend = []
        elif tag == "h2" and ("id", "idCaSubTitle") in attrs:
            self._heading = []
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "legend" and self._legend is not None:
            self._section = " ".join("".join(self._legend).split())
            self._legend = None
        elif tag == "h2" and self._heading is not None:
            self.subtitle = " ".join("".join(self._heading).split())
            self._heading = None
        elif tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append((self._section, self._row))
            self._row = None

    def handle_data(self, data: str) -> None:
        for buffer in (self._legend, self._heading, self._cell):
            if buffer is not None:
                buffer.append(data)


def iso_date(text: str) -> str:
    match = DATE.fullmatch(text)
    if match is None:
        raise CampusError(Code.INVALID_RESPONSE, "TUMonline fee status page was not recognized.")
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def amount(text: str) -> str:
    if not AMOUNT.fullmatch(text):
        raise CampusError(Code.INVALID_RESPONSE, "TUMonline fee status page was not recognized.")
    return text


def project_fees(body: bytes) -> FeeStatus:
    """Keep the invoice, deadline and bookings; drop the account holder and refund forms."""
    page = FeePage()
    page.feed(body.decode("utf-8", errors="replace"))
    items: list[FeeItem] = []
    payments: list[FeePayment] = []
    total: str | None = None
    deadline: str | None = None
    outstanding: str | None = None
    group = ""
    for section, cells in page.rows:
        if section == "Invoice" and len(cells) == 2 and cells[0]:
            label, text = cells
            if label == "Total":
                total = amount(text)
            elif label == "Payment deadline":
                deadline = iso_date(text)
            elif AMOUNT.fullmatch(text) and text != "0.00":
                items.append(FeeItem(name=label, amount_eur=text))
        elif section == "Payments" and len(cells) == 1:
            group = cells[0]
        elif section == "Payments" and len(cells) == 3 and cells[0] != "Booking date":
            date, kind, text = cells
            if group == "outstanding":
                outstanding = amount(text)
            else:
                payments.append(FeePayment(date=iso_date(date), kind=kind, amount_eur=amount(text)))
    if not page.subtitle or total is None:
        raise CampusError(Code.INVALID_RESPONSE, "TUMonline fee status page was not recognized.")
    return FeeStatus(
        semester=page.subtitle,
        items=tuple(items),
        total_eur=total,
        payment_deadline=deadline,
        payments=tuple(payments),
        outstanding_eur=outstanding,
    )


def read_fees(get: Get) -> FeeStatus:
    return project_fees(get(FEE_STATUS))
