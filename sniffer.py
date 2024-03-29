'''
the final records to data center will be like:
(
    {
    'name': name,
    'manuf': manuf,
    'last_seen': updated_at,
    'major_type': classic_major_class,
    'minor_type': classic_minor_class,
    'rssis': {
         {timestamp1: rssi_value1},
         {timestamp2: rssi_value2},
         ...,
        }
    
    },
    {
    ...
    },
    ...
)
'''
import psutil
import threading
import sqlite3
import os
import sys
import shutil
import time
import requests
import copy
from queue import Queue
from datetime import timedelta, datetime

import redis

import config
from tsdb import DBHelper
from util_kafka import sendMsg
from logger import getLogger
logger = getLogger('BT Sniffer')
logger.propagate = False

#Defininitions
rssilogPath = os.path.join(config.bluehydra_path, config.bluehydra_rssi_log_file)
databasePath = os.path.join(config.bluehydra_path, config.bluehydra_db_file)
sqlCommand = "SELECT address, name, vendor, company, manufacturer, \
                     classic_mode AS classic, \
                     le_mode AS le, le_address_type, \
                     updated_at as last_seen, \
                     classic_major_class, classic_minor_class, classic_class \
              FROM blue_hydra_devices \
              WHERE CAST(strftime('%s',updated_at) AS integer) BETWEEN CAST({} AS integer) AND CAST({} AS integer);"

upload_cache = Queue(maxsize=0)
all_devices = {}
dbtool = DBHelper() if config.Enable_TSDB else None
#use a lock to avoid the case of simutaneous reading of the buehydar_rssi_log file
collect_task_lock = threading.Lock()

redis_connector = redis.Redis(host=config.redis_host, port=config.redis_port, db=0)

def checkIfProcessRunning(processName):
    '''
    Check if there is any running process that contains the given name processName.
    '''
    #Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            # Check if process name contains the given name string.
            if processName.lower() in proc.name().lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False;

def loadDeviceFromDB():
    #Connect to database
    try:
        conn = sqlite3.connect(databasePath)
        c = conn.cursor()

        #Query for data, then store in list
        endtime = time.time()
        starttime = endtime - config.device_time_shift_hour*60*60
        sql = sqlCommand.format(starttime, endtime)
        try:
            c.execute(sql)
            results = c.fetchall()
        except Exception as e:
            logger.error("Unable to query database: " + str(e))
    except Exception as e:
        logger.error("Unable to connect to database: " + str(e))

    if results is not None or len(results)>0:
        for record in results:
            manuf = record[3] if record[3] else record[2]
            manuf = record[4] if record[4] else manuf
            all_devices[record[0]] = {
                'mac': record[0],
                'name': record[1],
                'manuf': manuf,
                'last_seen': record[-4],
                'major_type': record[-3],
                'minor_type': record[-2],
            }
            #logger.info('device from existed db: ', all_devices[record[0]])

def getLocation():
    res = redis_connector.hgetall(config.robot_id)
    logger.info('redis return {}'.format(res))
    if res is None or 'location'.encode() not in res.keys():
        return None

    return res['location'.encode()].decode()
        

#collect devices from kismet very config.collect_time_mini_interval seconds 
def collect_bluehydra(interval):
    while True:

        time.sleep(interval)
        
       
        # #wait for task lock
        # collect_task_lock.acquire()
        
        if not os.path.exists(rssilogPath):
            # logger.info('collect task: 0 rssi record found!')
            # collect_task_lock.release()
            continue

        location = getLocation()
        if location is None or len(location)<2:
            # collect_task_lock.release()
           pass
           #continue
        
        
        
        # empty current rssi log
        rssilogbakPath = rssilogPath+'.bak'
        shutil.copyfile(rssilogPath, rssilogbakPath)
        os.remove(rssilogPath)

        with open(rssilogbakPath) as rssilog:
            logs = rssilog.readlines()

        #remove logfile line
        if len(logs)>0 and 'Logfile' in logs[0]:
            logs = logs[1:]

        if len(logs) == 0:
            continue

            #check if timestamp exceed the interval, otherwise this batch should be discard because this batch was left by last long time ago
            #there will some logic error if the excution duration of collect_bluehydra exceed the interval
            # last_log = logs[-1]
            # log_fields = last_log.split(' ')
            # ts, mac, rssi = log_fields[0], log_fields[2], log_fields[3]
            # cur_time = int(time.time())
            # if (cur_time-int(ts)) > max(1, interval):
            #     logger.info('collect task: old records with time interval {}s, discard!'.format(cur_time-int(ts)))
            #     continue
                            
        #     for log_line in logs:
        #         log_line = log_line[:-1]
        #         log_fields = log_line.split(' ')
        #         ts, mac, rssi = log_fields[0], log_fields[2], log_fields[3]
        #         if mac not in rssi_records:
        #             # rssi_records[mac] = {location: {ts: rssi}}
        #             rssi_records[mac] = [location, ts, rssi]
        #         else:
        #             #filter repeated (mac, ts, rssi) records
        #             # if ts in rssi_records[mac][location]:
        #             #     if rssi > rssi_records[mac][location][ts]:
        #             #         rssi_records[mac][[location][ts] = rssi
        #             # else:
        #             #     rssi_records[mac][location][ts] = rssi
        #             if int(rssi) > int(rssi_records[mac][-1]):
        #                 rssi_records[mac] = [location, ts, rssi]

        #     logger.info('collect task: processed {} mac: ts: rssi records from {} original rssi records'.format(len(rssi_records), len(logs)))
        #     #print('collect task loop: processed records \n', rssi_records)

        # upload_cache.put(rssi_records)

        t = threading.Thread(target=filter_rssi_record, args=(location, logs))
        t.start()

