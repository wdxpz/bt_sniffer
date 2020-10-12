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
import shutil
import time
import requests
import copy
from queue import Queue
from datetime import timedelta, datetime

from timeloop import Timeloop

import config
from tsdb import DBHelper
from logger import logger

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
sql_trigger_insert_name = 'insert_device'
sqlTriggerInsert = "CREATE TRIGGER {} AFTER UPDATE ON blue_hydra_devices \
                 BEGIN SELECT updateDevice(NEW.address, \
                                           NEW.name, \
                                           NEW.vendor, \
                                           NEW.company, \
                                           NEW.manufacturer, \
                                           NEW.updated_at, \
                                           NEW.classic_major_class, \
                                           NEW.classic_minor_class); \
                  END;".format(sql_trigger_insert_name)
sql_trigger_update_name = 'update_device'
sqlTriggerUpdate = "CREATE TRIGGER update_device AFTER UPDATE ON blue_hydra_devices \
                 BEGIN SELECT updateDevice(NEW.address, \
                                           NEW.name, \
                                           NEW.vendor, \
                                           NEW.company, \
                                           NEW.manufacturer, \
                                           NEW.updated_at, \
                                           NEW.classic_major_class, \
                                           NEW.classic_minor_class); \
                 END;"
#.format(sql_trigger_update_name)

upload_cache = Queue(maxsize=0)
all_devices = {}
dbtool = DBHelper()

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

def updateDevice(address, name, vendor, company, manufacture, updated_at, classic_major_class, classic_minor_class):
    manuf = company if company else vendor
    manuf = manufacture if manufacture else manuf 
    all_devices[address] = {
                'mac': address,
                'name': name,
                'manuf': manuf,
                'last_seen': updated_at,
                'major_type': classic_major_class,
                'minor_type': classic_minor_class
     }
    logger.info('device updated or created: ', all_devices[address])

def initDeviceFromDB():
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
            logger.info('device from existed db: ', all_devices[record[0]])

    try:
        conn.create_function("updateDevice", 8, updateDevice)
        cur = conn.cursor()
        cur.execute("DROP TRIGGER IF EXISTS {};".format(sql_trigger_insert_name))
        cur.execute(sqlTriggerInsert)
        cur.execute("DROP TRIGGER IF EXISTS {};".format(sql_trigger_update_name))
        cur.execute(sqlTriggerUpdate)
        print('created db triggers')
        #test
        #cur.execute("UPDATE blue_hydra_devices \
        #     SET name='test5' \
        #     where address = '25:23:79:22:A0:7E';")
    except Exception as e:
        logger.error("Unable to create trigger in database: " + str(e))
    
    return

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

def upload(devices):
    # data to be sent to api
    #data = {'data':devices}
    data = devices
    # sending post request and saving response as response object
    try:
        #r = requests.post(url = config.upload_endpoint, data = data)
        dbtool.upload(data)
        logger.info('upload thread: uploaded {} devices'.format(len(devices)))
    except Exception as errh:
        logger.error("Http Error:",errh, "\n on devices: \n", devices)


#wait for bluehydra service
#while not checkIfProcessRunning(config.bluehydra_process_name):
#    time.sleep(1)
#print('found bluehydra!')

#load current devices
#initDeviceFromDB()
#print('found time valid devices {}'.format(len(all_devices)))

#use a lock to avoid the case of simutaneous reading of the buehydar_rssi_log file
collect_task_lock = threading.Lock()

tl = Timeloop()

#collect devices from kismet very config.collect_time_interval seconds 
@tl.job(interval=timedelta(seconds=config.collect_time_interval))
def collect_bluehydra():
    #wait for task lock
    collect_task_lock.acquire()

    #wait for bluehydra_rssi_log file
    #while not os.path.exists(rssilogPath):
    #    time.sleep(1)
    
    if not os.path.exists(rssilogPath):
        logger.info('collect task loop: not find blue_hydra_rssi.log, exit!')
        collect_task_lock.release()
        return

    rssi_records = {}
    
    # empty current rssi log
    rssilogbakPath = rssilogPath+'.bak'
    shutil.copyfile(rssilogPath, rssilogbakPath)
    os. remove(rssilogPath)

    with open(rssilogbakPath) as rssilog:
        logs = rssilog.readlines()
                           
        for log_line in logs[1:]:
            log_line = log_line[:-1]
            log_fields = log_line.split(' ')
            ts, mac, rssi = log_fields[0], log_fields[2], log_fields[3]
            if mac not in rssi_records:
                rssi_records[mac] = {ts: rssi} 
            else:
                #filter repeated (mac, ts, rssi) records
                if ts in rssi_records[mac]:
                    continue
                rssi_records[mac][ts] = rssi
        logger.info('collect task loop: processed {} mac: ts: rssi records from {} original rssi records'.format(len(rssi_records), len(logs)-1))
        #print('collect task loop: processed records \n', rssi_records)

    upload_cache.put(rssi_records)
    
    collect_task_lock.release()
    
    
#upload to data center
@tl.job(interval=timedelta(seconds=config.upload_time_interval))
def upload2datacenter():
    
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
        return
    
    #update device table
    #todo: can be improve by sqlite3 triger, the curretn problem
    #is the blue_hydra.db is reaonly so we can not add trigger into it
    #while once we change the right property of blue_hydra.db by chaning the whole direcoty into 777, the whole blue_hydra servcie will behave very stange and not stable
    loadDeviceFromDB()
    
    upload_devices = []
    for rssi_mac, rssi_values in all_records.items():
        if rssi_mac in all_devices:
            for timestamp, rssi in rssi_values.items():
                rssi_log = copy.deepcopy(all_devices[rssi_mac])
                rssi_log['signal'] = rssi
                rssi_log['time'] = datetime.fromtimestamp(int(timestamp)).utcnow().isoformat("T")
            upload_devices.append(rssi_log)
            #print('upload task loop: build upload record -- ', rssi_log)
    logger.info('upload task loop: built {} device+rssi records'.format(len(upload_devices)))
    
        
    t = threading.Thread(target=dbtool.upload, args=(upload_devices,))
    t.start()
    
    return



tl.start(block=True)
