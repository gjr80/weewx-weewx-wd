##
## This program is free software; you can redistribute it and/or modify it under
## the terms of the GNU General Public License as published by the Free Software
## Foundation; either version 2 of the License, or (at your option) any later
## version.
##
## This program is distributed in the hope that it will be useful, but WITHOUT 
## ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
## FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
## details.
##
## Version: 0.2.0                         Date: ?? January 2015 HH:MM GMT +10
##
## Revision History
##  ?? January 2015     v0.2.0      -Changed from wdWU to more general wdSupp 
##                                   for supplementary
##                                  -moved to separate db
##                                  -included theoretical max solar radiation 
##                                   (Rs) in table
##                                  -now keep past 8 days of data so we can 
##                                   plot Rs on day and week radiation plots
##  ?? January 2015     v0.1.0      -Initial implementation
##

import syslog
import threading
import urllib2
import json
import math
import time
import ephem
import datetime

import weewx
import weewx.manager
import weeutil.Sun 
from weewx.units import convert, obs_group_dict
import weewx.almanac

WDSUPP3_VERSION = '0.2'

def logmsg(level, msg):
    syslog.syslog(level, 'wdSupp3: %s' % msg)

def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)

def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)

def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)
    
def toint(label, value_tbc, default_value):
    """ Convert value_tbc to an integer whilst handling None.
    
        If value_tbc cannot be converted to an integer default_value is returned.
        
        Input:
            label: String with the name of the parameter being set
            value_tbc: The value to be converted to an integer
            default_value: The value to be returned if value cannot be 
                           converted to an integer
        
    """
    if isinstance(value_tbc, str) and value_tbc.lower() == 'none':
        value_tbc = None
    if value_tbc is not None:
        try:
            value_tbc = int(value_tbc)
        except Exception, e:
            logerr("bad value '%s' for %s" % (value_tbc, label))
            value_tbc = default_value
    return value_tbc

def get_default_binding_dict():
    """ Define a default binding dictionary.
    """
    
    return {'database':   'weewxwd_sqlite',
            'manager':    'weewx.manager.Manager',
            'table_name': 'supp',
            'schema':     'user.wdSupp3.schema'}
    
# Define schema for conditions table
schema = [('dateTime',              'INTEGER NOT NULL UNIQUE PRIMARY KEY'),
          ('usUnits',               'INTEGER NOT NULL'),
          ('forecastIcon',          'INTEGER'),
          ('forecastText',          'VARCHAR(256)'),
          ('forecastTextMetric',    'VARCHAR(256)'),
          ('currentIcon',           'INTEGER'),
          ('currentText',           'VARCHAR(256)'),
          ('tempRecordHigh',        'REAL'),
          ('tempNormalHigh',        'REAL'),
          ('tempRecordHighYear',    'INTEGER'),
          ('tempRecordLow',         'REAL'),
          ('tempNormalLow',         'REAL'),
          ('tempRecordLowYear',     'INTEGER'),
          ('vantageForecastIcon',   'INTEGER'),
          ('vantageForecastRule',   'VARCHAR(256)'),
          ('stormRain',             'REAL'),
          ('stormStart',            'INTEGER'),
          ('theoreticalRadiation',  'REAL')]

# Define a dictionary to look up WU icon names and 
# return corresponding Saratoga icon code
icon_dict = {
    'clear'             : 0,
    'cloudy'            : 18,
    'flurries'          : 25,
    'fog'               : 11,
    'hazy'              : 7,
    'mostlycloudy'      : 18,
    'mostlysunny'       : 9,
    'partlycloudy'      : 19,
    'partlysunny'       : 9,
    'sleet'             : 23,
    'rain'              : 20,
    'snow'              : 25,
    'sunny'             : 28,
    'tstorms'           : 29,
    'nt_clear'          : 1,
    'nt_cloudy'         : 13,
    'nt_flurries'       : 16,
    'nt_fog'            : 11,
    'nt_hazy'           : 13,
    'nt_mostlycloudy'   : 13,
    'nt_mostlysunny'    : 1,
    'nt_partlycloudy'   : 4,
    'nt_partlysunny'    : 1,
    'nt_sleet'          : 12,
    'nt_rain'           : 14,
    'nt_snow'           : 16,
    'nt_tstorms'        : 17,
    'chancerain'        : 20,
    'chancesleet'       : 23,
    'chancesnow'        : 25,
    'chancetstorms'     : 29
    }

