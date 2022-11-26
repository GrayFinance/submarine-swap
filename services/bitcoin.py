from services.lightning import lnd
from bitcoin_rpc import BitcoinRPC
from binascii import unhexlify
from database import database
from helpers import timestamp
from configs import BTC_URL, BTC_ZMQ_RAW_TX
from tinydb import Query

import logging
import hashlib
import zmq
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Initialization Bitcoin.
bitcoin = BitcoinRPC(BTC_URL)
try:
    # Check the network the bitcoin core is on running.
    network = bitcoin.call("getblockchaininfo")["chain"]
except:
    logging.critical("Bitcoin Core RPC not running.")
    logging.critical("Exit")
    sys.exit(1)

try:
    bitcoin.call("createwallet", "watchonly", True, True, "", False, True)
    logging.info("Create watchonly wallet.")
except Exception as error:
    logging.critical(error)

bitcoin = BitcoinRPC(f"{BTC_URL}/wallet/")
bitcoin_watchonly = BitcoinRPC(f"{BTC_URL}/wallet/watchonly")   

def start():
    context = zmq.Context()

    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.RCVHWM, 0)
    socket.setsockopt_string(zmq.SUBSCRIBE, "rawtx")    
    socket.connect(BTC_ZMQ_RAW_TX)

    while True:
        topic, body, seq = socket.recv_multipart()
        if not (topic == b"rawtx"):
            continue
        
        print(body)

        vin = bitcoin.decoderawtransaction(body.hex())["vin"]
        if (len(vin) != 1):
            continue
        else:
            vin = vin[0]
        
        if (vin.get("coinbase")):
            continue
        
        tx = database.get(
            (Query().funding_txid == vin["txid"]) & 
            (Query().funding_vout == vin["vout"]) & 
            (Query().status == "accepted")
        )
        if not (tx):
            continue
        
        txinwitness = vin["txinwitness"]
        if (len(txinwitness) != 5):
            continue
        
        pre_image = unhexlify(txinwitness[2])
        if (hashlib.sha256(pre_image).hexdigest() != tx["payment_hash"]):
            continue
        
        settle = lnd.settle_invoice(pre_image.decode())
        if (settle == {}):
            tx["status"] = "settled"
            tx["preimage"] = pre_image.decode()
            tx["updated_at"] = timestamp()
            database.update(tx, (Query().id == tx["id"]))

def get_balance() -> int:
    try:
        balance = lnd.wallet_balance()
        total_balance = int(balance["total_balance"])
        total_balance-= int(balance["reserved_balance_anchor_chan"])
        return total_balance
    except:
        return 0