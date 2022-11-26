from os.path import expanduser
from os import environ, makedirs

PATH = expanduser("~/submarine-swap")

makedirs(f"{PATH}/data", exist_ok=True)

# API configuration.
API_HOST = environ.get("API_HOST", "0.0.0.0")
API_PORT = int(environ.get("API_PORT", 9652))

# Swap configuration.
SWAP_SERVICE_FEERATE = float(environ.get("SWAP_SERVICE_FEERATE", 0.5))
SWAP_MAX_AMOUNT = int(environ.get("SWAP_MAX_AMOUNT", 100000000))
SWAP_MIN_AMOUNT = int(environ.get("SWAP_MIN_AMOUNT", 100000))

# Bitcoin configuration.
BTC_URL = environ["BTC_URL"]
BTC_ZMQ_RAW_TX = environ["BTC_ZMQ_RAW_TX"]

# Lnd configuration.
LND_HOST = environ.get("LND_HOST", "https://127.0.0.1:8080")
LND_MACAROON = environ.get("LND_MACAROON")
LND_CERTIFICATE = environ.get("LND_CERTIFICATE", False)

# Redis configuration.
REDIS_HOST = environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = environ.get("REDIS_PORT", 6379)
REDIS_PASS = environ.get("REDIS_PASS", "")