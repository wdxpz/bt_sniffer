robot_id='tb3_0'
id = robot_id+'-bt01'

bluehydra_process_name = 'blue_hydra'
bluehydra_path = '/home/pi/sources/blue_hydra'
bluehydra_rssi_log_file = 'blue_hydra_rssi.log'
bluehydra_db_file = 'blue_hydra.db'

#the valid device is from device_time_shift_hour hours ago
device_time_shift_hour = 1

collect_time_interval = 1
upload_time_interval = 1
collect_time_mini_interval = 0.2
upload_time_mini_interval = 0.5

#tsdb
Enable_TSDB = True
upload_URL = 'www.bestfly.ml'
upload_PORT = 8086
upload_DB = 'robot'
upload_table = 'bt_sniffer'

#kafaka
topic = "bt_sniffer"
brokers = ["192.168.12.146:9092"] # current internal brokers(actually 3 brokers behind)
block_waiting_time = 1

#redis
redis_host = "192.168.12.146"
redis_port = "6379"

#log file
log_file = '/home/pi/projects/bt_sniffer/bt_sniffer.log'
