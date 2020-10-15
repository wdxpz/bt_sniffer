"""
run this script to simulate robot position sender
"""


import time
import json
# from kafka import KafkaProducer
import redis

import config
from logger import getLogger
logger = getLogger('robot simulator')
logger.propagate = False


pos_body = {
    "timestamp": 1599033481,
    "robot_id": config.robot_id,
    "inspection_id": 0,
    "site_id": 0,
    "location": '0-0-0'
}
pos = [0.0, 0.0, 0.0]

# producer = KafkaProducer(
#     bootstrap_servers=config.brokers, compression_type='gzip', value_serializer=lambda x: json.dumps(x).encode())

redis_connector = redis.Redis(host=config.redis_host, port=config.redis_port, db=0)


while True:
    time.sleep(1)

    pos_body['timestamp'] = str(int(time.time()))
    pos = [x + 1e-5 for x in pos]
    pos_str = ['{:.5f}'.format(x) for x in pos]
    pos_body['location'] = '-'.join(pos_str)

    try:
        # future = producer.send('robot-position-test', key="".encode(), value=pos_body)
        # Block until a single message is sent (or timeout)
        # result = future.get(timeout=config.block_waiting_time)
        redis_connector.hmset(config.robot_id, pos_body)
        redis_connector.hmset('tb3_1', pos_body)

        logger.info('Redis operation : send robot pos record {}'.format(pos_body))
    except Exception as e:
        logger.error('Redis operation : send robot pos record error! ' + str(e))
        continue


