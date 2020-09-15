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
from kafaka import sendMsg
from logger import logger
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
dbtool = DBHelper() if Enable_TSDB else None
#use a lock to avoid the case of simutaneous reading of the buehydar_rssi_log file
collect_task_lock = threading.Lock()

#TODO: need redis uri
r = redis.Redis()

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
    if r is None:
        msg = "exit because Redis connection is failed!"
        logger.error(msg)
        raise Exception(msg)
    location = r.get(config.robot_id)

    return location
        

#collect devices from kismet very config.collect_time_mini_interval seconds 
def collect_bluehydra(interval):
    while True:

        time.sleep(interval)
        
       
        # #wait for task lock
        # collect_task_lock.acquire()
        
        if not os.path.exists(rssilogPath):
            logger.info('collect task loop: not find blue_hydra_rssi.log, exit!')
            # collect_task_lock.release()
            continue

        location = getLocation()
        if location is None or len(location)<2:
            # collect_task_lock.release()
            continue

        rssi_records = {}
        
        # empty current rssi log
        rssilogbakPath = rssilogPath+'.bak'
        shutil.copyfile(rssilogPath, rssilogbakPath)
        os.remove(rssilogPath)

        with open(rssilogbakPath) as rssilog:
            logs = rssilog.readlines()
                            
            for log_line in logs[1:]:
                log_line = log_line[:-1]
                log_fields = log_line.split(' ')
                ts, mac, rssi = log_fields[0], log_fields[2], log_fields[3]
                if mac not in rssi_records:
                    rssi_records[mac] = {'rssi': {ts: rssi}, 'location': location} 
                else:
                    #filter repeated (mac, ts, rssi) records
                    if ts in rssi_records[mac]:
                        continue
                    rssi_records[mac]['rssi'][ts] = rssi
            logger.info('collect task loop: processed {} mac: ts: rssi records from {} original rssi records'.format(len(rssi_records), len(logs)-1))
            #print('collect task loop: processed records \n', rssi_records)

        upload_cache.put(rssi_records)
        
        # collect_task_lock.release()
    
    
#upload to data center every config.upload_time_mini_interval
def upload2datacenter(interval):
    
    while True:

        time.sleep(interval)

        all_records = {}
        
        #unify the rssi_records in buffer to all_records
        while not upload_cache.empty():
            records = upload_cache.get()
            if len(all_records) == 0:
                all_records = records
            else:
                for record_mac, record_rssis in records.items():
                    if record_mac in all_records:
                        for ts, rssi in record_rssis.items():
                            if ts in all_records[record_mac]:
                                continue
                            all_records[record_mac][ts] = rssi
                    else:
                        all_records[record_mac] = record_rssis
                        
            upload_cache.task_done()
        logger.info('upload task loop: unified {} rssi records'.format(len(all_records)))
        #print('upload task loop: processed records \n', upload_cache)
        
        if len(all_records) == 0:
            continue
        
        #update device table
        #todo: can be improve by sqlite3 triger, the curretn problem
        #is the blue_hydra.db is reaonly so we can not add trigger into it
        #while once we change the right property of blue_hydra.db by chaning the whole direcoty into 777, the whole blue_hydra servcie will behave very stange and not stable
        loadDeviceFromDB()
        
        #send to kafaka
        upload_devices = []
        for rssi_mac, values in all_records.items():
            if rssi_mac in all_devices:
                rssi_values = values['rssi']
                location = values['location']
                rssi_log = copy.deepcopy(all_devices[rssi_mac])
                rssi_log['location'] = location
                rssi_log['signal'] = -sys.maxint
                rssi_log['time'] = None
                for timestamp, rssi in rssi_values.items():
                        if rssi > rssi_log['signal']:
                            rssi_log['signal'] = rssi
                            rssi_log['time'] = datetime.fromtimestamp(int(timestamp)).utcnow().isoformat("T")
                upload_devices.append(rssi_log)
            logger.info('sendMsg_kafuka task: built {} device+rssi records'.format(len(upload_devices)))      
            t = threading.Thread(target=sendMsg, args=(upload_devices,))
            t.start()


        if dbtool:
            upload_devices = []
            for rssi_mac, rssi_values in all_records.items():
                if rssi_mac in all_devices:
                    for timestamp, rssi in rssi_values.items():
                        rssi_log = copy.deepcopy(all_devices[rssi_mac])
                        rssi_log['signal'] = rssi
                        rssi_log['time'] = datetime.fromtimestamp(int(timestamp)).utcnow().isoformat("T")
                    upload_devices.append(rssi_log)
                    #print('upload task loop: build upload record -- ', rssi_log)
            logger.info('upload_tsdb task loop: built {} device+rssi records'.format(len(upload_devices)))      
            t = threading.Thread(target=dbtool.upload, args=(upload_devices,))
            t.start()

        


if __name__ == 'main':

    #wait for bluehydra service
    #while not checkIfProcessRunning(config.bluehydra_process_name):
    #    time.sleep(1)
    #print('found bluehydra!')

    #load current devices
    #initDeviceFromDB()
    #print('found time valid devices {}'.format(len(all_devices)))

    collect_t = threading.Thread(name='{}_collect_bt_task'.format(config.robot_id), target=collect_bluehydra, args=(config.collect_time_mini_interval,))
    collect_t.setDaemon(True)
    collect_t.start()

    upload_t = threading.Thread(name='{}_upload_bt_task'.format(config.robot_id), target=upload2datacenter, args=(config.upload_time_mini_interval,))
    upload_t.setDaemon(True)
    upload_t.start()
