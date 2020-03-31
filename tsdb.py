import copy
import datetime
from influxdb import InfluxDBClient


import config
from logger import logger

body_bt = {
    'measurement': config.upload_table,
    'time': 0,
    'tags': {
        'mac': 0
    },
    'fields':{
        'name': 0,
        'manuf': 0,
        'major_type': 0,
        'minor_type': 0,
        'signal': 0
    }
}

class DBHelper():
    def __init__(self, db_url=config.upload_URL, port=config.upload_PORT, dbname=config.upload_DB):
        self.client = InfluxDBClient(host=db_url, port=port, database=dbname)

    def writeBTRecords(self, bt_records):
        records = []
        if len(bt_records) == 0:
            return

        for record in bt_records:
            body = copy.deepcopy(body_bt)
            
            mac, name, manuf, major_type, minor_type, signal, time = record['mac'], record['name'], record['manuf'], \
                                                          record['major_type'], record['minor_type'], record['signal'], record['time']

            body['time'] = time
            body['tags']['mac'] = mac
            body['fields']['name'] = name
            body['fields']['manuf'] = manuf
            body['fields']['major_type'] = major_type
            body['fields']['minor_type'] = minor_type
            body['fields']['signal'] = signal

            records.append(body)

        try:
            self.client.write_points(records)
        except Exception as e:
            logger.error('DB operation: write bt records record error!', e)
    
    def emptyBTRecords(self):
        self.client.query("delete from {};".format(config.upload_table))
        # self.client.query("drop measurement {}".format(config.upload_table))

    def getAllBTRecords(self):
        resutls = self.client.query('select * from {};'.format(config.upload_table))
        return resutls

    def upload(self, bt_records):
        self.writeBTRecords(bt_records)
        logger.info('DBHelper: sent {} bt records'.format(len(bt_records)))

if __name__ == '__main__':
    dbtool = DBHelper()

#    cur_time = datetime.datetime.utcnow().isoformat("T")

#    dbtool.emptyPos()
#    records = [(0,0,0,cur_time)]
#    dbtool.writePosRecord(0, 0, records)
    results = dbtool.getAllBTRecords()
    print(results)