# Define a dictionary to look up Davis forecast rule
# and return forecast text
davis_fr_dict= {
        0   : 'Mostly clear and cooler.',
        1   : 'Mostly clear with little temperature change.',
        2   : 'Mostly clear for 12 hours with little temperature change.',
        3   : 'Mostly clear for 12 to 24 hours and cooler.',
        4   : 'Mostly clear with little temperature change.',
        5   : 'Partly cloudy and cooler.',
        6   : 'Partly cloudy with little temperature change.',
        7   : 'Partly cloudy with little temperature change.',
        8   : 'Mostly clear and warmer.',
        9   : 'Partly cloudy with little temperature change.',
        10  : 'Partly cloudy with little temperature change.',
        11  : 'Mostly clear with little temperature change.',
        12  : 'Increasing clouds and warmer. Precipitation possible within 24 to 48 hours.',
        13  : 'Partly cloudy with little temperature change.',
        14  : 'Mostly clear with little temperature change.',
        15  : 'Increasing clouds with little temperature change. Precipitation possible within 24 hours.',
        16  : 'Mostly clear with little temperature change.',
        17  : 'Partly cloudy with little temperature change.',
        18  : 'Mostly clear with little temperature change.',
        19  : 'Increasing clouds with little temperature change. Precipitation possible within 12 hours.',
        20  : 'Mostly clear with little temperature change.',
        21  : 'Partly cloudy with little temperature change.',
        22  : 'Mostly clear with little temperature change.',
        23  : 'Increasing clouds and warmer. Precipitation possible within 24 hours.',
        24  : 'Mostly clear and warmer. Increasing winds.',
        25  : 'Partly cloudy with little temperature change.',
        26  : 'Mostly clear with little temperature change.',
        27  : 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
        28  : 'Mostly clear and warmer. Increasing winds.',
        29  : 'Increasing clouds and warmer.',
        30  : 'Partly cloudy with little temperature change.',
        31  : 'Mostly clear with little temperature change.',
        32  : 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
        33  : 'Mostly clear and warmer. Increasing winds.',
        34  : 'Increasing clouds and warmer.',
        35  : 'Partly cloudy with little temperature change.',
        36  : 'Mostly clear with little temperature change.',
        37  : 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
        38  : 'Partly cloudy with little temperature change.',
        39  : 'Mostly clear with little temperature change.',
        40  : 'Mostly clear and warmer. Precipitation possible within 48 hours.',
        41  : 'Mostly clear and warmer.',
        42  : 'Partly cloudy with little temperature change.',
        43  : 'Mostly clear with little temperature change.',
        44  : 'Increasing clouds with little temperature change. Precipitation possible within 24 to 48 hours.',
        45  : 'Increasing clouds with little temperature change.',
        46  : 'Partly cloudy with little temperature change.',
        47  : 'Mostly clear with little temperature change.',
        48  : 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours.',
        49  : 'Partly cloudy with little temperature change.',
        50  : 'Mostly clear with little temperature change.',
        51  : 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
        52  : 'Partly cloudy with little temperature change.',
        53  : 'Mostly clear with little temperature change.',
        54  : 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
        55  : 'Partly cloudy with little temperature change.',
        56  : 'Mostly clear with little temperature change.',
        57  : 'Increasing clouds and warmer. Precipitation possible within 6 to 12 hours.',
        58  : 'Partly cloudy with little temperature change.',
        59  : 'Mostly clear with little temperature change.',
        60  : 'Increasing clouds and warmer. Precipitation possible within 6 to 12 hours. Windy.',
        61  : 'Partly cloudy with little temperature change.',
        62  : 'Mostly clear with little temperature change.',
        63  : 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
        64  : 'Partly cloudy with little temperature change.',
        65  : 'Mostly clear with little temperature change.',
        66  : 'Increasing clouds and warmer. Precipitation possible within 12 hours.',
        67  : 'Partly cloudy with little temperature change.',
        68  : 'Mostly clear with little temperature change.',
        69  : 'Increasing clouds and warmer. Precipitation likley.',
        70  : 'Clearing and cooler. Precipitation ending within 6 hours.',
        71  : 'Partly cloudy with little temperature change.',
        72  : 'Clearing and cooler. Precipitation ending within 6 hours.',
        73  : 'Mostly clear with little temperature change.',
        74  : 'Clearing and cooler. Precipitation ending within 6 hours.',
        75  : 'Partly cloudy and cooler.',
        76  : 'Partly cloudy with little temperature change.',
        77  : 'Mostly clear and cooler.',
        78  : 'Clearing and cooler. Precipitation ending within 6 hours.',
        79  : 'Mostly clear with little temperature change.',
        80  : 'Clearing and cooler. Precipitation ending within 6 hours.',
        81  : 'Mostly clear and cooler.',
        82  : 'Partly cloudy with little temperature change.',
        83  : 'Mostly clear with little temperature change.',
        84  : 'Increasing clouds with little temperature change. Precipitation possible within 24 hours.',
        85  : 'Mostly cloudy and cooler. Precipitation continuing.',
        86  : 'Partly cloudy with little temperature change.',
        87  : 'Mostly clear with little temperature change.',
        88  : 'Mostly cloudy and cooler. Precipitation likely.',
        89  : 'Mostly cloudy with little temperature change. Precipitation continuing.',
        90  : 'Mostly cloudy with little temperature change. Precipitation likely.',
        91  : 'Partly cloudy with little temperature change.',
        92  : 'Mostly clear with little temperature change.',
        93  : 'Increasing clouds and cooler. Precipitation possible and windy within 6 hours.',
        94  : 'Increasing clouds with little temperature change. Precipitation possible and windy within 6 hours.',
        95  : 'Mostly cloudy and cooler. Precipitation continuing. Increasing winds.',
        96  : 'Partly cloudy with little temperature change.',
        97  : 'Mostly clear with little temperature change.',
        98  : 'Mostly cloudy and cooler. Precipitation likely. Increasing winds.',
        99  : 'Mostly cloudy with little temperature change. Precipitation continuing. Increasing winds.',
        100 : 'Mostly cloudy with little temperature change. Precipitation likely. Increasing winds.',
        101 : 'Partly cloudy with little temperature change.',
        102 : 'Mostly clear with little temperature change.',
        103 : 'Increasing clouds and cooler. Precipitation possible within 12 to 24 hours possible wind shift to the W, NW, or N.',
        104 : 'Increasing clouds with little temperature change. Precipitation possible within 12 to 24 hours possible wind shift to the W, NW, or N.',
        105 : 'Partly cloudy with little temperature change.',
        106 : 'Mostly clear with little temperature change.',
        107 : 'Increasing clouds and cooler. Precipitation possible within 6 hours possible wind shift to the W, NW, or N.',
        108 : 'Increasing clouds with little temperature change. Precipitation possible within 6 hours possible wind shift to the W, NW, or N.',
        109 : 'Mostly cloudy and cooler. Precipitation ending within 12 hours possible wind shift to the W, NW, or N.',
        110 : 'Mostly cloudy and cooler. Possible wind shift to the W, NW, or N.',
        111 : 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours possible wind shift to the W, NW, or N.',
        112 : 'Mostly cloudy with little temperature change. Possible wind shift to the W, NW, or N.',
        113 : 'Mostly cloudy and cooler. Precipitation ending within 12 hours possible wind shift to the W, NW, or N.',
        114 : 'Partly cloudy with little temperature change.',
        115 : 'Mostly clear with little temperature change.',
        116 : 'Mostly cloudy and cooler. Precipitation possible within 24 hours possible wind shift to the W, NW, or N.',
        117 : 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours possible wind shift to the W, NW, or N.',
        118 : 'Mostly cloudy with little temperature change. Precipitation possible within 24 hours possible wind shift to the W, NW, or N.',
        119 : 'Clearing, cooler and windy. Precipitation ending within 6 hours.',
        120 : 'Clearing, cooler and windy.',
        121 : 'Mostly cloudy and cooler. Precipitation ending within 6 hours. Windy with possible wind shift to the W, NW, or N.',
        122 : 'Mostly cloudy and cooler. Windy with possible wind shift o the W, NW, or N.',
        123 : 'Clearing, cooler and windy.',
        124 : 'Partly cloudy with little temperature change.',
        125 : 'Mostly clear with little temperature change.',
        126 : 'Mostly cloudy with little temperature change. Precipitation possible within 12 hours. Windy.',
        127 : 'Partly cloudy with little temperature change.',
        128 : 'Mostly clear with little temperature change.',
        129 : 'Increasing clouds and cooler. Precipitation possible within 12 hours, possibly heavy at times. Windy.',
        130 : 'Mostly cloudy and cooler. Precipitation ending within 6 hours. Windy.',
        131 : 'Partly cloudy with little temperature change.',
        132 : 'Mostly clear with little temperature change.',
        133 : 'Mostly cloudy and cooler. Precipitation possible within 12 hours. Windy.',
        134 : 'Mostly cloudy and cooler. Precipitation ending in 12 to 24 hours.',
        135 : 'Mostly cloudy and cooler.',
        136 : 'Mostly cloudy and cooler. Precipitation continuing, possible heavy at times. Windy.',
        137 : 'Partly cloudy with little temperature change.',
        138 : 'Mostly clear with little temperature change.',
        139 : 'Mostly cloudy and cooler. Precipitation possible within 6 to 12 hours. Windy.',
        140 : 'Mostly cloudy with little temperature change. Precipitation continuing, possibly heavy at times. Windy.',
        141 : 'Partly cloudy with little temperature change.',
        142 : 'Mostly clear with little temperature change.',
        143 : 'Mostly cloudy with little temperature change. Precipitation possible within 6 to 12 hours. Windy.',
        144 : 'Partly cloudy with little temperature change.',
        145 : 'Mostly clear with little temperature change.',
        146 : 'Increasing clouds with little temperature change. Precipitation possible within 12 hours, possibly heavy at times. Windy.',
        147 : 'Mostly cloudy and cooler. Windy.',
        148 : 'Mostly cloudy and cooler. Precipitation continuing, possibly heavy at times. Windy.',
        149 : 'Partly cloudy with little temperature change.',
        150 : 'Mostly clear with little temperature change.',
        151 : 'Mostly cloudy and cooler. Precipitation likely, possibly heavy at times. Windy.',
        152 : 'Mostly cloudy with little temperature change. Precipitation continuing, possibly heavy at times. Windy.',
        153 : 'Mostly cloudy with little temperature change. Precipitation likely, possibly heavy at times. Windy.',
        154 : 'Partly cloudy with little temperature change.',
        155 : 'Mostly clear with little temperature change.',
        156 : 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy.',
        157 : 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy',
        158 : 'Increasing clouds and cooler. Precipitation continuing. Windy with possible wind shift to the W, NW, or N.',
        159 : 'Partly cloudy with little temperature change.',
        160 : 'Mostly clear with little temperature change.',
        161 : 'Mostly cloudy and cooler. Precipitation likely. Windy with possible wind shift to the W, NW, or N.',
        162 : 'Mostly cloudy with little temperature change. Precipitation continuing. Windy with possible wind shift to the W, NW, or N.',
        163 : 'Mostly cloudy with little temperature change. Precipitation likely. Windy with possible wind shift to the W, NW, or N.',
        164 : 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy with possible wind shift to the W, NW, or N.',
        165 : 'Partly cloudy with little temperature change.',
        166 : 'Mostly clear with little temperature change.',
        167 : 'Increasing clouds and cooler. Precipitation possible within 6 hours possible wind shift to the W, NW, or N.',
        168 : 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy with possible wind shift to the W, NW, or N.',
        169 : 'Increasing clouds with little temperature change. Precipitation possible within 6 hours possible wind shift to the W, NW, or N.',
        170 : 'Partly cloudy with little temperature change.',
        171 : 'Mostly clear with little temperature change.',
        172 : 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy with possible wind shift to the W, NW, or N.',
        173 : 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy with possible wind shift to the W, NW, or N.',
        174 : 'Partly cloudy with little temperature change.',
        175 : 'Mostly clear with little temperature change.',
        176 : 'Increasing clouds and cooler. Precipitation possible within 12 to 24 hours. Windy with possible wind shift to the W, NW, or N.',
        177 : 'Increasing clouds with little temperature change. Precipitation possible within 12 to 24 hours. Windy with possible wind shift to the W, NW, or N.',
        178 : 'Mostly cloudy and cooler. Precipitation possibly heavy at times and ending within 12 hours. Windy with possible wind shift to the W, NW, or N.',
        179 : 'Partly cloudy with little temperature change.',
        180 : 'Mostly clear with little temperature change.',
        181 : 'Mostly cloudy and cooler. Precipitation possible within 6 to 12 hours, possibly heavy at times. Windy with possible wind shift to the W, NW, or N.',
        182 : 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours. Windy with possible wind shift to the W, NW, or N.',
        183 : 'Mostly cloudy with little temperature change. Precipitation possible within 6 to 12 hours, possibly heavy at times. Windy with possible wind shift to the W, NW, or N.',
        184 : 'Mostly cloudy and cooler. Precipitation continuing.',
        185 : 'Partly cloudy with little temperature change.',
        186 : 'Mostly clear with little temperature change.',
        187 : 'Mostly cloudy and cooler. Precipitation likely. Windy with possible wind shift to the W, NW, or N.',
        188 : 'Mostly cloudy with little temperature change. Precipitation continuing.',
        189 : 'Mostly cloudy with little temperature change. Precipitation likely.',
        190 : 'Partly cloudy with little temperature change.',
        191 : 'Mostly clear with little temperature change.',
        192 : 'Mostly cloudy and cooler. Precipitation possible within 12 hours, possibly heavy at times. Windy.',
        193 : 'FORECAST REQUIRES 3 HOURS OF RECENT DATA',
        194 : 'Mostly clear and cooler.',
        195 : 'Mostly clear and cooler.',
        196 : 'Mostly clear and cooler.'
        }

