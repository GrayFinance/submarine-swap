from configs import REDIS_HOST, REDIS_PORT, REDIS_PASS
from redis import StrictRedis

redis = StrictRedis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS)