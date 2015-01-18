#!/usr/bin/python
# MySensors-Domoticz handler - JSON-database 
# uses local python dictionary DB for storage of sensors, values and updates
# Database is stored in "MySensors_DB.txt" in human readable/editable format
# Role of the database is "translation" of MySensors and Domoticz as this is not one-on-one
#
# there is not much error checking... make sure you understand the basic functionality
# Installation:
# - make sure that python libraries are installed (mostly only requests is needed)
# - put the script somewhere where your scripts reside, make sure to add the database "MySensors_DB.txt"! 
# - make sure you made a backup of the Domoticz database
# - edit this script GATEWAY_PORT & DOMOTICZ 
# - edit "MySensors_DB.txt" to reflect at least one of your Sensors. Make sure the Domoticz id's are existing as Virtual devices in Domoticz.
# - the script needs rights for reading the serial port: run the script from the command line like:  sudo python My_Sensors.py   
# - for unattended run (after testing): sudo python MySensorsController.py > /dev/null &
# - if you want to editing the  "MySensors_DB.txt" be sure to stop the scrip when running in background. (sudo ps ax | grep python - for the process id and sudo kill <id>
# 
# for the combined Temp, Hum, Baro devices:
# - as MySensors only supports 'single' sensors: assign the respective individual sensors in the database 
#		"MySensors_DB.txt" the same domoticz id and D_T_H of D_T_H_B domoticz Type, they will be combined by the script if present
import time, calendar
import json
import serial
import requests
# import sqlite3 # for future DB update?

###########################################
# Constants definition
###########################################
# MySensors Gateway serial, attached to USB0 
##########################################
GATEWAY_PORT = '/dev/ttyUSB0'	# specify absolute USB port of MySensors Gateway (defined in rules.d)
# Open serial port for S0 meter, timeout is 0 second: non-blocking
ser = serial.Serial(GATEWAY_PORT, 115200, timeout=0)
# constants
MAX_NODE_ID = 255 			# maximum number of nodes allowed
###############################################
# Domoticz address & virtual meters/ variables
###############################################
DOMOTICZ_IP = "127.0.0.1"	# IP of domoticz metering system (on this system)
DOMOTICZ_PORT = "8080"		# Port number
DOMOTICZ_MYSENSORS_ID = "2" # MySensors hardware ID in Domoticz

# MySensors message type definitions and handlers
# message structure = [1]node-id ; [2]child-sensor-id; [3]message-type; [4]ack; [5]sub-type; [6]payload\n
# Sensor message types
MS_MessageType = {
    'PRESENTATION': {'id': 0, 'comment': 'Sent by a node when they present attached sensors. This is usually done in setup() at startup.'},
    'SET': {'id': 1, 'comment': 'This message is sent from or to a sensor when a sensor value should be updated'},
    'REQ': {'id': 2, 'comment': 'Requests a variable value (usually from an actuator destined for controller).'},
    'INTERNAL': {'id': 3, 'comment': 'This is a special internal message. See table below for the details'},
    'STREAM': {'id': 4, 'comment': 'Used for OTA firmware updates'},
}
def MSmessageTypeID(label):
# get MySensors messagetype id for label, no error check
	global MS_MessageType  # list
	return MS_MessageType[label]['id']

def MSmessageTypeLabelForID(id):
# get MySensors messagetype id for label, no error check
	global MS_MessageType  # list
	for sensor in MS_MessageType:
		if MS_MessageType[sensor]['id'] == id:
			return( sensor )