class wdSuppThread(threading.Thread):
    """ Thread in which to run WdSuppArchive service.
    
        As we need to obtain WU data via WU API query we need to run this in 
        another thread so as to not hold up Weewx if we have a slow connection 
        or WU is unresponsive for any reason.
    """
    
    def __init__(self, target, *args):
        self._target = target
        self._args = args
        threading.Thread.__init__(self)

    def run(self):
        self._target(*self._args)
    
class WdSuppArchive(weewx.engine.StdService):
    """ Service to obtain and archive WU API sourced data and Davis console
        forecast data as well as calculate and archive theoretical max solar 
        radiation data.
    """
    
    def __init__(self, engine, config_dict):
        super(WdSuppArchive, self).__init__(engine, config_dict)

        #
        # Setup for WU API calls/Vantage Console data
        #
        
        # Get station info required for Sun related calcs
        self.latitude = float(config_dict['Station']['latitude'])
        self.longitude = float(config_dict['Station']['longitude'])
        self.altitude = convert(engine.stn_info.altitude_vt, 'meter')[0]
        # Create a list of the WU API calls we need
        self.WUqueryTypes=['conditions', 'forecast', 'almanac']
        # Set interval between API calls for each API call type we need
        self.interval = {}
        self.interval['conditions'] = int(self.config_dict['Weewx-WD']['Supplementary']['WU'].get('current_interval', 1800))
        self.interval['forecast'] = int(self.config_dict['Weewx-WD']['Supplementary']['WU'].get('forecast_interval', 1800))
        self.interval['almanac'] = int(self.config_dict['Weewx-WD']['Supplementary']['WU'].get('almanac_interval', 3600))
        # Set ts we last made the call
        self.last = {}
        self.last['conditions'] = None
        self.last['forecast'] = None
        self.last['almanac'] = None
        # Create holder for WU responses
        self.response = {}
        # Create holder for Davis Console loop data
        self.loop_packet = {}
        # Set max no of tries we will make in any one attempt to contact WU via API
        self.max_WU_tries = self.config_dict['Weewx-WD']['Supplementary']['WU'].get('max_WU_tries', 3)
        self.max_WU_tries = toint('max_WU_tries', self.max_WU_tries, 3)
        # set API call lockout period. refer weewx.conf
        self.api_lockout_period = self.config_dict['Weewx-WD']['Supplementary']['WU'].get('api_lockout_period', 60)
        self.api_lockout_period = toint('api_lockout_period', self.api_lockout_period, 60)
        # create holder for last WU API call ts
        self.last_WU_query = None
        # Get our API key from weewx.conf, first look in [Weewx-WD] and if no luck
        # try [Forecast] if it exists. Wrap in a try..except loop to catch exceptions (ie one or
        # both don't exist.
        try:
            if self.config_dict['Weewx-WD']['Supplementary']['WU'].get('apiKey', None) != None:
                self.api_key = self.config_dict['Weewx-WD']['Supplementary']['WU'].get('apiKey')
            elif self.config_dict['Forecast']['WU'].get('api_key', None) != None:
                self.api_key = self.config_dict['Forecast']['WU'].get('api_key')
            else:
                loginf("Cannot find valid Weather Underground API key")
        except:
            loginf("Cannot find Weather Underground API key")
        # Get our 'location' for use in WU API calls. Refer weewx.conf for details.
        self.location = self.config_dict['Weewx-WD']['Supplementary']['WU'].get('location', (self.latitude, self.longitude))
        # Set fixed part of WU API call url
        self.default_url = 'http://api.wunderground.com/api'
        
        # Extract our binding from the [Weewx-WD][[Supplementary]] section of 
        # the config file. If it's missing, fill with a default
        if 'Weewx-WD' in config_dict:
            self.binding = config_dict['Weewx-WD']['Supplementary'].get('data_binding', 'wdsupp_binding')
        else:
            self.binding = 'wdsupp_binding'
            
        syslog.syslog(syslog.LOG_INFO, "engine: WdSuppArchive will use data binding %s" % self.binding)
        
        # setup our database if needed
        self.setup_database(config_dict)
        
        # Set some of our parameters we require to manage the db
        # How long to keep loop records
        self.max_age = config_dict['Weewx-WD']['Supplementary'].get('max_age', 691200)
        self.max_age = toint('max_age', self.max_age, 691200)
        # Option to vacuum the sqlite database
        self.vacuum = config_dict['Weewx-WD']['Supplementary'].get('vacuum', 86400)
        self.vacuum = toint('vacuum', self.vacuum, 86400)
        # ts at which we last vacuumed
        self.last_vacuum = None
        # How often to retry database failures
        self.db_max_tries = config_dict['Weewx-WD']['Supplementary'].get('database_max_tries', 3)
        self.db_max_tries = int(self.db_max_tries)
        # How long to wait between retries, in seconds
        self.db_retry_wait = config_dict['Weewx-WD']['Supplementary'].get('database_retry_wait', 10)
        self.db_retry_wait = int(self.db_retry_wait)

        # set the unit groups for our obs
        obs_group_dict["tempRecordHigh"] = "group_temperature"
        obs_group_dict["tempNormalHigh"] = "group_temperature"
        obs_group_dict["tempRecordLow"] = "group_temperature"
        obs_group_dict["tempNormalLow"] = "group_temperature"
        obs_group_dict["stormRain"] = "group_rain"
        obs_group_dict["stormStart"] = "group_time"
        
        # Bind ourself to NEW_ARCHIVE_RECORD to ensure we have a chance to:
        # - update WU data(if necessary)
        # - save our data
        # on each new record
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        # bind ourself to each new loop packet so we can capture Davis
        # Vantage forecast data
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        loginf(('forecast interval=%s conditions interval=%s almanac interval=%s '
               'max_age=%s vacuum=%s api_key=%s location=%s') %
               (self.interval['forecast'], self.interval['conditions'], self.interval['almanac'],
               self.max_age, self.vacuum, 'xxxxxxxxxxxx'+self.api_key[-4:], self.location))

    def new_archive_record(self, event):
        """ Kick off in a new thread.
        """
        
        t = wdSuppThread(self.wdSupp_main, event)
        t.setName('wdSuppThread')
        t.start()
        self.wdSupp_main(event)

    def wdSupp_main(self, event):
        """ Take care of getting our data, archiving it and completing any 
            database housekeeping.
        
            Step through each of our WU API calls and obtain our results. Parse 
            these results and then save to archive. Calculate theoretical max 
            solar radiation and archive it. Delete any old records and 'vacuum'
            the database if required.
        """

        # Get time now as a ts
        now = time.time()
        # Get ts of record about to be processed
        rec_ts = event.record['dateTime']
        # Almanac gives more accurate results if current temp and pressure provided
        # Initialise some defaults
        temperature_C = 15.0
        pressure_mbar = 1010.0
        # Get current outTemp and barometer if they exist
        if 'outTemp' in event.record:
            temperature_C = weewx.units.convert(weewx.units.as_value_tuple(event.record, 'outTemp'),
                                                "degree_C")[0]
        if 'barometer' in event.record:
            pressure_mbar = weewx.units.convert(weewx.units.as_value_tuple(event.record, 'barometer'),
                                                "mbar")[0]
        # Get our almanac object
        self.almanac = weewx.almanac.Almanac(rec_ts, self.latitude, self.longitude, self.altitude,
                                             temperature_C, pressure_mbar)
        # Work out sunrise and sunset ts so we can determine if it is night or day. Needed so
        # we can set day or night icons when translating WU icons to Saratoga icons
        sunrise_ts = self.almanac.sun.rise.raw
        sunset_ts = self.almanac.sun.set.raw
        # If we are not between sunrise and sunset it must be night
        self.night = not (sunrise_ts < rec_ts < sunset_ts)
        # Loop through our list of API calls to be made
        for _WUquery in self.WUqueryTypes:
            logdbg("Last Weather Underground %s query at %s" % (_WUquery, self.last[_WUquery]))
            # Has it been at least 60 seconds since our last API call?
            if self.last_WU_query is None or ((now + 1 - self.api_lockout_period) >= self.last_WU_query):
                # If we haven't made this API call previously or if its been too long since
                # the last call then make the call
                if (self.last[_WUquery] is None) or ((now + 1 - self.interval[_WUquery]) >= self.last[_WUquery]):
                    # Make the call, wrap in a try..except just in case
                    try:
                        self.response[_WUquery] = self.get_WU_response(_WUquery, self.max_WU_tries)
                        logdbg("Downloaded updated Weather Underground %s information" % (_WUquery))
                        # If we got something back then reset our timer
                        if self.response[_WUquery] is not None:
                            self.last[_WUquery] = now
                    except:
                        loginf("Weather Underground '%s' API query failure" % (_WUquery))
            else:
                # API call limiter kicked in so say so
                loginf("API call limit reached. Tried to make an API call within %d sec of the previous call. API call skipped." % (self.api_lockout_period, ))
                break
        self.last_WU_query = max(self.last[q] for q in self.last)
        # Parse the WU responses and put into a dictionary
        _data_packet = self.parse_WU_responses(event)
        # Add our latest loop info from the Vantage if available
        if 'forecastIcon' in self.loop_packet:
            _data_packet['vantageForecastIcon'] = self.loop_packet['forecastIcon']
        if 'forecastRule' in self.loop_packet:
            try:
                _data_packet['vantageForecastRule'] = davis_fr_dict[self.loop_packet['forecastRule']]
            except:
                _data_packet['vantageForecastRule'] = ""
                loginf('parse_WU_responses: Could not decode Vantage forecast code.')
        if 'stormRain' in self.loop_packet:
            _data_packet['stormRain'] = self.loop_packet['stormRain']
        if 'stormStart' in self.loop_packet:
            _data_packet['stormStart'] = self.loop_packet['stormStart']
        # Add theoretical solar radiation value
        _data_packet['theoreticalRadiation'] = self.calc_rs_radiation()
        # Get a dictionary for our database manager
        dbm_dict = weewx.manager.get_manager_dict(self.config_dict['DataBindings'],
                                                  self.config_dict['Databases'],
                                                  self.binding,
                                                  default_binding_dict=get_default_binding_dict())
        with weewx.manager.open_manager(dbm_dict) as dbm:
            # save our data
            self.save_packet(dbm, _data_packet, self.db_max_tries, self.db_retry_wait)
            # set ts of last packet processed
            self.last_ts = _data_packet['dateTime']
            # prune older packets and vacuum if required
            if self.max_age > 0:
                self.prune(dbm, self.last_ts - self.max_age,
                           self.db_max_tries,
                           self.db_retry_wait)
                # vacuum the database
                if self.vacuum > 0:
                    if self.last_vacuum is None or ((now + 1 - self.vacuum) >= self.last_vacuum):
                        self.vacuum_database(dbm)
                        self.last_vacuum = now
        return
        
    def get_WU_response(self, _WUquery, max_WU_tries):
        """ Construct then make a WU API call and return the raw response.
        """

        # Construct our API call URL
        url = '%s/%s/%s/pws:1/q/%s.json' % (self.default_url, self.api_key, _WUquery, self.location)
        # We will attempt the call max_WU_tries times
        for count in range(max_WU_tries):
            # Attempt the call
            try:
                w = urllib2.urlopen(url)
                _WUresponse = w.read()
                w.close()
                return _WUresponse
            except:
                loginf("Failed to get '%s' on attempt %d" % (_WUquery, count+1))
        else:
            loginf("Failed to get Weather Underground '%s'" % (_WUquery, ))
        return None

    def parse_WU_responses(self, event):
        """ Parse WU responses and construct a data packet with the required fields.
        """
        
        # Create a holder for the data (lines) we will write to file
        _data_packet = {}
        _data_packet['dateTime'] = event.record['dateTime']
        _data_packet['usUnits'] = event.record['usUnits']
        # Step through each of the API calls
        for _WUquery in self.WUqueryTypes:
            # Deserialise our JSON response
            _parsed_response = json.loads(self.response[_WUquery])
            # Check for recognised format
            if not 'response' in _parsed_response:
                loginf("Unknown format in Weather Underground '%s'" % (_WUquery, ))
                return _data_packet
            _response = _parsed_response['response']
            # Check for WU provided error otherwise start pulling in the fields/data we want
            if 'error' in _response:
                loginf("Error in Weather Underground '%s' response" % (_WUquery, ))
                return _data_packet
            # Forecast data
            elif _WUquery == 'forecast':
                # Look up Saratoga icon number given WU icon name
                _data_packet['forecastIcon'] = icon_dict[_parsed_response['forecast']['txt_forecast']['forecastday'][0]['icon']]
                _data_packet['forecastText'] = _parsed_response['forecast']['txt_forecast']['forecastday'][0]['fcttext']
                _data_packet['forecastTextMetric'] = _parsed_response['forecast']['txt_forecast']['forecastday'][0]['fcttext_metric']
            # Conditions data
            elif _WUquery == 'conditions':
                # WU does not seem to provide day/night icon name in their 'conditions' response so we
                # need to do. Just need to add 'nt_' to front of name before looking up in out Saratoga 
                # icons dictionary
                if self.night:
                    _data_packet['currentIcon'] = icon_dict['nt_' + _parsed_response['current_observation']['icon']]
                else:
                    _data_packet['currentIcon'] = icon_dict[_parsed_response['current_observation']['icon']]
                _data_packet['currentText'] = _parsed_response['current_observation']['weather']
            # Almanac data
            elif _WUquery == 'almanac':
                if _data_packet['usUnits'] is weewx.US:
                    _data_packet['tempRecordHigh'] = _parsed_response['almanac']['temp_high']['record']['F']
                    _data_packet['tempNormalHigh'] = _parsed_response['almanac']['temp_high']['normal']['F']
                    _data_packet['tempRecordLow'] = _parsed_response['almanac']['temp_low']['record']['F']
                    _data_packet['tempNormalLow'] = _parsed_response['almanac']['temp_low']['normal']['F']
                else:
                    _data_packet['tempRecordHigh'] = _parsed_response['almanac']['temp_high']['record']['C']
                    _data_packet['tempNormalHigh'] = _parsed_response['almanac']['temp_high']['normal']['C']
                    _data_packet['tempRecordLow'] = _parsed_response['almanac']['temp_low']['record']['C']
                    _data_packet['tempNormalLow'] = _parsed_response['almanac']['temp_low']['normal']['C']
                _data_packet['tempRecordHighYear'] = _parsed_response['almanac']['temp_high']['recordyear']
                _data_packet['tempRecordLowYear'] = _parsed_response['almanac']['temp_low']['recordyear']
        return _data_packet
        
    def calc_rs_radiation(self):
        """ Calculate the theoretical solar radiation value using the 
            1972 Ryan-Stolzenbach model.
            http://www.ecy.wa.gov/programs/eap/models.html

            Rs = Rstoa * (ATC ^ Rm)
            Rstoa = (R0 * sin(El))/(R ^ 2)
            Rm = (((288 - 0.0065 * Z)/288) ^ 5.256)/(sin(El) + 0.15 * ((El + 3.885) ^ -1.253))
            
            where:
                Rs    = radiation on the ground (W/m2)
                Rstoa = radiation at top of atmosphere (W/m2)
                ATC   = atmospheric transmission coefficient (0.70-0.91)
                R0    = extraterrestrial radiation = 1367 W/m2
                El    = solar elevation (degrees)
                R     = distance from earth to sun (AU)
                Z     = elevation (metres)
        """
        
        R = self.almanac.sun.earth_distance
        Z = self.altitude
        R0 = 1367.0
        ATC = 0.8
        El = self.almanac.sun.alt
        sinEl = math.sin(math.radians(El))
        if sinEl < 0:
            return 0.0
        else:
            Rm = math.pow(((288 - 0.0065 * Z)/288), 5.256)/(sinEl + 0.15 * math.pow((El + 3.885), -1.253))
            Rs_toa = R0 * sinEl/math.pow(R, 2)
            Rs = Rs_toa * math.pow(ATC, Rm)
            return Rs

    @staticmethod
    def save_packet(dbm, _data_packet, max_tries=3, retry_wait=10):
        """ Save a data packet to our database.
        """
        
        for count in range(max_tries):
            try:
                logdbg('saving WU response')
                # save our data to the database
                dbm.addRecord(_data_packet, log_level=syslog.LOG_DEBUG)
                break
            except Exception, e:
                logerr('save failed (attempt %d of %d): %s' %
                       ((count + 1), max_tries, e))
                logerr('waiting %d seconds before retry' % (retry_wait, ))
                time.sleep(retry_wait)
        else:
            raise Exception('save failed after %d attempts' % max_tries)

    @staticmethod
    def prune(dbm, ts, max_tries=3, retry_wait=10):
        """ Remove records older than ts from the database.
        """

        sql = "delete from %s where dateTime < %d" % (dbm.table_name, ts)
        for count in range(max_tries):
            try:
                logdbg('deleting data prior to %d' % (ts, ))
                dbm.getSql(sql)
                logdbg('deleted prior to %d' % (ts))
                break
            except Exception, e:
                logerr('prune failed (attempt %d of %d): %s' % ((count+1), max_tries, e))
                logerr('waiting %d seconds before retry' % (retry_wait, ))
                time.sleep(retry_wait)
        else:
            raise Exception('prune failed after %d attemps' % max_tries)
        return

    @staticmethod
    def vacuum_database(dbm):
        """ Vacuum our database to save space.
        """
        
        # SQLite databases need a little help to prevent them from continually 
        # growing in size even though we prune records from the database. 
        # Vacuum will only work on SQLite databases.  It will compact the 
        # database file. It should be OK to run this on a MySQL database - it
        # will silently fail.
        
