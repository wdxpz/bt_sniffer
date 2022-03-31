# Environment

## change apt-get source to ustc
1. /etc/apt/sources.list
```
注释掉已配置好的raspberry官方镜像，使用#号注释(或直接删除，哈哈)

添加中科大源镜像：
deb http://mirrors.ustc.edu.cn/raspbian/raspbian/ buster main contrib non-free rpi
```
2. sudo vim /etc/apt/sources.list.d/raspi.list
```
注释掉原内容，并以以下内容替换：

deb http://mirrors.ustc.edu.cn/archive.raspberrypi.org/debian/ buster main ui
```
3. ** remember to change stretch to buster ** for raspberry buster system

## install ubertooth driver
1. Prerequisites
```
sudo apt-get install git cmake libusb-1.0-0-dev make gcc g++ libbluetooth-dev \
pkg-config libpcap-dev python-numpy python-pyside python-qt4
```
or compile as [Raspberry Pi - Blue Hydra bluetooth logger](https://wiki.polaire.nl/doku.php?id=blue_hydra_ubertooth_pi)
2. build libbtbb
```
git clone https://github.com/greatscottgadgets/libbtbb.git
cd libbtbb
mkdir build
cd build
cmake ..
make
sudo make install
```
***Linux users: if you are installing for the first time, or you receive errors about finding the library, you should run:***
```
sudo ldconfig
```
3. build Ubertooth tool
1. The Ubertooth repository contains host code for sniffing Bluetooth packets, configuring the Ubertooth and updating firmware. All three are built and installed by default using the following method:
```
git clone https://github.com/greatscottgadgets/ubertooth.git
cd ubertooth/host
mkdir build
cd build
cmake ..
make
sudo make install
```
***Linux users: if you are installing for the first time, or you receive errors about finding the library, you should run:***
```
sudo ldconfig
```

## install blue_hydra
a bluetooth sniffering tool, combined with Ubertooth one, which can sniffer data from Lower Address Part (LAP), no like the original Kismet, which can only sniffer data from HCI level

this blue_hydra is clone from : [ZeroChao BlueHydra](https://github.com/ZeroChaos-/blue_hydra), which seems recording all sniffered bluetooth devices, not like the [original bluehydra](https://github.com/greatscottgadgets/ubertooth/wiki/Capturing-BLE-in-Wireshark)


1. clone source and build it
```
git clone https://github.com/ZeroChaos-/blue_hydra
```
2. if error `An error occurred while installing louis (2.3.4), and Bundler cannot continue.
Make sure that `gem install louis -v '2.3.4'` succeeds before bundling.`

```
#update system ruby to 2.4.0 or 2.5.1, 
# refer https://askubuntu.com/questions/839775/how-do-i-upgrade-to-ruby-2-2-on-my-ubuntu-system
sudo apt update
sudo apt-add-repository ppa:brightbox/ruby-ng && sudo apt-get update
sudo apt-get install ruby2.4 ruby2.4-dev
```
3. if error `blue hydra Unable to read the mac address from hci0`
```
sudo apt install bluez

#and then check the hci by
 hciconfig -a
 
```
5. config
  * open rssi log, in `blue_hydra_source_dir/blue_hydra.yml`
```
rssi_log: true

```
  * systemd service, [template service file](docs/blue_hydra.service)

### install bluehydar on rosbot
1. **for rosbot has no embeded bluetooth adapter, bluehydra will fail to start**
* refer [this](https://github.com/pwnieexpress/blue_hydra/issues/57) for the reason: ubertooth is not a bluetooth adapter. While ubertooth is supported, it is only supported in addition to a bluetooth adapter. Please plug in a bluetooth adapter to use blue_hydra
* for bluetooth adapter compatible with ubuntu, please refer: [HardwareSupportComponentsBluetoothUsbAdapters](https://wiki.ubuntu.com/HardwareSupportComponentsBluetoothUsbAdapters)

2. **remeber to modifiy the file path of delete_file.sh in blue_hydra.service file and pathes of blue_hydra_rssi.log and bt_sniffer.log in delete_file.sh**

3. modify and deploy blue_hydra.service
```
#remeber to modifiy the workspace and file path 
cp template_blue_hydar.serice /etc/systemd/system/blue_hydra.service
sudo systemctl enable blue_hydra.service
sudo systemctl start blue_hydra.service
sudo systemctl status blue_hydra.service
```

# Reference
1. File loaction
to collect bluetooth device information, it is needed to combine the data from two sources:
    * table blue_hydra_devices from blue_hydra.db in `source_dir_blue_hydra`
    * the blue_hydra_rssi.log in `source_dir_blue_hydra`


2. [**Ignored**, no longer to do it]
permission of blue_hydra.db
**currently, if we change the persission of blue_hydra like this way, it will cause serious problem on staring blue_hydra and generating rssi_log file after forced delete**
change the permission of blue_hydra.db for the further step to add trigger function
```
chmod 777 -R source_dir_of_blue_hydra
```

3. Smaple Codes:
    * a sql script to load device from blue_hydra_device db from [](https://github.com/pwnieexpress/pwn_pad_sources/blob/develop/scripts/blue_hydra.sh)
```
SELECT address, name, vendor, company, manufacturer, 
       classic_mode AS classic, 
       le_mode AS le, le_address_type, 
       updated_at as last_seen,
       classic_major_class, classic_minor_class, classic_class 
FROM blue_hydra_devices 
WHERE CAST(strftime('%s',updated_at) AS integer) 
BETWEEN CAST($START_TIME AS integer) AND CAST($STOP_TIME AS integer);
```
    * a sample code to exec sql query from [](https://github.com/corbanvilla/BluetoothDetection/blob/master/python/query.py):

# Deploy bt_sniffer service
## enviroment of needed packages
```
pip3 install timeloop
sudo apt-get install python3-influxdb
```

## modification of blue_hydra source codes
1. modify runner.rb to recreate blue_hydra_rssi.log file after forced delete from python scrip
add some codes between line 835 and 836, like:

```
#file location: `blue_hydra_source_dir/lib/blue_hydra/runner.rb`
#line 835: msg = [ts, type, address, rssi].join(' ')

rssi_logfile = File.expand_path('../../../blue_hydra_rssi.log', __FILE__)
if not File.exists?(rssi_logfile)
  puts "reopen rssi log file"
  BlueHydra.rssi_logger.reopen(rssi_logfile)
end

#line 836: BlueHydra.rssi_logger.info(msg)

```
2. modify blue_hydra.rb to change the default set to enable rssi_log


```
#file location: 'blue_hydra_source_dir/lib/blue_hydra.rb'

#line 69
"rssi_log"           => true,
```

3. Deploy: make the sniffer.py as service
  * modify the robot id in `project_dir/config.py`, change `robot_id` and `id`
```
robot_id='tb3_0'
id = robot_id+'-bt01'

```

  * nano wifi_sniffer.servcie

```
[Unit]
Description=BT Sniffer Service

[Service]
Type=idle
User=pi
Group=pi
ExecStart=/usr/bin/python3 /home/pi/projects/bt_sniffer/sniffer.py
Restart=always

[Install]
WantedBy=multi-user.target
```

** key: need to add 'User/Group=pi' for raspberry, 'User/Group=husarion' for rosbot, otherwise, the module Kismest_rest will not be loaded **


  * Steps to start service

```
$ cd project_dir
$ sudo cp wifi_sniffer.service /lib/systemd/system/bt_sniffer.service
$ sudo chmod 644 /lib/systemd/system/bt_sniffer.service
$ sudo systemctl daemon-reload
$ sudo systemctl enable bt_sniffer.service
$ sudo systemctl start bt_sniffer.service
```