# Mysensors presentation types and values and Domoticz default equivalent
MS_Presentation = {
    'S_DOOR': {'id': 0, 'comment': 'Door and window sensors', 		'dcz_type': 'D_SWITCH'},
    'S_MOTION': {'id': 1, 'comment': 'Motion sensors', 				'dcz_type': 'D_SWITCH'}, # cannot be created as JSON virtual
    'S_SMOKE': {'id': 2, 'comment': 'Smoke sensor',					'dcz_type': 'D_SWITCH'},
    'S_LIGHT': {'id': 3, 'comment': 'Light Actuator (on/off)', 		'dcz_type': 'D_SWITCH'},
    'S_DIMMER': {'id': 4, 'comment': 'Dimmable device of some kind','dcz_type': 'D_SWITCH'}, # subtype of Switch, set level 0..100
    'S_COVER': {'id': 5, 'comment': 'Window covers or shades', 		'dcz_type': 'D_SWITCH'},
    'S_TEMP': {'id': 6, 'comment': 'Temperature sensor', 			'dcz_type': 'D_TEMP'},
    'S_HUM': {'id': 7, 'comment': 'Humidity sensor', 				'dcz_type': 'D_HUM'},
    'S_BARO': {'id': 8, 'comment': 'Barometer sensor (Pressure)', 	'dcz_type': 'D_T_H_B'}, # combined sensor
    'S_WIND': {'id': 9, 'comment': 'Wind sensor', 					'dcz_type': 'D_WIND'}, # complex sensor, tbd
    'S_RAIN': {'id': 10, 'comment': 'Rain sensor', 					'dcz_type': 'D_RAIN'},
    'S_UV': {'id': 11, 'comment': 'UV sensor', 						'dcz_type': 'D_UV'},
    'S_WEIGHT': {'id': 12, 'comment': 'Weight sensor for scales etc.', 'dcz_type': None},
    'S_POWER': {'id': 13, 'comment': 'Power measuring device, like power meters', 'dcz_type': 'D_ENERGY'},
    'S_HEATER': {'id': 14, 'comment': 'Heater device',				'dcz_type': 'D_SWITCH'},
    'S_DISTANCE': {'id': 15, 'comment': 'Distance sensor', 			'dcz_type': None},
    'S_LIGHT_LEVEL': {'id': 16, 'comment': 'Light sensor', 			'dcz_type': 'D_LUX'},
    'S_ARDUINO_NODE': {'id': 17, 'comment': 'Arduino node device', 	'dcz_type': None},
    'S_ARDUINO_RELAY': {'id': 18, 'comment': 'Arduino repeating node device', 'dcz_type': None},
    'S_LOCK': {'id': 19, 'comment': 'Lock device', 					'dcz_type': 'D_SWITCH'},
    'S_IR': {'id': 20, 'comment': 'Ir sender/receiver device', 		'dcz_type': None},
    'S_WATER': {'id': 21, 'comment': 'Water meter', 				'dcz_type': None},
    'S_AIR_QUALITY': {'id': 22, 'comment': 'Air quality sensor e.g. MQ-2', 'dcz_type': 'D_AIRQUALITY'},
    'S_CUSTOM': {'id': 23, 'comment': 'Use this for custom sensors where no other fits.', 'dcz_type': None},
    'S_DUST': {'id': 24, 'comment': 'Dust level sensor', 			'dcz_type': None},
    'S_SCENE_CONTROLLER': {'id': 25, 'comment': 'Scene controller device', 'dcz_type': None}, # special type, can be implemented?
}
def MSpresentationID(label):
# get MySensors presentation id for label, no error check
	global MS_Presentation  # list
	return MS_Presentation[label]['id']
	
def MSpresentationLabelForID(id):
# get MySensors messagetype id for label, no error check
	global MS_Presentation  # list
	for sensor in MS_Presentation:
		if MS_Presentation[sensor]['id'] == id:
			return( sensor )
	
# Sensor values
MS_SetReq = {
    'V_TEMP': {'id': 0, 'comment': 'Temperature'},
    'V_HUM': {'id': 1, 'comment': 'Humidity'},
    'V_LIGHT': {'id': 2, 'comment': 'Light status. 0=off 1=on'},
    'V_DIMMER': {'id': 3, 'comment': 'Dimmer value. 0-100%'},
    'V_PRESSURE': {'id': 4, 'comment': 'Atmospheric Pressure'},
    'V_FORECAST': {'id': 5, 'comment': 'Whether forecast. One of stable, sunny, cloudy, unstable, thunderstorm or unknown'},
    'V_RAIN': {'id': 6, 'comment': 'Amount of rain'},
    'V_RAINRATE': {'id': 7, 'comment': 'Rate of rain'},
    'V_WIND': {'id': 8, 'comment': 'Windspeed'},
    'V_GUST': {'id': 9, 'comment': 'Gust'},
    'V_DIRECTION': {'id': 10, 'comment': 'Wind direction'},
    'V_UV': {'id': 11, 'comment': 'UV light level'},
    'V_WEIGHT': {'id': 12, 'comment': 'Weight (for scales etc)'},
    'V_DISTANCE': {'id': 13, 'comment': 'Distance'},
    'V_IMPEDANCE': {'id': 14, 'comment': 'Impedance value'},
    'V_ARMED': {'id': 15, 'comment': 'Armed status of a security sensor. 1=Armed, 0=Bypassed'},
    'V_TRIPPED': {'id': 16, 'comment': 'Tripped status of a security sensor. 1=Tripped, 0=Untripped'},
    'V_WATT': {'id': 17, 'comment': 'Watt value for power meters'},
    'V_KWH': {'id': 18, 'comment': 'Accumulated number of KWH for a power meter'},
    'V_SCENE_ON': {'id': 19, 'comment': 'Turn on a scene'},
    'V_SCENE_OFF': {'id': 20, 'comment': 'Turn of a scene'},
    'V_HEATER': {'id': 21, 'comment': 'Mode of header. One of Off, HeatOn, CoolOn, or AutoChangeOver'},
    'V_HEATER_SW': {'id': 22, 'comment': 'Heater switch power. 1=On, 0=Off'},
    'V_LIGHT_LEVEL': {'id': 23, 'comment': 'Light level. 0-100%'},
    'V_VAR1': {'id': 24, 'comment': 'Custom value'},
    'V_VAR2': {'id': 25, 'comment': 'Custom value'},
    'V_VAR3': {'id': 26, 'comment': 'Custom value'},
    'V_VAR4': {'id': 27, 'comment': 'Custom value'},
    'V_VAR5': {'id': 28, 'comment': 'Custom value'},
    'V_UP': {'id': 29, 'comment': 'Window covering. Up.'},
    'V_DOWN': {'id': 30, 'comment': 'Window covering. Down.'},
    'V_STOP': {'id': 31, 'comment': 'Window covering. Stop.'},
    'V_IR_SEND': {'id': 32, 'comment': 'Send out an IR-command'},
    'V_IR_RECEIVE': {'id': 33, 'comment': 'This message contains a received IR-command'},
    'V_FLOW': {'id': 34, 'comment': 'Flow of water (in meter)'},
    'V_VOLUME': {'id': 35, 'comment': 'Water volume'},
    'V_LOCK_STATUS': {'id': 36, 'comment': 'Set or get lock status. 1=Locked, 0=Unlocked'},
    'V_DUST_LEVEL': {'id': 37, 'comment': 'Dust level'},
    'V_VOLTAGE': {'id': 38, 'comment': 'Voltage level'},
    'V_CURRENT': {'id': 39, 'comment': 'Current level'},
}
def MSsetreqID(label):
# get MySensors set request id from label, no error check
	global MS_SetReq  # list
	return MS_SetReq[label]['id']

# Internal types & values
MS_Internal = {
    'I_BATTERY_LEVEL': {'id': 0, 'comment': 'Use this to report the battery level (in percent 0-100).'},
    'I_TIME': {'id': 1, 'comment': 'Sensors can request the current time from the Controller using this message. The time will be reported as the seconds since 1970'},
    'I_VERSION': {'id': 2, 'comment': 'Sensors report their library version at startup using this message type'},
    'I_ID_REQUEST': {'id': 3, 'comment': 'Use this to request a unique node id from the controller.'},
    'I_ID_RESPONSE': {'id': 4, 'comment': 'Id response back to sensor. Payload contains sensor id.'},
    'I_INCLUSION_MODE': {'id': 5, 'comment': 'Start/stop inclusion mode of the Controller (1=start, 0=stop).'},
    'I_CONFIG': {'id': 6, 'comment': 'Config request from node. Reply with (M)etric or (I)mperal back to sensor.'},
    'I_FIND_PARENT': {'id': 7, 'comment': 'When a sensor starts up, it broadcast a search request to all neighbor nodes. They reply with a I_FIND_PARENT_RESPONSE.'},
    'I_FIND_PARENT_RESPONSE': {'id': 8, 'comment': 'Reply message type to I_FIND_PARENT request.'},
    'I_LOG_MESSAGE': {'id': 9, 'comment': 'Sent by the gateway to the Controller to trace-log a message'},
    'I_CHILDREN': {'id': 10, 'comment': 'A message that can be used to transfer child sensors (from EEPROM routing table) of a repeating node.'},
    'I_SKETCH_NAME': {'id': 11, 'comment': 'Optional sketch name that can be used to identify sensor in the Controller GUI'},
    'I_SKETCH_VERSION': {'id': 12, 'comment': 'Optional sketch version that can be reported to keep track of the version of sensor in the Controller GUI.'},
    'I_REBOOT': {'id': 13, 'comment': 'Used by OTA firmware updates. Request for node to reboot.'},
    'I_GATEWAY_READY': {'id': 14, 'comment': 'Send by gateway to controller when startup is complete.'},
}
def MSinternalID(label):
# get MySensors internal id from label, no error check
	global MS_Internal # list
	return MS_Internal[label]['id']
	
def MSinternalLabelForID(id):
# get MySensors internal label for id, no error check
	global MS_Internal  # list
	for sensor in MS_Internal:
		if MS_Internal[sensor]['id'] == id:
			return( sensor )
	
# Domoticz - Device types and values (to be) supported (from Domoticz/RFXtrx.h)
DCZ_DevType = {
	'D_PRESSURE' : {'id':  1, 'comment': 'Pressure (Airpressure in Bar, not Baro)' },
	'D_PERCENTAGE' : {'id':  2, 'comment': 'Percentage (generic)'},
	'D_SWITCH' : {'id':  17, 'comment': 'Switch'}, #(no 17, Switch cannot be created as JSON virtual device, will fail for now)
	'D_TEMP' : {'id':  80, 'comment': 'Temperature sensor'},
	'D_HUM' : {'id':  81, 'comment': 'Humidity sensor'},
	'D_T_H' : {'id':  82, 'comment': 'Temp Hum'},
	#'D_BARO' : {'id':  83, 'comment': '(Barometer, cannot be created as virtual device)'},
	'D_T_H_B' : {'id':  84, 'comment': 'Temp Hum Baro'},
	'D_RAIN' : {'id':  85, 	'comment': 'Rain sensor'},
	'D_WIND' : {'id':  86, 	'comment': 'Wind sensor'},
	'D_UV' : {'id':  87, 'comment': 'UV sensor'},
	'D_ENERGY' : {'id':  90, 'comment':'?? Power measuring device, like power meters'}, # 
	'D_TEXT' : {'id':  243, 'comment':' Text sensor'},
	'D_LUX' : {'id':  246, 'comment':' Light sensor'},
	'D_AIRQUALITY' : {'id':  249,'comment': ' Air Quality'}
}
def DCZdeviceTypeID(label):
# get MySensors internal id from label, no error check
	global DCZ_DevType # list
	return DCZ_DevType[label]['id']
	