# remove timing code once we get a handle on how long this takes
        # Get time now as a ts
        t1 = time.time()
        try:
            logdbg('vacuuming database %s' % (dbm.database_name))
            dbm.getSql('vacuum')
        except Exception, e:
            logerr('Vacuuming database % failed: %s' % (dbm.database_name, e))

        t2 = time.time()
        loginf("vacuum_database executed in %0.9f seconds" % (t2-t1))
        
    def setup_database(self, config_dict):
        """ Setup the database table we will be using.
        """

        # This will create the database and/or table if either doesn't exist, 
        # then return an opened instance of the database manager.
        dbmanager = self.engine.db_binder.get_database(self.binding, initialize=True)
        syslog.syslog(syslog.LOG_INFO, "engine: Using binding '%s' to database '%s'" % (self.binding, dbmanager.database_name))
        
    def new_loop_packet(self, event):
        """ Save Davis Console forecast data that arrives in loop packets so 
            we can save it to archive later.
        
            The Davis Console forecast data is published in each loop packet. 
            There is little benefit in saving this data to database each loop 
            period as the data is slow changing so we will stash the data and 
            save to database each archive period along with our WU sourced data.
        """
        
        # update our stashed loop packet data
        try:
            # We only need 2 fields
            self.loop_packet['forecastIcon'] = event.packet['forecastIcon']
            self.loop_packet['forecastRule'] = event.packet['forecastRule']
            self.loop_packet['stormRain'] = event.packet['stormRain']
            self.loop_packet['stormStart'] = event.packet['stormStart']
        except:
            loginf('new_loop_packet: Loop packet data error. Cannot decode packet.')
        
    def shutDown(self):
        pass