from configs import LND_CERTIFICATE, LND_HOST, LND_MACAROON
from lnd import Lnd

lnd = Lnd(url=LND_HOST, macaroon=LND_MACAROON, certificate=LND_CERTIFICATE)

def create_invoice_hold(payment_hash: str, value: int, expiry=(60 * 60)) -> dict:
    invoice = lnd.create_hold_invoice(payment_hash, value, expiry=expiry)
    if not invoice.get("payment_request"):
        raise Exception("There was a problem trying to create a new invoice.")
    
    # Get payment request.
    payment_request = invoice["payment_request"]
    return {"payment_hash": payment_hash, "payment_request": payment_request, "expiry": expiry}
