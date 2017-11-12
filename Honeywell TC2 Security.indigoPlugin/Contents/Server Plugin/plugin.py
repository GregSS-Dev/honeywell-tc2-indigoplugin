# Copyright 2017 Greg Scherrer
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import datetime

from Honeywell import TotalConnectClient

ERROR = -1


class Plugin(indigo.PluginBase):

	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		
		self.tcUsername = pluginPrefs.get("username", '')
		self.tcPassword = pluginPrefs.get("password", '')
		
		self.refreshInterval = int(pluginPrefs.get("refreshInterval", 0))
		
		self.Honeywell = None
				
	def __del__(self):
		indigo.PluginBase.__del__(self)
		
	def startup(self):
		self.logger.debug(u"Startup called")
		self.Honeywell = TotalConnectClient(self, self.tcUsername, self.tcPassword)
		fetchedDetails = self.Honeywell.populate_details()
		
		# Retrieve Locations
		
		locationList = self.Honeywell.get_locations()
		self.logger.debug("Total Connect returned the following locations list: %s", str(locationList))

		locationNames = []
		for location in locationList:
			name = location.values()[location.keys().index(u'LocationName')]
			locationNames.append(name)
		self.locationNames = locationNames
				
	def shutdown(self):
	 # do any cleanup necessary before exiting
		self.logger.debug('Honeywell Total Connect plugin shutting down.')
		self.Honeywell.logout()	 	
	 
	def runConcurrentThread(self):
		try:
			while True:
				self.logger.debug('Executing main plug-in thread.')

				self.Honeywell.executeRunLoopTasks()

				timeSinceRefresh = datetime.timedelta.max

				if self.refreshInterval > 0:
					for keypad in indigo.devices.iter("self.alarmKeypad"):				
						lastStatusUpdate = datetime.datetime.strptime(keypad.states['lastStatusUpdate'], '%Y-%m-%d %H:%M:%S')
						timeSinceRefresh = datetime.datetime.now() - lastStatusUpdate
		
						#return false if time since refresh is over 4 minutes (likely timeout)       
						if (timeSinceRefresh.total_seconds() > self.refreshInterval * 60) or (keypad.states['state'] == 'Arming') or (keypad.states['state'] == 'Disarming'):
							self.logger.debug('Updating status of %s.', keypad.name)
							self.updateDeviceStatus(keypad)
								
				
				self.sleep(30) # in seconds
		except self.StopThread:
			# do any cleanup here
			self.logger.debug('Run loop is ending.')
			pass	
			
	########################################################
	# Device specific methods
	########################################################
	def deviceStartComm(self, dev):
		dev.updateStateOnServer('lastStatusUpdate', value='2000-01-01 00:00:00', triggerEvents=False)

		# Update status, but don't fire triggers on initial status setting
		self.updateDeviceStatus(dev, triggerEvents=False)
			
	def updateDeviceStatus(self, dev, triggerEvents=True):
		armedStatus = self.Honeywell.get_armed_status(dev.pluginProps['locationName'])
		if armedStatus != ERROR:
			armedStatusDetailString = self.Honeywell.armedStatusDetailString(armedStatus)
			armedStatusTypeString = self.Honeywell.armedStatusTypeString(armedStatus)
			isArmed = self.Honeywell.isArmed(armedStatus)
			isBypass = self.Honeywell.isBypass(armedStatus)
			armedStatusDetailStringDisplayValue = self.Honeywell.armedStatusDetailStringDisplayValue(armedStatus)
			armedStatusTypeStringDisplayValue = self.Honeywell.armedStatusTypeStringDisplayValue(armedStatus)

			if (triggerEvents == False) or (armedStatusTypeString != dev.states['state']):
				self.logger.info('%s is %s; status last updated at %s', dev.name, armedStatusDetailStringDisplayValue, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
			else:
				self.logger.debug('%s is %s; status last updated at %s', dev.name, armedStatusDetailStringDisplayValue, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
			dev.updateStateOnServer('state', value=armedStatusTypeString, uiValue=armedStatusTypeStringDisplayValue, triggerEvents=triggerEvents)
			dev.updateStateOnServer('isBypass', value=isBypass, triggerEvents=triggerEvents)
			dev.updateStateOnServer('isArmed', value=isArmed, triggerEvents=triggerEvents)
			dev.updateStateOnServer('lastStatusUpdate', value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), triggerEvents=False)
			if isArmed:
				dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
			else:
				dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
			
			return True
		else:
			return False	
	
	########################################################
	# Action object callback methods
	########################################################
	def disarm(self, action, dev):	
		keypadDevice = dev
		self.logger.info(u"Security panel %s disarming.", keypadDevice.name)
		locationName = keypadDevice.pluginProps['locationName']
		self.Honeywell.disarm(locationName)
		self.updateDeviceStatus(dev)
		
	def armStay(self, action, dev):		
		keypadDevice = dev
		self.logger.info(u"Security panel %s stay arming.", keypadDevice.name)
		locationName = keypadDevice.pluginProps['locationName']
		self.Honeywell.arm_stay(locationName)
		self.updateDeviceStatus(dev)

	def armAway(self, action, dev):		
		keypadDevice = dev
		self.logger.info(u"Security panel %s away arming.", keypadDevice.name)
		locationName = keypadDevice.pluginProps['locationName']
		self.Honeywell.arm_away(locationName)
		self.updateDeviceStatus(dev)

	def armStayNight(self, action, dev):		
		keypadDevice = dev
		self.logger.info(u"Security panel %s night arming.", keypadDevice.name)
		locationName = keypadDevice.pluginProps['locationName']
		self.Honeywell.arm_stay_night(locationName)
		self.updateDeviceStatus(dev)
		
	def updateStatus(self, action, dev):	
		keypadDevice = dev
		self.updateDeviceStatus(keypadDevice)

	########################################################
	# Functions for configuration dialogs
	########################################################

	def getLocations(self, filter="", valuesDict=None, typeId="", targetId=0):
		valuesList = []
		for name in self.locationNames:
			valuesList.append((name, name))
		
		return valuesList
		
	def validateDeviceConfigUi(self, valuesDict, typeId, devId):
		if typeId == 'alarmKeypad':
			if not valuesDict['locationName']:
				errorDict = indigo.Dict()
				errorDict["locationName"] = "You must associate this keypad with a location"
				errorDict["showAlertText"] = "You must pick a location. If no locations are listed, log in to Total Connect to review your configuration."
				return (False, valuesDict, errorDict)
		
		return True
		
	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		if userCancelled == False:
			if (valuesDict['username'] != self.tcUsername) or (valuesDict['password'] != self.tcPassword):
				self.Honeywell.logout()
				
			self.tcUsername = valuesDict['username']
			self.tcPassword = valuesDict['password']
		
			self.refreshInterval = int(valuesDict['refreshInterval'])
		
	