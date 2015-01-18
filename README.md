# MySensors
MySensors developments

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