def DCZdeviceLabelForID(id):
# get Domoticz messagetype label, no error check
	global DCZ_DevType  # list
	for device in DCZ_DevType:
		if DCZ_DevType[device]['id'] == id:
			return( device )
			
##########################################
# Local variables
##########################################
NodeIds = [] # list with used/available Node id's, filled from MySensors_DB at startup

def initNodeIds():
	# build the used Node table
	global NodeIds # table
	for i in xrange(MAX_NODE_ID): # set all to false
		NodeIds.append(False)
	for sensor in Sensor_DB: # set used to true
		if sensor["Node"]:
			NodeIds[sensor["Node"]] = True
	#print(NodeIds)
	return
		
###########################################
# MySensors Database & routines
# sensors are hardcoded for now:
# - Domoticz id's assume "virtual" created devices
# - Reading is last value (12 / 13 is just placeholder..)
###########################################
## just an example as reference, DB is stored in file MySensors_DB.txt as JSON, format should follow: 
# Sensor_DB = [{"Node": 1, "LastUpdate": null, "Domoticz_id": None, "Dcz_Type": "D_SWITCH", "Child": 1, "Reading": 12, "Type": "S_MOTION"}]			

def save_DB():
	global Sensor_DB
	# save (commit) Sensor_DB as JSON txt file
	# update or add the type text to make it readable and editable
	# for sensor in Sensor_DB:
		# print(sensor)
		# sensor["Type_comment"] = MSpresentationLabelForID(sensor["Type"]) # add/ replace key text for MS sensor
		# sensor["Dcz_Type_comment"] = DCZdeviceLabelForID(sensor["Dcz_Type"]) # add/ replace key text for Domoticz device
	with open('MySensors_DB.txt', 'w') as outfile:
		json.dump(Sensor_DB, outfile, indent=0, sort_keys = False, ensure_ascii=False)
		
def load_DB():
	global Sensor_DB
	# read Sensor_DB as JSON txt file
	with open('MySensors_DB.txt', 'r') as infile:
		Sensor_DB = json.load(infile)

## Check if node in DB and return dictionary
def DB_get_node(MS_node):
# returns None or list of entries (more sensors for one node)
    return [item for item in Sensor_DB if (item['Node'] == int(MS_node))]
			
## Check if sensor in DB and return dictionary
def DB_get_sensor(MS_node, MS_child):
# returns None or list of entries (more value types for one sensor)
    return [item for item in Sensor_DB if (item['Node'] == int(MS_node)) and (item['Child'] == int(MS_child))]

	## Check if sensor in DB and return dictionary
def DB_add_sensor(MS_node, MS_child, MS_devType, DCZ_dev, DCZ_devType):
# adds a record with attributes in the Sensor_DB
# returns True
	global Sensor_DB
	Sensor = {} # = Sensor_DB[0] # Take first line as reference
	Sensor["Node"] = int(MS_node)
	Sensor["Child"] = int(MS_child)
	Sensor["Type"] = MS_devType
	Sensor["Domoticz_id"] = int(DCZ_dev) # 0 for "None"
	Sensor["Dcz_Type"] = DCZ_devType
	Sensor["LastUpdate"] = None
	Sensor["Reading"] = 0
	Sensor_DB.append(Sensor)
	return True
	
## Check if Domoticz (dcz) device in DB and return dictionary
def DB_get_dczdev(DCZ_dev):
# returns None or list of entries (could > 1, if more values for one sensor)
    return [item for item in Sensor_DB if (item['Domoticz_id'] == int(DCZ_dev))]
	
## replace reading in DB for MS device
## Sensor_DB[0]["Domoticz_id"] = 999 # i.e. locate the sensor and replace value
def DB_replace_reading(MS_node, MS_child, new_value): # only call if node & sensor present!!
# input node & sensor = unique key
# new_reading = reading to be replaced
	global Sensor_DB
	for sensor in Sensor_DB: # for  
		if (sensor['Node'] == int(MS_node)) and (sensor['Child'] == int(MS_child)):
			sensor['Reading'] = new_value
			sensor['LastUpdate'] = time.strftime("%F %T") # set to current time
	return

