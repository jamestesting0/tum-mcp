import pytest

from tum_mcp.errors import CampusError
from tum_mcp.tumonline.fees import project_fees

PAGE = """
<div id="pageContent">
<table id="idTopPageHeader"><tr>
<td class="pageOwner"><a href="visitenkarte.show_vcard?pPersonenId=synthetic-private-id">
synthetic-private-name</a></td></tr></table>
<h1 class="headerHeading">Fee status</h1>
<h2 id="idCaSubTitle" class="m">Winter semester 2026/27</h2>
<form><table><tr><td><label class="Mask">Account information for:</label></td>
<td><select id="idSemesterNr"><option selected>Winter semester 2026/27</option>
<option>Summer semester 2026</option></select></td></tr></table>
<fieldset><legend class="Mask"><span class="Mask">Invoice</span></legend>
<table class="MaskSpacing"><tr><td><div><table class="cotable">
<thead><tr><th></th><th>Amount within admission deadline (&euro;)</th></tr></thead>
<tbody>
<tr class="coRow"><td><a href="#"></a>Semester fees</td><td>0.00</td></tr>
<tr class="coRow"><td><a href="#"></a>Student union fee</td><td>85.00</td></tr>
<tr class="coRow"><td><a href="#"></a>Basic fee for MVG Semester Ticket</td><td>1,234.50</td></tr>
<tr class="coRow"><td><a href="#"></a><span class="bold">Total</span></td><td>
<span class="bold">1,319.50</span></td></tr>
<tr class="coRow"><td><a href="#"></a></td><td></td></tr>
<tr class="coRow"><td><a href="#"></a>Payment deadline</td><td>15.02.2027</td></tr>
</tbody></table></div></td></tr></table></fieldset>
<fieldset><legend class="Mask"><span class="Mask">Payments</span></legend>
<table class="MaskSpacing"><tr><td><div><table class="cotable">
<thead><tr><th>Booking date</th><th>Type of payment</th><th>Amount (&euro;)</th></tr></thead>
<tbody>
<tr class="coRow coTableGR1"><td>confirmed<a></a></td></tr>
<tr class="coRow"><td><a href="#">03.02.2027</a></td><td>Bank</td><td>85.00</td></tr>
<tr class="coRow coTableGR1"><td>outstanding<a></a></td></tr>
<tr class="coRow"><td><a href="#"></a></td><td></td><td>
<span class="infoText">1,234.50</span></td></tr>
</tbody></table></div></td></tr></table></fieldset>
<fieldset><legend class="Mask"><span class="Mask">Applications</span></legend>
<table><tr>
<td><a href="studienbeitrag.refund?pId=synthetic-private-refund">Request a refund</a></td>
</tr></table>
</fieldset></form></div>
"""


def test_fee_page_keeps_invoice_deadline_and_bookings_but_not_the_account_holder() -> None:
    status = project_fees(PAGE.encode())
    assert status.semester == "Winter semester 2026/27"
    assert [(item.name, item.amount_eur) for item in status.items] == [
        ("Student union fee", "85.00"),
        ("Basic fee for MVG Semester Ticket", "1,234.50"),
    ]
    assert (status.total_eur, status.payment_deadline) == ("1,319.50", "2027-02-15")
    assert [(p.date, p.kind, p.amount_eur) for p in status.payments] == [
        ("2027-02-03", "Bank", "85.00")
    ]
    assert status.outstanding_eur == "1,234.50"
    assert "synthetic-private" not in status.model_dump_json()


def test_unrecognized_fee_page_fails_closed() -> None:
    login = b"<html><title>Login</title><form><label>Username</label></form></html>"
    with pytest.raises(CampusError, match="INVALID_RESPONSE"):
        project_fees(login)
