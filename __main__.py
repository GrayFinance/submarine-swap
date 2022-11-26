from dotenv import load_dotenv
from os import environ

# Loads the variables of environments in the .env file
# of the current directory.
load_dotenv(environ.get("ENV_PATH", ".env"))

from threading import Thread
from services import bitcoin

import api

def start():
    threads = []
    
    thread = Thread(target=api.start)
    thread.start()
    threads.append(thread)

    thread = Thread(target=bitcoin.start)
    thread.start()
    threads.append(thread)

    for t in threads:
        t.join()
    
if __name__ == "__main__":
    start()