## replace reading in DB for DCZ device
## Sensor_DB[0]["Domoticz_id"] = 999 # i.e. locate the sensor and replace value
def DB_replace_reading_dcz(DCZ_dev, new_value): # only call if present!!
# input dcz_dev = unique key
# new_reading = reading to be replaced
	global Sensor_DB
	for sensor in Sensor_DB:
		if (sensor['Domoticz_id'] == int(DCZ_dev)):
			sensor['Reading'] = new_value
			sensor['LastUpdate'] = time.strftime("%F %T") # set to current time
	return

## replace NodeInfo in DB for MS node
def DB_replace_nodeInfo(MS_node, new_value): 
# input dcz_dev = unique key
# new_reading = reading to be replaced 
	global Sensor_DB
	for sensor in Sensor_DB:
		if (sensor['Node'] == int(MS_node)):
			sensor['NodeInfo'] = new_value
	return
			
##########################################
# -- Domoticz routines
##########################################
# Open Domoticz json url, get JSON response and convert to list
##########################################
def dcz_request(dcz_json):
	try:
		request = requests.get('http://' + DOMOTICZ_IP + ':' + DOMOTICZ_PORT + dcz_json)
		#print(request.text)
		r = json.loads(request.text)
		#print(r)
	except requests.exceptions.ConnectionError as e:    # Check connection error in correct syntax
		print(time.strftime("%c") + " Call to Domoticz failed, not available.")
		print(e)
		r = "Error"
	except requests.exceptions.RequestException as e:    # Catch other exceptions
		print(time.strftime("%c") + " Call to Domoticz failed.")
		print(e)
		r = "Error"
	return (r)
	
# read values from domoticz device (json)
# input = variable index
# return = variable with attributes	
def read_domoticz_dev(dcz_var_idx):
	dcz_command = '/json.htm?type=devices&rid='+str(dcz_var_idx)
	#print(dcz_command)
	# load and convert from json in one line
	var_json=dcz_request(dcz_command)
	try:
		result = var_json["result"][0]
	except (ValueError, KeyError, TypeError):
		print(time.strftime("%c") + " Error receiving Domoticz data")
		result = "Error"
	return(result)

# read switches from domoticz (json)
# input = none
# return = variables with attributes	
def read_domoticz_switches():
	dcz_command = '/json.htm?type=devices&filter=light&used=true'
	# load and convert from json in one line
	var_json=dcz_request(dcz_command)
	try:
		result = var_json["result"]
	except (ValueError, KeyError, TypeError):
		print(time.strftime("%c") + " Error receiving Domoticz data")
		result = "Error"
	return(result)	