def filter_rssi_record(location, logs):
    rssi_records = {}
    
    for log_line in logs:
        log_line = log_line[:-1]
        log_fields = log_line.split(' ')
        ts, mac, rssi = log_fields[0], log_fields[2], log_fields[3]
        if mac not in rssi_records:
            # rssi_records[mac] = {location: {ts: rssi}}
            rssi_records[mac] = [location, ts, rssi]
        else:
            #filter repeated (mac, ts, rssi) records
            # if ts in rssi_records[mac][location]:
            #     if rssi > rssi_records[mac][location][ts]:
            #         rssi_records[mac][[location][ts] = rssi
            # else:
            #     rssi_records[mac][location][ts] = rssi
            if int(rssi) > int(rssi_records[mac][-1]):
                rssi_records[mac] = [location, ts, rssi]

    logger.info('collect task: processed {} mac: ts: rssi records from {} original rssi records'.format(len(rssi_records), len(logs)))
    #print('collect task loop: processed records \n', rssi_records)

    upload_cache.put(rssi_records)
    
    
#upload to data center every config.upload_time_mini_interval
def upload2datacenter(interval):
    
    while True:

        time.sleep(interval)

        all_records = {}
        
        #unify the rssi_records in buffer to all_records
        while not upload_cache.empty():
            records = upload_cache.get()
            if len(all_records) == 0:
                for mac, record in records.items():
                    location, ts, rssi = record
                    all_records[mac] = {location: [ts, rssi]}
            else:
                for mac, record in records.items():
                    location, ts, rssi = record
                    if mac in all_records:
                        if location in all_records[mac]:
                            if int(rssi) > int(all_records[mac][location][-1]):
                                all_records[mac][location] = [ts, rssi]
                        else:
                            all_records[mac][location] = [ts, rssi]
                    else:
                        all_records[mac] = {location: [ts, rssi]}
                        
            upload_cache.task_done()
        
        if len(all_records) == 0:
            continue

        # logger.info('upload task: unified {} rssi records'.format(len(all_records)))
        
        #update device table
        #todo: can be improve by sqlite3 triger, the curretn problem
        #is the blue_hydra.db is reaonly so we can not add trigger into it
        #while once we change the right property of blue_hydra.db by chaning the whole direcoty into 777, the whole blue_hydra servcie will behave very stange and not stable
        loadDeviceFromDB()
        
        #send to kafaka
        upload_devices = []
        for rssi_mac, values in all_records.items():
            if rssi_mac in all_devices:
                for location, (ts, rssi) in values.items():
                    rssi_log = copy.deepcopy(all_devices[rssi_mac])
                    rssi_log['location'] = location
                    rssi_log['signal'] = rssi
                    rssi_log['time'] = ts #datetime.fromtimestamp(int(ts)).utcnow().isoformat("T")
                    upload_devices.append(rssi_log)
            else:
                logger.warning('upload task: found riss reocrd with mac not existed in device DB!')
        logger.info('upload task: to send {} device+rssi records'.format(len(upload_devices)))      
        t = threading.Thread(target=sendMsg, args=(upload_devices,))
        t.start()


        if dbtool:
            upload_devices = []
            for rssi_mac, rssi_values in all_records.items():
                if rssi_mac in all_devices:
                    for location, (ts, rssi) in rssi_values.items():
                        rssi_log = copy.deepcopy(all_devices[rssi_mac])
                        rssi_log['signal'] = rssi
                        print(ts)
                        rssi_log['time'] = ts #datetime.fromtimestamp(int(ts)).utcnow().isoformat("T")
                    upload_devices.append(rssi_log)
                    #print('upload task loop: build upload record -- ', rssi_log)
            logger.info('upload_tsdb task loop: built {} device+rssi records'.format(len(upload_devices)))      
            t = threading.Thread(target=dbtool.upload, args=(upload_devices,))
            t.start()

        


if __name__ == '__main__':

    #wait for bluehydra service
    #while not checkIfProcessRunning(config.bluehydra_process_name):
    #    time.sleep(1)
    #print('found bluehydra!')

    #load current devices
    #initDeviceFromDB()
    #print('found time valid devices {}'.format(len(all_devices)))

    collect_t = threading.Thread(name='{}_collect_bt_task'.format(config.robot_id), target=collect_bluehydra, args=(config.collect_time_mini_interval,))
    # collect_t.setDaemon(True)
    collect_t.start()

    upload_t = threading.Thread(name='{}_upload_bt_task'.format(config.robot_id), target=upload2datacenter, args=(config.upload_time_mini_interval,))
    # upload_t.setDaemon(True)
    upload_t.start()
