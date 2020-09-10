import json
from kafka import KafkaProducer
import config

from logger import getLogger
logger = getLogger('Kafaka operation')
logger.propagate = False

producer = KafkaProducer(
    bootstrap_servers=config.brokers, compression_type='gzip', value_serializer=lambda x: json.dumps(x).encode())

# just an example, you don't have to follow this format
payload = {
    'timestamp': None,
    "location": None,
    'id': config.id, 
    'mac': None,
    'name': None,
    'manuf': None,
    'major_type': None,
    'minor_type': None,
    'signal': None
}

def sendMsg(data):
    for record in data:
        if record['location'] is None or len(record['location'])<2: #tell record is found during robot inspection

            body = copy.deepcopy(payload)
            body['timestamp'] = record['time']
            body['locatoin'] = record['location']
            body['mac'] = record['mac']
            body['name'] = record['name']
            body['manuf'] = record['manuf']
            body['major_type'] = record['major_type']
            body['minor_type'] = record['minor_type']
            body['signal'] = record['signal']

        try:
            future = producer.send(config.topic, key="".encode(), value=body)
            # Block until a single message is sent (or timeout)
            result = future.get(timeout=10)
        except Exception as e:
            logger.error('Kafaka operation : send bt records record error!', e)