# send values to Domoticz virtual device (json)
# input = domoticz virtual device idx
# return = domoticz message (json)
# needs to adapt to Sensor type, limited number of sensors implemented, Domoticz "virtual devices" is default
# current (tested) set:
# - Humidity (V_HUM)  	: single device
# - Motion (V_TRIPPED)	: single (switch) device
# - Temperature (V_TEMP): Single device
# - Pressure (V_PRESSURE): Temp-Hum-Baro (5 values), single domoticz pressure is not Baro
# - Light (V_LIGHT)		: single device, lux
# - 
def send_domoticz_dev(dcz_dev):
	# first get (map) Domoticz device type from Database
	# Domoticz easily crashes database if incorrect JSON format sent, use domoticz device types to be sure
	DB_dcz_dev = DB_get_dczdev(dcz_dev)				# read records for this domoticz device
	dcz_dev_type = DB_dcz_dev[0]["Dcz_Type"]		# get domoticz device type from first record
	# ms_dev_type = DB_dcz_dev[0]["Type"]				# get MySensors device type
	dcz_dev_value = str(DB_dcz_dev[0]["Reading"])	# get value from first record and convert string for processing
	# handle accordingly
	if dcz_dev_type == 'D_HUM': # dcz humidity needs nvalue = Humidity & svalue = 0..3 (normal, comfortable, dry, wet)
		dcz_command= '/json.htm?type=command&param=udevice&idx=' + str(dcz_dev) + '&nvalue=' + dcz_dev_value + '&svalue=1'
		# print(dcz_command)
	elif dcz_dev_type == 'D_T_H': # combined Temp-hum device (set missing values to 0) 
		# workaround: find dcz devices for TEMP & HUMIDITY and use the lastvalues to complete the whole set... ;-)
		dev_temp_value = 0
		dev_hum_value = 0
		for sensor in DB_dcz_dev: # loop through records and gather all present values
			# check for corresponding sensor values
			#print(sensor, sensor["Type"])
			if (sensor["Type"] == 'S_TEMP'): 
				dev_temp_value = sensor["Reading"]
			elif (sensor["Type"] == 'S_HUM'): 
				dev_hum_value = sensor["Reading"]
		dcz_command= '/json.htm?type=command&param=udevice&idx='+str(dcz_dev)+'&nvalue=0&svalue='+str(dev_temp_value)+';'+str(dev_hum_value)+';0
	elif dcz_dev_type == 'D_T_H_B': # combined Temp-hum-baro device (set missing values to 0 (domoticz has no separate barometric virtual yet)
		# workaround: try to find dcz devices for BARO, TEMP & HUMIDITY and use the lastvalues to complete the whole set... ;-)
		dev_temp_value = 0
		dev_hum_value = 0
		dev_baro_value = 0 # in case not found set to 0
		for sensor in DB_dcz_dev: # loop through records and gather all present values
			# check for corresponding sensor values
			#print(sensor, sensor["Type"])
			if (sensor["Type"] == 'S_TEMP'): 
				dev_temp_value = sensor["Reading"]
			elif (sensor["Type"] == 'S_HUM'): 
				dev_hum_value = sensor["Reading"]
			elif (sensor["Type"] == 'S_BARO'):
				dev_baro_value = sensor["Reading"]
		dcz_command= '/json.htm?type=command&param=udevice&idx='+str(dcz_dev)+'&nvalue=0&svalue='+str(dev_temp_value)+';'+str(dev_hum_value)+';0;'+str(dev_baro_value)+';0'
	elif dcz_dev_type == 'D_SWITCH': # switch sensor same type as DIMMER, set domoticz type accordingly
		#/json.htm?type=command&param=switchlight&idx=&switchcmd=&level=0
		# print("motion sensor: ", dev_value)
		if DB_dcz_dev[0]["Type"] == "S_DIMMER": # dimmer, not a switch action, set only level
			dcz_command= '/json.htm?type=command&param=switchlight&idx=' + str(dcz_dev) + '&switchcmd=Set Level&level=' + dcz_dev_value
		else: # pure switch
			if dcz_dev_value == "1": # switch = on
				dcz_command= '/json.htm?type=command&param=switchlight&idx=' + str(dcz_dev) + '&switchcmd=On' + '&level=0'
			else: # dcz_dev_value) == "0"
				dcz_command= '/json.htm?type=command&param=switchlight&idx=' + str(dcz_dev) + '&switchcmd=Off' + '&level=0'
	elif dcz_dev_type in ['D_PRESSURE','D_PERCENTAGE','D_UV','D_TEMP','D_HUM','D_LUX']   : # currently supported devices
		# (light, ..., ,,,,:  no specific command, use default values 
		dcz_command= '/json.htm?type=command&param=udevice&idx=' + str(dcz_dev) + '&nvalue=0&svalue=' + dcz_dev_value
	else:
		pass  # do nothing, just send a dummy message, else risk of Domoticz DB crash
		dcz_command= '/json.htm?type=command&param=getSunRiseSet'
	result = dcz_request(dcz_command)
	#print(dcz_command)
	return(result)

# Create Domoticz virtual device (json) for new Sensors, 
# input = domoticz device type
# return = domoticz id or None
# needs: DOMOTICZ_MYSENSORS_ID, existing device type & carefull usage!!
def create_domoticz_dev(device_type):
	dcz_dev = 0 # 0  if no succes
	dcz_command = "/json.htm?type=createvirtualsensor&idx=" + str(DOMOTICZ_MYSENSORS_ID) + "&sensortype=" + str(device_type)
	if dcz_request(dcz_command)["status"] == "OK":
		### get device id: list unused devices and select last ID, make sure it is the right one
		dcz_command = "/json.htm?type=devices&filter=all&used=false&order=ID"
		devices = dcz_request(dcz_command)["result"]
		device = devices[len(devices)-1] # last in list
		if device["HardwareID"] == int(DOMOTICZ_MYSENSORS_ID): # make sure to get the right id: hardware & unused, created last
			dcz_dev = device["idx"]	# ["idx"] = device index
	return(dcz_dev) 
	
def get_dcz_temp_hum_baro(sensor): # not really needed here, for testing only
	# get sensor value in array, without units
	# Temp - Hum - Baro 
	dcz_dev_r = read_domoticz_dev( sensor ) # temperature, humidity, baro
	# split sensor data in elements with units and print individual
	# remove blanks between data and unit
	print(dcz_dev_r["Data"])
	return_array = []
	for sensor_data in dcz_dev_r["Data"].split(', '): # ", " between return values
		return_array.append(sensor_data.split(' ')[0]) # remove units
	return(return_array)
	
#############################################################
# Main Mysensors routines
###############################################################
# build MySensors telegram (message)
def MS_make_telegram(MS_node, MS_child, MS_type, MS_ack, MS_subtype, MS_payload):
	# builds telegram for sending to MySensors network
	# takes strings as argument
	telegram = ";".join((str(MS_node), str(MS_child), str(MS_type), str(MS_ack), str(MS_subtype), str(MS_payload)));
	print(telegram)
	return (telegram + "\n") # newline is needed to complete telegram


