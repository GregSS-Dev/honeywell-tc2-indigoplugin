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

# Original source code developed by Craig J. Ward and used with permission:
# https://github.com/wardcraigj/total-connect-client

import zeep
import logging
import datetime
import requests

ARM_TYPE_AWAY = 0
ARM_TYPE_STAY = 1
ARM_TYPE_STAY_INSTANT = 2
ARM_TYPE_AWAY_INSTANT = 3
ARM_TYPE_STAY_NIGHT = 4

ERROR = -1
DISARMED = 10200
DISARMED_BYPASS = 10211
ARMED_AWAY = 10201
ARMED_AWAY_BYPASS = 10202
ARMED_AWAY_INSTANT = 10205
ARMED_AWAY_INSTANT_BYPASS = 10206
ARMED_STAY = 10203
ARMED_STAY_BYPASS = 10204
ARMED_STAY_INSTANT = 10209
ARMED_STAY_INSTANT_BYPASS = 10210
ARMED_STAY_NIGHT = 10218
ARMING = 10307
DISARMING = 10308

class TotalConnectClient:

	def __init__(self, plugin, username, password):

		try:
			self.soapClient = zeep.Client('https://rs.alarmnet.com/TC21api/tc2.asmx?WSDL')
		except requests.exceptions.ReadTimeout:
			self.plugin.logger.error('A timeout error occurred when communicating with Total Connect. The list of available commands could not be loaded. You should restart the plug-in.')
		except:
			self.plugin.logger.error('An unknown error occurred when communicating with Total Connect. The list of available commands could not be loaded. You should restart the plug-in.')

		self.plugin = plugin

		self.applicationId = "14588"
		self.applicationVersion = "1.0.34"
		self.username = username
		self.password = password
		self.token = False
		self.tokenRefresh = datetime.datetime.min

		self.locations = []

		self.authenticate()

	def authenticate(self):
		"""Login to the system."""
		try:
			response = self.soapClient.service.AuthenticateUserLogin(self.username, self.password, self.applicationId, self.applicationVersion)
			if response.ResultData == 'Success':
				self.token = response.SessionID
				self.recordSuccessfulCommand()
				self.plugin.logger.info('Logged in to Total Connect as user: %s', self.username)
			else:
				self.plugin.logger.error('Authentication error when connecting to Total Connect: %s', response.ResultData)
		except requests.exceptions.ReadTimeout:
			self.plugin.logger.error('A timeout error occurred when communicating with Total Connect. Authentication failed.')
		except:
			self.plugin.logger.error('An unknown error occurred when communicating with Total Connect. Authentication failed.')

	def populate_details(self, isRetry=False):
		"""Populates system details."""

		self.prepareConnection()
		try:
			response = self.soapClient.service.GetSessionDetails(self.token, self.applicationId, self.applicationVersion)

			if (isRetry == False) and (response.ResultData != 'Success'):
				self.reestablishSession()
				self.populate_details(isRetry=True)
			else:
				if response.ResultData == 'Success':
					self.recordSuccessfulCommand()

					self.plugin.logger.debug('Fetched session details from Total Connect.')

					self.locations = zeep.helpers.serialize_object(response.Locations)['LocationInfoBasic']

					self.plugin.logger.debug('Fetched configuration details from Total Connect.')
				
					return True
				else:
					self.plugin.logger.error('Failed to fetch configuration details from Total Connect: %s', response.ResultData)
					return False

		except requests.exceptions.ReadTimeout:
			self.plugin.logger.error('A timeout error occurred when communicating with Total Connect. Configuration details could not be loaded. You may need to restart the plug-in.')
		except:
			self.plugin.logger.error('An unknown error occurred when communicating with Total Connect. Configuration details could not be loaded. You may need to restart the plug-in.')
				
	def executeRunLoopTasks(self):
		# Send keepAlive command at intervals to ensure connection stays active
		timeSinceRefresh = datetime.datetime.now() - self.tokenRefresh
		
    	#return false if time since refresh is over 4 minutes (likely timeout)       
		if timeSinceRefresh.total_seconds() > 3 * 60:
			self.keepAlive()
		

	def arm_away(self, location_name=False):
		"""Arm the system (Away)."""

		self.arm(ARM_TYPE_AWAY, location_name)

	def arm_stay(self, location_name=False):
		"""Arm the system (Stay)."""

		self.arm(ARM_TYPE_STAY, location_name)

	def arm_stay_instant(self, location_name=False):
		"""Arm the system (Stay - Instant)."""

		self.arm(ARM_TYPE_STAY_INSTANT, location_name)

	def arm_away_instant(self, location_name=False):
		"""Arm the system (Away - Instant)."""

		self.arm(ARM_TYPE_AWAY_INSTANT, location_name)

	def arm_stay_night(self, location_name=False):
		"""Arm the system (Stay - Night)."""

		self.arm(ARM_TYPE_STAY_NIGHT, location_name)

	def arm(self, arm_type, location_name=False, isRetry=False):
		"""Arm the system."""

		location = self.get_location_by_location_name(location_name)
		deviceId = self.get_security_panel_device_id(location)

		self.prepareConnection()
		try:
			response = self.soapClient.service.ArmSecuritySystem(self.token, location['LocationID'], deviceId, arm_type, '-1')

			if (isRetry == False) and (response.ResultData != 'Success'):
				self.reestablishSession()
				self.arm(arm_type, location_name, True)
			else:
				if response.ResultData == 'Success':
					self.recordSuccessfulCommand()
					self.plugin.logger.debug('Armed security panel (arm type=%d) at %s location via Total Connect.', arm_type, location_name)

				else:
					self.plugin.logger.warn('Failed to arm security panel (arm type=%d) at %s location via Total Connect: %s', arm_type, location_name, response.ResultData)

		except requests.exceptions.ReadTimeout:
			self.plugin.logger.warn('A timeout error occurred when communicating with Total Connect. The security panel may not be armed.')
		except:
			self.plugin.logger.warn('An unknown error occurred when communicating with Total Connect. The security panel may not be armed.')


	def get_security_panel_device_id(self, location):
		"""Find the device id of the security panel."""
		deviceId = False
		for device in location['DeviceList']['DeviceInfoBasic']:
			if (device['DeviceName'] == 'Security Panel' or device['DeviceName'] == 'Security System'):
				deviceId = device['DeviceID']

		if deviceId is False:
			raise Exception('No security panel found')

		return deviceId

	def get_location_by_location_name(self, location_name=False):
		"""Get the location object for a given name (or the default location if none is provided)."""

		location = False

		for loc in self.locations:
			if location_name is False and location is False:
				location = loc
			elif loc['LocationName'] == location_name:
				location = loc

		if location is False:
			raise Exception('Could not select location. Try using default location.')

		return location

	def get_armed_status(self, location_name=False, isRetry=False):
		"""Get the status of the panel."""
		location = self.get_location_by_location_name(location_name)

		self.prepareConnection()
		try:
			response = self.soapClient.service.GetPanelMetaDataAndFullStatus(self.token, location['LocationID'], 0, 0, 1)

			if (isRetry == False) and (response.ResultData != 'Success'):
				self.reestablishSession()
				self.get_armed_status(location_name, True)
			else:
				if response.ResultData == 'Success':
					self.recordSuccessfulCommand()
					status = zeep.helpers.serialize_object(response)
					alarm_code = status['PanelMetadataAndStatus']['Partitions']['PartitionInfo'][0]['ArmingState']
					self.plugin.logger.debug('Retrieved armed status of %s location: %d', location_name, alarm_code)

				else:
					self.plugin.logger.warn('Could not obtain armed status of location %s.', location_name)
					alarm_code = ERROR

			return alarm_code
		except requests.exceptions.ReadTimeout:
			self.plugin.logger.warn('A timeout error occurred when communicating with Total Connect. The current status could not be read.')
		except:
			self.plugin.logger.warn('An unknown error occurred when communicating with Total Connect. The current status could not be read.')

		return ERROR

	def is_armed(self, location_name=False, alarm_code=False):
		# Get the current armed_status, if necessary
		if (alarm_code != False):
			alarm_code = self.get_armed_status(location_name)

		# Return True or False if the system is armed in any way

		if alarm_code == 10201:
			return True
		elif alarm_code == 10202:
			return True
		elif alarm_code == 10205:
			return True
		elif alarm_code == 10206:
			return True
		elif alarm_code == 10203:
			return True
		elif alarm_code == 10204:
			return True
		elif alarm_code == 10209:
			return True
		elif alarm_code == 10210:
			return True
		elif alarm_code == 10218:
			return True
		else:
			return False

	def is_arming(self, location_name=False, alarm_code=False):
		"""Return true or false is the system is in the process of arming."""

		# Get the current armed_status, if necessary
		if (alarm_code != False):
			alarm_code = self.get_armed_status(location_name)

		if alarm_code == 10307:
			return True
		else:
			return False

	def is_disarming(self, location_name=False, alarm_code=False):
		"""Return true or false is the system is in the process of disarming."""

		# Get the current armed_status, if necessary
		if (alarm_code != False):
			alarm_code = self.get_armed_status(location_name)

		if alarm_code == 10308:
			return True
		else:
			return False

	def is_pending(self, location_name=False, alarm_code=False):
		"""Return true or false is the system is pending an action."""

		# Get the current armed_status, if necessary
		if (alarm_code != False):
			alarm_code = self.get_armed_status(location_name)

		if alarm_code == 10307 or alarm_code == 10308:
			return True
		else:
			return False

	def disarm(self, location_name=False, isRetry=False):
		"""Disarm the system."""

		location = self.get_location_by_location_name(location_name)
		deviceId = self.get_security_panel_device_id(location)

		self.plugin.logger.debug('Device ID %s found for location %s.', deviceId, location_name)

		self.prepareConnection()
		try:
			response = self.soapClient.service.DisarmSecuritySystem(self.token, location['LocationID'], deviceId, '-1')
		
			if (isRetry == False) and (response.ResultData != 'Success'):
				self.reestablishSession()
				self.disarm(location_name, True)
			else:
				if response.ResultData == 'Success':
					self.recordSuccessfulCommand()
					self.plugin.logger.debug('Disarmed security panel at %s location via Total Connect.', location_name)

				else:
					self.plugin.logger.warn('Failed to disarm security panel at %s location via Total Connect: %s', location_name, response.ResultData)
		except requests.exceptions.ReadTimeout:
			self.plugin.logger.warn('A timeout error occurred when communicating with Total Connect. The security panel may not be disarmed.')
		except:
			self.plugin.logger.warn('An unknown error occurred when communicating with Total Connect. The security panel may not be disarmed.')

	def logout(self):
		"""Request that the given sessionID be logged out and/or terminated."""
		if self.token != False:
			try:
				response = self.soapClient.service.Logout(self.token)
				if response.ResultData == 'Success':
					self.token = False	
					self.tokenRefresh = datetime.datetime.min
					self.plugin.logger.info("Logged out of Total Connect.")			
				else:
					self.plugin.logger.warn('Error logging out of Total Connect: %s.', response.ResultData)
			except requests.exceptions.ReadTimeout:
				self.plugin.logger.warn('A timeout error occurred when communicating with Total Connect. Error when logging out.')
			except:
				self.plugin.logger.warn('An unknown error occurred when communicating with Total Connect. Error when logging out.')
			
	def tokenIsValid(self):
		if self.token == False:
			return False
			
		timeSinceRefresh = datetime.datetime.now() - self.tokenRefresh
		
    	#return false if time since refresh is over 4 minutes (likely timeout)       
		if timeSinceRefresh.total_seconds() > 4 * 60:
			return False
			
		return True		
				
	def get_locations(self):
		return self.locations
		
	def prepareConnection(self):
		if not self.tokenIsValid():
			self.authenticate()
			
	def recordSuccessfulCommand(self):
		self.tokenRefresh = datetime.datetime.now()
			
	def keepAlive(self):
		try:
			response = self.soapClient.service.KeepAlive(self.token)
			if response.ResultData == 'Success':
				self.plugin.logger.debug('Keep alive used to maintain connection to Total Connect.')
				self.recordSuccessfulCommand()
		except requests.exceptions.ReadTimeout:
			self.plugin.logger.warn('A timeout error occurred when communicating with Total Connect. The connection could not be kept open.')
		except:
			self.plugin.logger.warn('An unknown error occurred when communicating with Total Connect. The connection could not be kept open.')

			
	def reestablishSession(self):
		self.plugin.logger.info("Last command failed due to invalid Total Connect session ID. Logging in again.")
		self.authenticate()
			
	def armedStatusDetailString(self, armed_status=False):
		if armed_status == DISARMED:
			return 'Disarmed'
		elif armed_status == DISARMED_BYPASS:
			return 'Disarmed, Bypass'
		elif armed_status == ARMED_AWAY:
			return 'Armed Away'
		elif armed_status == ARMED_AWAY_BYPASS:
			return 'Armed Away, Bypass'
		elif armed_status == ARMED_AWAY_INSTANT:
			return 'Armed Away, Instant'					
		elif armed_status == ARMED_AWAY_INSTANT_BYPASS:
			return 'Armed Away, Instant Bypass'
		elif armed_status == ARMED_STAY:
			return 'Armed Stay'					
		elif armed_status == ARMED_STAY_BYPASS:
			return 'Armed Stay, Bypass'						
		elif armed_status == ARMED_STAY_INSTANT:
			return 'Armed Stay, Instant'						
		elif armed_status == ARMED_STAY_INSTANT_BYPASS:
			return 'Armed Stay, Instant Bypass'					
		elif armed_status == ARMED_STAY_NIGHT:
			return 'Armed Night Stay'						
		elif armed_status == ARMING:
			return 'Arming'					
		elif armed_status == DISARMING:
			return 'Disarming'
		else:
			return None			
			
	def armedStatusDetailStringDisplayValue(self, armed_status=False):
		if armed_status == DISARMED:
			return 'Disarmed'
		elif armed_status == DISARMED_BYPASS:
			return 'Disarmed, Bypass'
		elif armed_status == ARMED_AWAY:
			return 'Armed Away'
		elif armed_status == ARMED_AWAY_BYPASS:
			return 'Armed Away, Bypass'
		elif armed_status == ARMED_AWAY_INSTANT:
			return 'Armed Away, Instant'					
		elif armed_status == ARMED_AWAY_INSTANT_BYPASS:
			return 'Armed Away, Instant Bypass'
		elif armed_status == ARMED_STAY:
			return 'Armed Stay'					
		elif armed_status == ARMED_STAY_BYPASS:
			return 'Armed Stay, Bypass'						
		elif armed_status == ARMED_STAY_INSTANT:
			return 'Armed Stay, Instant'						
		elif armed_status == ARMED_STAY_INSTANT_BYPASS:
			return 'Armed Stay, Instant Bypass'					
		elif armed_status == ARMED_STAY_NIGHT:
			return 'Armed Night Stay'						
		elif armed_status == ARMING:
			return 'Arming'					
		elif armed_status == DISARMING:
			return 'Disarming'
		else:
			return None			
			
	def armedStatusTypeString(self, armed_status=False):
		if armed_status == DISARMED:
			return 'Disarmed'
		elif armed_status == DISARMED_BYPASS:
			return 'Disarmed'
		elif armed_status == ARMED_AWAY:
			return 'Armed-Away'
		elif armed_status == ARMED_AWAY_BYPASS:
			return 'Armed-Away'
		elif armed_status == ARMED_AWAY_INSTANT:
			return 'Armed-Away'					
		elif armed_status == ARMED_AWAY_INSTANT_BYPASS:
			return 'Armed-Away'
		elif armed_status == ARMED_STAY:
			return 'Armed-Stay'					
		elif armed_status == ARMED_STAY_BYPASS:
			return 'Armed-Stay'						
		elif armed_status == ARMED_STAY_INSTANT:
			return 'Armed-Stay'						
		elif armed_status == ARMED_STAY_INSTANT_BYPASS:
			return 'Armed-Stay'					
		elif armed_status == ARMED_STAY_NIGHT:
			return 'Armed-Night'						
		elif armed_status == ARMING:
			return 'Arming'					
		elif armed_status == DISARMING:
			return 'Disarming'
		else:
			return None			
			
	def armedStatusTypeStringDisplayValue(self, armed_status=False):
		if armed_status == DISARMED:
			return 'Disarmed'
		elif armed_status == DISARMED_BYPASS:
			return 'Disarmed'
		elif armed_status == ARMED_AWAY:
			return 'Armed-Away'
		elif armed_status == ARMED_AWAY_BYPASS:
			return 'Armed-Away'
		elif armed_status == ARMED_AWAY_INSTANT:
			return 'Armed-Away'					
		elif armed_status == ARMED_AWAY_INSTANT_BYPASS:
			return 'Armed-Away'
		elif armed_status == ARMED_STAY:
			return 'Armed-Stay'					
		elif armed_status == ARMED_STAY_BYPASS:
			return 'Armed-Stay'						
		elif armed_status == ARMED_STAY_INSTANT:
			return 'Armed-Stay'						
		elif armed_status == ARMED_STAY_INSTANT_BYPASS:
			return 'Armed-Stay'					
		elif armed_status == ARMED_STAY_NIGHT:
			return 'Armed-Night'						
		elif armed_status == ARMING:
			return 'Arming'					
		elif armed_status == DISARMING:
			return 'Disarming'
		else:
			return None			
			
	def isBypass(self, armed_status=False):
		if armed_status == DISARMED:
			return False
		elif armed_status == DISARMED_BYPASS:
			return True
		elif armed_status == ARMED_AWAY:
			return False
		elif armed_status == ARMED_AWAY_BYPASS:
			return True
		elif armed_status == ARMED_AWAY_INSTANT:
			return False				
		elif armed_status == ARMED_AWAY_INSTANT_BYPASS:
			return True
		elif armed_status == ARMED_STAY:
			return False				
		elif armed_status == ARMED_STAY_BYPASS:
			return True					
		elif armed_status == ARMED_STAY_INSTANT:
			return False					
		elif armed_status == ARMED_STAY_INSTANT_BYPASS:
			return True				
		elif armed_status == ARMED_STAY_NIGHT:
			return False					
		elif armed_status == ARMING:
			return False					
		elif armed_status == DISARMING:
			return False
		else:
			return None														
			
	def isArmed(self, armed_status=False):
		if armed_status == DISARMED:
			return False
		elif armed_status == DISARMED_BYPASS:
			return False
		elif armed_status == ARMED_AWAY:
			return True
		elif armed_status == ARMED_AWAY_BYPASS:
			return True
		elif armed_status == ARMED_AWAY_INSTANT:
			return True					
		elif armed_status == ARMED_AWAY_INSTANT_BYPASS:
			return True
		elif armed_status == ARMED_STAY:
			return True				
		elif armed_status == ARMED_STAY_BYPASS:
			return True						
		elif armed_status == ARMED_STAY_INSTANT:
			return True						
		elif armed_status == ARMED_STAY_INSTANT_BYPASS:
			return True					
		elif armed_status == ARMED_STAY_NIGHT:
			return True					
		elif armed_status == ARMING:
			return False					
		elif armed_status == DISARMING:
			return True
		else:
			return None														