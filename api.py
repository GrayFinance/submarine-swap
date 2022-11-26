from services.lightning import lnd, create_invoice_hold
from services.bitcoin import bitcoin, bitcoin_watchonly, get_balance, network
from services.redis import redis

from database import database
from binascii import unhexlify

from helpers import descsum_create, percentage, timestamp
from fastapi import FastAPI, HTTPException
from configs import API_HOST, API_PORT, SWAP_MAX_AMOUNT, SWAP_MIN_AMOUNT, SWAP_SERVICE_FEERATE
from schemas import SubmarineSwapSchema

from tinydb import Query
from json import dumps, loads
from htlc import HTLC, Tx
from os import urandom

import logging
import hashlib
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Initialization HTLC.
htlc = HTLC(network=network)

# Initialization Tx.
tx = Tx(network=network)

# Initialization API.
api = FastAPI()

@api.post("/api/v1/create")
def create_submarine_swap(data: SubmarineSwapSchema):
    pubkey = data.pubkey
    value = data.value
    payment_hash = data.payment_hash
    if (len(pubkey) < 64):
        raise HTTPException(400, "Pubkey invalid.")
    
    if (value <= 565):
        raise HTTPException(400, "Amount must not be less than the dust limit.")
    
    elif (value <= 0):
        raise HTTPException(400, "Amount must not be less than or equal to zero.")
        
    elif (value < SWAP_MIN_AMOUNT):
        raise HTTPException(400, "Amount is less than the minimum.")
      
    elif (value > SWAP_MAX_AMOUNT):
        raise HTTPException(400, "Amount is greater than the maximum.")
    
    if (len(payment_hash) < 64) or (len(payment_hash) > 64):
        raise HTTPException(400, "Payment hash invalid.")

    broker_addr = bitcoin.getnewaddress()
    broker_pubk = bitcoin.getaddressinfo(broker_addr)["pubkey"]
    blockheight = bitcoin.getblockcount()
    locktime = (blockheight + 6)
    
    # Create script witness.
    script_witness = htlc.create_witness_script(
        image=unhexlify(payment_hash), 
        broker=unhexlify(broker_pubk), 
        customer=unhexlify(pubkey), 
        locktime=locktime
    )

    # Generate bitcoin address 
    # from witness script.
    p2wsh_address = htlc.create_p2wsh_address(script_witness)
    
    fee_total = lnd.get_estimate_fee(p2wsh_address, value, target_conf=1)
    if not (fee_total.get("feerate_sat_per_byte")):
        raise HTTPException(500, "Unable to estimate fee.")
    
    fee_network = int(fee_total["fee_sat"]) / int(fee_total["feerate_sat_per_byte"])    
    fee_service = int(percentage(value, SWAP_SERVICE_FEERATE))
    
    # Check if you have enough funds.
    balance = get_balance()
    if ((value + fee_network) > balance):
        raise HTTPException(500, "We don't have enough liquidity at the moment.")
    
    # Generate an invoice with the 
    # customer's payment_hash.
    value_release = (value + fee_network + fee_service)
    try:
        hold_invoice = create_invoice_hold(payment_hash=payment_hash, value=value_release)
    except:
        raise HTTPException(500, "There was a problem trying to create a new invoice.")
    
    expiry = ((60 * 10) * (locktime - blockheight)) * 2
    
    tx = { "id": ( urandom(16).hex() ) }
    tx["status"] = "pending"
    tx["value"] = value
    tx["invoice"] = hold_invoice["payment_request"]
    tx["address"] = p2wsh_address
    tx["locktime"] = locktime
    tx["fee_network"] = fee_network
    tx["fee_service"] = fee_service
    tx["redeem_script"] = script_witness.hex()
    tx["payment_hash"] = payment_hash
    tx["preimage"] = None
    tx["expiry"] = expiry
    tx["created_at"] = timestamp()
    tx["updated_at"] = tx["created_at"]
    
    redis.set("sb.%s" % (tx["id"]), dumps(tx))
    redis.expire("sb.%s" % (tx["id"]), expiry)
    return tx

@api.post("/api/v1/settle/{swap_id}")
def settle(swap_id: str, preimage: str):
    tx = database.get((Query().id == swap_id) & (Query().status == "accepted"))
    if not (tx):
        raise HTTPException(500, "Transaction not found.")

    if not (hashlib.sha256(preimage.encode()).hexdigest() == tx["payment_hash"]):
        raise HTTPException(500, "Invalid pre-image.")
    
    settle = lnd.settle_invoice(preimage)
    if (settle == {}):
        database.update({"status": "settled", "preimage": preimage, "updated_at": timestamp()}    , (Query().id == swap_id))
        return tx
    else:
        raise HTTPException(500, "Invalid pre-image.")
    
@api.get("/api/v1/lookup/{swap_id}")
def lookup(swap_id: str):
    tx = redis.get(f"sb.{swap_id}")
    if (tx):
        tx = loads(tx)
    else:
        tx = database.get((Query().id == swap_id))
        if not (tx):
            raise HTTPException(500, "Transaction not found.")

    payment_hash = tx["payment_hash"]
    lookup = lnd.lookup_invoice(payment_hash)
    if (tx["status"] == "pending") and (lookup["state"] == "ACCEPTED"):
        tx["status"] = "accepted"
        tx["updated_at"] = timestamp()

        address = tx["address"]
        descriptor = descsum_create(f"addr({address})")

        bitcoin_watchonly.importdescriptors({
            "desc": descriptor, 
            "internal": False, 
            "watchonly": True, 
            "active": False, 
            "timestamp": "now"
        })
        
        txid = lnd.send_coins(tx["address"], tx["value"]).get("txid")
        if (txid):        
            tx["funding_txid"] = txid
            list_unspent = lnd.list_unspent(min_confs=0)["utxos"]
            funding_vout = list(filter(lambda utxo: txid == utxo["outpoint"]["txid_str"], list_unspent))[0]["outpoint"]
            funding_vout = int(funding_vout["output_index"])
            if (funding_vout == 0):
                tx["funding_vout"] = 1
            else:
                tx["funding_vout"] = 0
            
            redis.delete("sb.%s" % (tx["id"]))
            database.insert(tx)
        else:
            tx["status"] = "canceled"
            tx["updated_at"] = timestamp()
            redis.set("sb.%s" % (tx["id"]), dumps(tx))
            redis.expire("sb.%s" % (tx["id"]), 60 * 10)
            lnd.cancel_invoice(tx["payment_hash"])
    return tx
    
def start():
    uvicorn.run(api, host=API_HOST, port=API_PORT, log_config={
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(asctime)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",

            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "foo-logger": {"handlers": ["default"], "level": "DEBUG"},
        },
    })