# debug and test: print the node types, attributes and values with unit	
def print_node_type(MS_node, MS_child, MS_type, MS_subtype, MS_payload):
	print("Node Info ", MS_node, MS_child, MS_type, MS_subtype, MS_payload)
	return

# tbd:Sensor needs to have the latest (own) status: get from DB or Domoticz
def process_MS_requestStatus():	
	return
	
# tbd:Sensor sends include
def process_MS_include():	
	return
	
# Find next available Node ID and set to not available
def getAvailableNodeID():
	global NodeIds
	for i in range(1,len(NodeIds)):
		if not NodeIds[i]:  # if not used, set used and return
			NodeIds[i] = True
			return(i)
	return(MAX_NODE_ID) # max if no one available
	
# Process the MySensors messages according to type	
# input = content of telegram
# global = Sensor_DB
def process_MS_message(	MS_node, MS_child, MS_type, MS_subtype, MS_payload):
	messageType = MSmessageTypeLabelForID(int(MS_type))
	#print(messageType)
	if messageType == 'SET':
		# print("Set sensor")
		# debug: print_node_type(MS_node, MS_child, MS_type, MS_subtype, MS_payload)
		DB_result = DB_get_sensor(MS_node, MS_child)
		# print("Sensor  ", Sensor)
		if DB_result != []: # if found in database (if not Sensor should be added)
			# update database and LastUpdate, Domoticz update is done from the database
			DB_replace_reading(MS_node, MS_child, MS_payload)
			Sensor = DB_result[0] # database can return many results, use only first one for now
			if (Sensor['Domoticz_id']) != 0:  # if domoticz_id present update domoticz, double check..
				send_domoticz_dev(Sensor['Domoticz_id'])
	elif messageType == 'REQ':
		# Sensor requested response
		# print("Request")
		DB_result = DB_get_sensor(MS_node, MS_child) # Determine message type from database
		if DB_result != []: # if found in database (if not, the Sensor should be added manually for now)
			# if there is a domoticz_id present then get message from Domoticz
			Sensor = DB_result[0] # database can return many results, use only first one for now
			# print("Req message, send response now")
			if (Sensor['Domoticz_id']) != 0: # if domoticz_id present get and send domoticz "Data" Value
				#print("Domoticz sensor", Sensor['Domoticz_id'], Sensor['Domoticz_id'])
				Message = read_domoticz_dev(Sensor['Domoticz_id'])['Data']
				telegram = MS_make_telegram(MS_node, MS_child, MSmessageTypeID('SET'), "0", MS_subtype , Message)
				#print(telegram)
				ser.write(telegram)
			else: # no domoticz_id present, send error message (or environment, status)
				# should check... if int(MS_subtype) == V_VAR1: # LCD message telegram (custom)
				# alternative: temperature etc. t_h_b = get_dcz_temp_hum_baro(DOMOTICZ_WU_THB) # WU, returns three values without unit
				# Message = ('{}C {}% {}hP'.format(t_h_b[0], t_h_b[1], t_h_b[2]))
				print("No information in domoticz for request")
			DB_replace_reading(MS_node, MS_child, MS_payload) # always update readings
		# else ignore and do nothing
	elif messageType == 'INTERNAL':
		messageSubType = MSinternalLabelForID(int(MS_subtype))
		# print(messageSubType)
		if messageSubType == 'I_TIME': # Time telegram
			print("time request, should send response now")
			# should be epoch local... no good way to determine yet, send with known attributes
			time_telegram = MS_make_telegram(MS_node, MS_child , MS_type, "1", MS_subtype, int(calendar.timegm(time.localtime())))
			print(time_telegram)
			ser.write(time_telegram)
		elif messageSubType == "I_ID_REQUEST":
			#-- Determine next available nodeid and sent it to the node
			telegram = MS_make_telegram(MS_node, MS_child, MS_type, "0", MSinternalID("I_ID_RESPONSE"), getAvailableNodeID())
			print("ID requested:", telegram)
			ser.write(telegram)
		# else ignore and do nothing
		elif messageSubType == "I_LOG_MESSAGE":
			pass
		elif messageSubType == "I_SKETCH_NAME":
			# Message from node: sketch name. Update all nodes in DB with sketch info
			DB_replace_nodeInfo(MS_node, MS_payload)
		# else ignore
	elif messageType == 'PRESENTATION':
		# if presentation 
		print("Presentation")
		# check if node/ sensor present
		if NodeIds[int(MS_node)]: # node is known, proceed
			DB_result = DB_get_sensor(MS_node, MS_child)
			if DB_result == []: # if not found in database, Sensor should be added)
				messageSubType = MSpresentationLabelForID(int(MS_subtype))
				# print(MS_subtype, messageSubType)
				if int(MS_child) == 255: # Node with no children, do nothing for now
					print("Node: ", MS_node, " Node with no children, generic message,do nothing for now")
				else: # create Sensor
					DCZ_Dev_Type = MS_Presentation[messageSubType]['dcz_type'] # find DCZ type
					if DCZ_Dev_Type != None:
						# create device and add
						DCZ_device = create_domoticz_dev(DCZdeviceTypeID(DCZ_Dev_Type)) # 0 if not present
						if DCZ_device <> 0:
							# add to database (should not fail)
							print("Add sensor: ", MS_node, MS_child, messageSubType, DCZ_device, DCZ_Dev_Type, " happend")
						else:
							print("Node: ", MS_node, MS_child, messageSubType, DCZ_Dev_Type, " DCZ creation failed")
						DB_add_sensor(MS_node, MS_child, messageSubType, DCZ_device, DCZ_Dev_Type) # always add to DB
					else:
						print("Node: ", MS_node, MS_child, " DCZ type not supported")
			else:
				print("Node: ", MS_node, MS_child, " already present, update information")
		else:
			print("Node: ", MS_node, " not found, no action")
	else:
		print("No action for this message")
	return

	
## Poll status of switch items in domoticz and update corresponding values 
## take appropriate action, i.e. update sensor 
## Sensor_DB[0]["Domoticz_id"] =  # i.e. locate the sensor and replace value
def DB_poll_dcz(): # 
# input global Sensor_DB, lastpoll (last update)
# output = status 
	global lastpoll # last poll (in LastUpdate format)
	#print("Database sync")
	dcz_switches = read_domoticz_switches() # read the switch values from domoticz
	for dcz_switch in dcz_switches:
		if (dcz_switch['LastUpdate'] > 0): #lastpoll): # disabled: check of updates only if change since lastpoll (need to be aware of delays.., )
			DB_result = DB_get_dczdev(dcz_switch['idx']) # check if dcz sensor is in database
			if DB_result != []: # if found in database (if not, nothing for now)
				Sensor = DB_result[0] # database can return many results, use only first one for now
				if (dcz_switch['LastUpdate'] > Sensor['LastUpdate']): # action and update if change from last time
					# replace reading in DB and update LastUpdate, reading is level (opposed to on/off)
					on_values = ["On", "Up", "Open"]
					off_values = ["Off", "Down", "Closed"]
					dcz_value =  dcz_switch['Data'] # domoticz response value
					if (True in [True for match in on_values if match in dcz_value]): # if on, 100%
						sensor_value = 100
					elif (True in [True for match in off_values if match in dcz_value]): # if off, 0%
						sensor_value = 0
					else: # otherwise use dimmer level
						sensor_value = dcz_switch['Level']
					DB_replace_reading_dcz(dcz_switch['idx'], sensor_value)
					#Debug: print("Switch present in DB, status updated", Sensor)
					telegram = MS_make_telegram(Sensor['Node'],Sensor['Child'], MSmessageTypeID('SET'), 1, MSsetreqID('V_DIMMER'), sensor_value)
					#print(telegram)
					ser.write(telegram)
	lastpoll = time.strftime("%F %T") # update the global poll variable
	return

	
#### main loop ###
# print start
# get MySensors telegram(message), non-blocking and take action
# check if updates in Domoticz switches and take action 
# 
CurrentTime =  time.strftime("%F %T") 	# for use in update
print(CurrentTime + " Start")
lastupdate = time.time() 				# timer value for per xx seconds update
lastpoll_t = lastupdate					# timer value for per xx seconds polling of domoticz
lastpoll = CurrentTime 					# sets the last domoticz database poll, checks for changes
loop_count = 0 							# just for debug
load_DB()								# Read of DB after restart.
initNodeIds()							# initialize local variable used node labels from Sensor_DB
# test
#print(create_domoticz_dev(80))
while 1 :
	# Loop: read lines from serial port, decode and send to Domoticz
	try:
		# set variable for time delay loops
		now = time.time()
		# first read messages
		MySensors_telegram = str(ser.readline()).strip()
		if (MySensors_telegram <> ""):
			print(MySensors_telegram)
			# all values are string type
			MS_node, MS_child, MS_type, MS_ack, MS_subtype, MS_payload = MySensors_telegram.split(";")
			# ignore ack messages?
			if int(MS_ack) == 0:
				process_MS_message(	MS_node, MS_child, MS_type, MS_subtype, MS_payload) # proces the message and take action
		# delay sync DB with domoticz, test
		if (now - lastpoll_t > 1): # once every 1 second
			DB_poll_dcz()
			## test code ###
			lastpoll_t = now
		
		# delay loop, commit DB & for debug and testing
		if (now - lastupdate > 60): # once every sixty seconds
			save_DB()
			# create messages
			lastupdate = now
			loop_count += 1
			
		# sleep a little to avoid CPU max.load
		time.sleep(0.3) 
		
	except (ValueError, TypeError), e: #,  KeyError
		print("Wrong/No input from MySensors gateway", e)
