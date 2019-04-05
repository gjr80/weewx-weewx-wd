"""
weewxwd.py

Service classes used by WeeWX-WD

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

Version: 1.2.0a1                                    Date: 29 March 2019

Revision History
    29 March 2019       v1.2.0a1
        - revised for WeeWX v3.5.0
        - moved __main__ code to weewxwd_config utility
        - now uses appTemp and humidex as provided by StdWXCalculate
        - simplified WdWXCalculate.new_loop_packet,
          WdWXCalculate.new_archive_record and WdArchive.new_archive_record
          methods
        - simplified outTempDay and outTempNight calculations
        - simplified function toint()
        - added support for a WeeWX-WD supplementary database for recording
          short term information such as theoretical solar max, WU current 
          conditions, WU forecast and WU almanac data
        - added WU API language support
        - added ability to exercise WU aspects of weewxwd.py without the
          overheads of running a WeeWX instance
        - added current_label config option to allow a user defined label to be
          prepended to the current conditions text
        - fixed bug that occurred on partial packet stations that occasionally 
          omit outTemp from packets/records
        - changed behaviour for calculating derived obs. If any one of the 
          pre-requisite obs are missing then the derived obs is not calculated 
          and not added to the packet/record. If all of the pre-requisite obs 
          exist but one or more is None then the derived obs is set to None. If 
          all pre-requisite obs exist and are non-None then the derived obs is 
          calculated and added to the packet/record as normal.
        - simplified WdArchive new_archive_record() method
Previous Bitbucket revision history
    31 March 2017       v1.0.3
        - no change, version number change only
    14 December 2016    v1.0.2
        - no change, version number change only
    30 November 2016    v1.0.1
        - now uses humidex and appTemp formulae from weewx.wxformulas
        - WeeWX-WD db management functions moved to wd_database utility
        - implemented syslog wrapper functions
        - minor reformatting
        - replaced calls to superseded DBBinder.get_database method with
          DBBinder.get_manager method
        - removed database management utility functions and placed in new
          wd_database utility
    10 January 2015     v1.0.0
        - rewritten for WeeWX v3.0
        - uses separate database for WeeWX-WD specific data, no longer
          recycles existing WeeWX database fields
        - added __main__ to allow command line execution of a number of db
          management actions
        - removed --debug option from main()
        - added --create_archive option to main() to create the weewxwd
          database
        - split --backfill_daily into separate --drop_daily and
          --backfill_daily options
        - added 'user.' to all WeeWX-WD imports
    18 September 2014   v0.9.4 (never released)
        - added GNU license text
    18 May 2014         v0.9.2
        - removed code that set windDir/windGustDir to 0 if windDir/windGustDir
          were None respectively
    30 July 2013        v0.9.1
        - revised version number to align with WeeWX-WD version numbering
    20 July 2013        v0.1
        - initial implementation
"""

# python imports
import Queue
import socket
import syslog
import threading
import urllib2
import json
import time
from datetime import datetime

# WeeWX imports
import weeutil.weeutil
import weewx
import weewx.almanac
import weewx.engine
import weewx.manager
import weewx.units
import weewx.wxformulas

from weewx.units import convert, obs_group_dict
from weeutil.weeutil import accumulateLeaves, to_int, to_bool

WEEWXWD_VERSION = '1.2.0a1'


# define a dictionary with our API call query details
WU_queries = [
    {'name': 'conditions',
     'interval': None,
     'last': None,
     'def_interval': 1800,
     'response': None,
     'json_title': 'current_observation'
     },
    {'name': 'forecast',
     'interval': None,
     'last': None,
     'def_interval': 1800,
     'response': None,
     'json_title': 'forecast'
     },
    {'name': 'almanac',
     'interval': None,
     'last': None,
     'def_interval': 3600,
     'response': None,
     'json_title': 'almanac'
     }
    ]

# define dict of languages supported by the WU API
WU_languages = {
    'afrikaans': 'AF',
    'albanian': 'AL',
    'arabic': 'AR',
    'armenian': 'HY',
    'azerbaijani': 'AZ',
    'basque': 'EU',
    'belarusian': 'BY',
    'bulgarian': 'BU',
    'british english': 'LI',
    'burmese': 'MY',
    'catalan': 'CA',
    'chinese - simplified': 'CN',
    'chinese - traditional': 'TW',
    'croatian': 'CR',
    'czech': 'CZ',
    'danish': 'DK',
    'dhivehi': 'DV',
    'dutch': 'NL',
    'english': 'EN',
    'esperanto': 'EO',
    'estonian': 'ET',
    'farsi': 'FA',
    'finnish': 'FI',
    'french': 'FR',
    'french canadian': 'FC',
    'galician': 'GZ',
    'german': 'DL',
    'georgian': 'KA',
    'greek': 'GR',
    'gujarati': 'GU',
    'Haitian creole': 'HT',
    'hebrew': 'IL',
    'hindi': 'HI',
    'hungarian': 'HU',
    'icelandic': 'IS',
    'ido': 'IO',
    'indonesian': 'ID',
    'irish gaelic': 'IR',
    'italian': 'IT',
    'japanese': 'JP',
    'javanese': 'JW',
    'khmer': 'KM',
    'korean': 'KR',
    'kurdish': 'KU',
    'latin': 'LA',
    'latvian': 'LV',
    'lithuanian': 'LT',
    'low german': 'ND',
    'macedonian': 'MK',
    'maltese': 'MT',
    'mandinka': 'GM',
    'maori': 'MI',
    'marathi': 'MR',
    'mongolian': 'MN',
    'norwegian': 'NO',
    'occitan': 'OC',
    'pashto': 'PS',
    'plautdietsch': 'GN',
    'polish': 'PL',
    'portuguese': 'BR',
    'punjabi': 'PA',
    'romanian': 'RO',
    'russian': 'RU',
    'serbian': 'SR',
    'slovak': 'SK',
    'slovenian': 'SL',
    'spanish': 'SP',
    'swahili': 'SI',
    'swedish': 'SW',
    'swiss': 'CH',
    'tagalog': 'TL',
    'tatarish': 'TT',
    'thai': 'TH',
    'turkish': 'TR',
    'turkmen': 'TK',
    'ukrainian': 'UA',
    'uzbek': 'UZ',
    'vietnamese': 'VU',
    'welsh': 'CY',
    'wolof': 'SN',
    'yiddish - transliterated': 'JI',
    'yiddish - unicode': 'YI'
}

# Define a dictionary to look up WU icon names and
# return corresponding Saratoga icon code
icon_dict = {
    'clear': 0,
    'cloudy': 18,
    'flurries': 25,
    'fog': 11,
    'hazy': 7,
    'mostlycloudy': 18,
    'mostlysunny': 9,
    'partlycloudy': 19,
    'partlysunny': 9,
    'sleet': 23,
    'rain': 20,
    'snow': 25,
    'sunny': 28,
    'tstorms': 29,
    'nt_clear': 1,
    'nt_cloudy': 13,
    'nt_flurries': 16,
    'nt_fog': 11,
    'nt_hazy': 13,
    'nt_mostlycloudy': 13,
    'nt_mostlysunny': 1,
    'nt_partlycloudy': 4,
    'nt_partlysunny': 1,
    'nt_sleet': 12,
    'nt_rain': 14,
    'nt_snow': 16,
    'nt_tstorms': 17,
    'chancerain': 20,
    'chancesleet': 23,
    'chancesnow': 25,
    'chancetstorms': 29
    }

# Define a dictionary to look up Davis forecast rule
# and return forecast text
davis_fr_dict = {
        0: 'Mostly clear and cooler.',
        1: 'Mostly clear with little temperature change.',
        2: 'Mostly clear for 12 hours with little temperature change.',
        3: 'Mostly clear for 12 to 24 hours and cooler.',
        4: 'Mostly clear with little temperature change.',
        5: 'Partly cloudy and cooler.',
        6: 'Partly cloudy with little temperature change.',
        7: 'Partly cloudy with little temperature change.',
        8: 'Mostly clear and warmer.',
        9: 'Partly cloudy with little temperature change.',
        10: 'Partly cloudy with little temperature change.',
        11: 'Mostly clear with little temperature change.',
        12: 'Increasing clouds and warmer. Precipitation possible within 24 to 48 hours.',
        13: 'Partly cloudy with little temperature change.',
        14: 'Mostly clear with little temperature change.',
        15: 'Increasing clouds with little temperature change. Precipitation possible within 24 hours.',
        16: 'Mostly clear with little temperature change.',
        17: 'Partly cloudy with little temperature change.',
        18: 'Mostly clear with little temperature change.',
        19: 'Increasing clouds with little temperature change. Precipitation possible within 12 hours.',
        20: 'Mostly clear with little temperature change.',
        21: 'Partly cloudy with little temperature change.',
        22: 'Mostly clear with little temperature change.',
        23: 'Increasing clouds and warmer. Precipitation possible within 24 hours.',
        24: 'Mostly clear and warmer. Increasing winds.',
        25: 'Partly cloudy with little temperature change.',
        26: 'Mostly clear with little temperature change.',
        27: 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
        28: 'Mostly clear and warmer. Increasing winds.',
        29: 'Increasing clouds and warmer.',
        30: 'Partly cloudy with little temperature change.',
        31: 'Mostly clear with little temperature change.',
        32: 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
        33: 'Mostly clear and warmer. Increasing winds.',
        34: 'Increasing clouds and warmer.',
        35: 'Partly cloudy with little temperature change.',
        36: 'Mostly clear with little temperature change.',
        37: 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
        38: 'Partly cloudy with little temperature change.',
        39: 'Mostly clear with little temperature change.',
        40: 'Mostly clear and warmer. Precipitation possible within 48 hours.',
        41: 'Mostly clear and warmer.',
        42: 'Partly cloudy with little temperature change.',
        43: 'Mostly clear with little temperature change.',
        44: 'Increasing clouds with little temperature change. Precipitation possible within 24 to 48 hours.',
        45: 'Increasing clouds with little temperature change.',
        46: 'Partly cloudy with little temperature change.',
        47: 'Mostly clear with little temperature change.',
        48: 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours.',
        49: 'Partly cloudy with little temperature change.',
        50: 'Mostly clear with little temperature change.',
        51: 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
        52: 'Partly cloudy with little temperature change.',
        53: 'Mostly clear with little temperature change.',
        54: 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
        55: 'Partly cloudy with little temperature change.',
        56: 'Mostly clear with little temperature change.',
        57: 'Increasing clouds and warmer. Precipitation possible within 6 to 12 hours.',
        58: 'Partly cloudy with little temperature change.',
        59: 'Mostly clear with little temperature change.',
        60: 'Increasing clouds and warmer. Precipitation possible within 6 to 12 hours. Windy.',
        61: 'Partly cloudy with little temperature change.',
        62: 'Mostly clear with little temperature change.',
        63: 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
        64: 'Partly cloudy with little temperature change.',
        65: 'Mostly clear with little temperature change.',
        66: 'Increasing clouds and warmer. Precipitation possible within 12 hours.',
        67: 'Partly cloudy with little temperature change.',
        68: 'Mostly clear with little temperature change.',
        69: 'Increasing clouds and warmer. Precipitation likley.',
        70: 'Clearing and cooler. Precipitation ending within 6 hours.',
        71: 'Partly cloudy with little temperature change.',
        72: 'Clearing and cooler. Precipitation ending within 6 hours.',
        73: 'Mostly clear with little temperature change.',
        74: 'Clearing and cooler. Precipitation ending within 6 hours.',
        75: 'Partly cloudy and cooler.',
        76: 'Partly cloudy with little temperature change.',
        77: 'Mostly clear and cooler.',
        78: 'Clearing and cooler. Precipitation ending within 6 hours.',
        79: 'Mostly clear with little temperature change.',
        80: 'Clearing and cooler. Precipitation ending within 6 hours.',
        81: 'Mostly clear and cooler.',
        82: 'Partly cloudy with little temperature change.',
        83: 'Mostly clear with little temperature change.',
        84: 'Increasing clouds with little temperature change. Precipitation possible within 24 hours.',
        85: 'Mostly cloudy and cooler. Precipitation continuing.',
        86: 'Partly cloudy with little temperature change.',
        87: 'Mostly clear with little temperature change.',
        88: 'Mostly cloudy and cooler. Precipitation likely.',
        89: 'Mostly cloudy with little temperature change. Precipitation continuing.',
        90: 'Mostly cloudy with little temperature change. Precipitation likely.',
        91: 'Partly cloudy with little temperature change.',
        92: 'Mostly clear with little temperature change.',
        93: 'Increasing clouds and cooler. Precipitation possible and windy within 6 hours.',
        94: 'Increasing clouds with little temperature change. Precipitation possible and windy within 6 hours.',
        95: 'Mostly cloudy and cooler. Precipitation continuing. Increasing winds.',
        96: 'Partly cloudy with little temperature change.',
        97: 'Mostly clear with little temperature change.',
        98: 'Mostly cloudy and cooler. Precipitation likely. Increasing winds.',
        99: 'Mostly cloudy with little temperature change. Precipitation continuing. Increasing winds.',
        100: 'Mostly cloudy with little temperature change. Precipitation likely. Increasing winds.',
        101: 'Partly cloudy with little temperature change.',
        102: 'Mostly clear with little temperature change.',
        103: 'Increasing clouds and cooler. Precipitation possible within 12 to 24 hours possible wind shift '
             'to the W, NW, or N.',
        104: 'Increasing clouds with little temperature change. Precipitation possible within 12 to 24 hours '
             'possible wind shift to the W, NW, or N.',
        105: 'Partly cloudy with little temperature change.',
        106: 'Mostly clear with little temperature change.',
        107: 'Increasing clouds and cooler. Precipitation possible within 6 hours possible wind shift to the '
             'W, NW, or N.',
        108: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours possible '
             'wind shift to the W, NW, or N.',
        109: 'Mostly cloudy and cooler. Precipitation ending within 12 hours possible wind shift to the W, NW, or N.',
        110: 'Mostly cloudy and cooler. Possible wind shift to the W, NW, or N.',
        111: 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours possible wind '
             'shift to the W, NW, or N.',
        112: 'Mostly cloudy with little temperature change. Possible wind shift to the W, NW, or N.',
        113: 'Mostly cloudy and cooler. Precipitation ending within 12 hours possible wind shift to the W, NW, or N.',
        114: 'Partly cloudy with little temperature change.',
        115: 'Mostly clear with little temperature change.',
        116: 'Mostly cloudy and cooler. Precipitation possible within 24 hours possible wind shift to the W, NW, or N.',
        117: 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours possible wind '
             'shift to the W, NW, or N.',
        118: 'Mostly cloudy with little temperature change. Precipitation possible within 24 hours possible wind '
             'shift to the W, NW, or N.',
        119: 'Clearing, cooler and windy. Precipitation ending within 6 hours.',
        120: 'Clearing, cooler and windy.',
        121: 'Mostly cloudy and cooler. Precipitation ending within 6 hours. Windy with possible wind shift to the '
             'W, NW, or N.',
        122: 'Mostly cloudy and cooler. Windy with possible wind shift o the W, NW, or N.',
        123: 'Clearing, cooler and windy.',
        124: 'Partly cloudy with little temperature change.',
        125: 'Mostly clear with little temperature change.',
        126: 'Mostly cloudy with little temperature change. Precipitation possible within 12 hours. Windy.',
        127: 'Partly cloudy with little temperature change.',
        128: 'Mostly clear with little temperature change.',
        129: 'Increasing clouds and cooler. Precipitation possible within 12 hours, possibly heavy at times. Windy.',
        130: 'Mostly cloudy and cooler. Precipitation ending within 6 hours. Windy.',
        131: 'Partly cloudy with little temperature change.',
        132: 'Mostly clear with little temperature change.',
        133: 'Mostly cloudy and cooler. Precipitation possible within 12 hours. Windy.',
        134: 'Mostly cloudy and cooler. Precipitation ending in 12 to 24 hours.',
        135: 'Mostly cloudy and cooler.',
        136: 'Mostly cloudy and cooler. Precipitation continuing, possible heavy at times. Windy.',
        137: 'Partly cloudy with little temperature change.',
        138: 'Mostly clear with little temperature change.',
        139: 'Mostly cloudy and cooler. Precipitation possible within 6 to 12 hours. Windy.',
        140: 'Mostly cloudy with little temperature change. Precipitation continuing, possibly heavy at times. Windy.',
        141: 'Partly cloudy with little temperature change.',
        142: 'Mostly clear with little temperature change.',
        143: 'Mostly cloudy with little temperature change. Precipitation possible within 6 to 12 hours. Windy.',
        144: 'Partly cloudy with little temperature change.',
        145: 'Mostly clear with little temperature change.',
        146: 'Increasing clouds with little temperature change. Precipitation possible within 12 hours, possibly '
             'heavy at times. Windy.',
        147: 'Mostly cloudy and cooler. Windy.',
        148: 'Mostly cloudy and cooler. Precipitation continuing, possibly heavy at times. Windy.',
        149: 'Partly cloudy with little temperature change.',
        150: 'Mostly clear with little temperature change.',
        151: 'Mostly cloudy and cooler. Precipitation likely, possibly heavy at times. Windy.',
        152: 'Mostly cloudy with little temperature change. Precipitation continuing, possibly heavy at times. Windy.',
        153: 'Mostly cloudy with little temperature change. Precipitation likely, possibly heavy at times. Windy.',
        154: 'Partly cloudy with little temperature change.',
        155: 'Mostly clear with little temperature change.',
        156: 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy.',
        157: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy',
        158: 'Increasing clouds and cooler. Precipitation continuing. Windy with possible wind shift to the W, NW, '
             'or N.',
        159: 'Partly cloudy with little temperature change.',
        160: 'Mostly clear with little temperature change.',
        161: 'Mostly cloudy and cooler. Precipitation likely. Windy with possible wind shift to the W, NW, or N.',
        162: 'Mostly cloudy with little temperature change. Precipitation continuing. Windy with possible wind shift '
             'to the W, NW, or N.',
        163: 'Mostly cloudy with little temperature change. Precipitation likely. Windy with possible wind shift to '
             'the W, NW, or N.',
        164: 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy with possible wind shift to '
             'the W, NW, or N.',
        165: 'Partly cloudy with little temperature change.',
        166: 'Mostly clear with little temperature change.',
        167: 'Increasing clouds and cooler. Precipitation possible within 6 hours possible wind shift to the W, NW, '
             'or N.',
        168: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy with '
             'possible wind shift to the W, NW, or N.',
        169: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours possible wind '
             'shift to the W, NW, or N.',
        170: 'Partly cloudy with little temperature change.',
        171: 'Mostly clear with little temperature change.',
        172: 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy with possible wind shift to '
             'the W, NW, or N.',
        173: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy with '
             'possible wind shift to the W, NW, or N.',
        174: 'Partly cloudy with little temperature change.',
        175: 'Mostly clear with little temperature change.',
        176: 'Increasing clouds and cooler. Precipitation possible within 12 to 24 hours. Windy with possible wind '
             'shift to the W, NW, or N.',
        177: 'Increasing clouds with little temperature change. Precipitation possible within 12 to 24 hours. Windy '
             'with possible wind shift to the W, NW, or N.',
        178: 'Mostly cloudy and cooler. Precipitation possibly heavy at times and ending within 12 hours. Windy with '
             'possible wind shift to the W, NW, or N.',
        179: 'Partly cloudy with little temperature change.',
        180: 'Mostly clear with little temperature change.',
        181: 'Mostly cloudy and cooler. Precipitation possible within 6 to 12 hours, possibly heavy at times. Windy '
             'with possible wind shift to the W, NW, or N.',
        182: 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours. Windy with possible '
             'wind shift to the W, NW, or N.',
        183: 'Mostly cloudy with little temperature change. Precipitation possible within 6 to 12 hours, possibly '
             'heavy at times. Windy with possible wind shift to the W, NW, or N.',
        184: 'Mostly cloudy and cooler. Precipitation continuing.',
        185: 'Partly cloudy with little temperature change.',
        186: 'Mostly clear with little temperature change.',
        187: 'Mostly cloudy and cooler. Precipitation likely. Windy with possible wind shift to the W, NW, or N.',
        188: 'Mostly cloudy with little temperature change. Precipitation continuing.',
        189: 'Mostly cloudy with little temperature change. Precipitation likely.',
        190: 'Partly cloudy with little temperature change.',
        191: 'Mostly clear with little temperature change.',
        192: 'Mostly cloudy and cooler. Precipitation possible within 12 hours, possibly heavy at times. Windy.',
        193: 'FORECAST REQUIRES 3 HOURS OF RECENT DATA',
        194: 'Mostly clear and cooler.',
        195: 'Mostly clear and cooler.',
        196: 'Mostly clear and cooler.'
        }


def logmsg(level, src, msg):
    syslog.syslog(level, '%s: %s' % (src, msg))


def logcrit(src, msg):
    logmsg(syslog.LOG_CRIT, src, msg)


def logdbg(src, msg):
    logmsg(syslog.LOG_DEBUG, src, msg)


def logdbg2(src, msg):
    if weewx.debug >= 2:
        logmsg(syslog.LOG_DEBUG, src, msg)


def loginf(src, msg):
    logmsg(syslog.LOG_INFO, src, msg)


def logerr(src, msg):
    logmsg(syslog.LOG_ERR, src, msg)


# ============================================================================
#                     Exceptions that could get thrown
# ============================================================================


class MissingApiKey(IOError):
    """Raised when an API key cannot be found for an external source/service."""


# ==============================================================================
#                              Class WdWXCalculate
# ==============================================================================


class WdWXCalculate(weewx.engine.StdService):
    """Service to calculate WeeWX-WD specific observations."""

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WdWXCalculate, self).__init__(engine, config_dict)

        # bind our self to new loop packet and new archive record events
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    @staticmethod
    def new_loop_packet(event):
        """Add outTempDay and outTempNight to the loop packet."""

        _x = dict()
        _x['outTempDay'], _x['outTempNight'] = calc_day_night(event.packet)
        event.packet.update(_x)

    @staticmethod
    def new_archive_record(event):
        """Add outTempDay and outTempNight to the archive record."""

        _x = dict()
        _x['outTempDay'], _x['outTempNight'] = calc_day_night(event.record)
        event.record.update(_x)


# ==============================================================================
#                                Class WdArchive
# ==============================================================================


class WdArchive(weewx.engine.StdService):
    """Service to store Weewx-WD specific archive data."""

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WdArchive, self).__init__(engine, config_dict)

        # Extract our binding from the WeeWX-WD section of the config file. If
        # it's missing, fill with a default.
        if 'WeewxWD' in config_dict:
            self.data_binding = config_dict['WeewxWD'].get('data_binding',
                                                           'wd_binding')
        else:
            self.data_binding = 'wd_binding'
        loginf("wdarchive",
               "WdArchive will use data binding %s" % self.data_binding)

        # extract the WeeWX binding for use when we check the need for backfill
        # from the WeeWX archive
        if 'StdArchive' in config_dict:
            self.data_binding_wx = config_dict['StdArchive'].get('data_binding',
                                                                 'wx_binding')
        else:
            self.data_binding_wx = 'wx_binding'

        # setup our database if needed
        self.setup_database()

        # set the unit groups for our obs
        obs_group_dict["humidex"] = "group_temperature"
        obs_group_dict["appTemp"] = "group_temperature"
        obs_group_dict["outTempDay"] = "group_temperature"
        obs_group_dict["outTempNight"] = "group_temperature"

        # bind ourselves to NEW_ARCHIVE_RECORD event
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_archive_record(self, event):
        """Save the WeeWX-WD archive record.

           Use our db manager's addRecord method to save the relevant WeeWX-WD
           fields to the WeeWX-WD archive.
        """

        # get our db manager
        dbmanager = self.engine.db_binder.get_manager(self.data_binding)
        # now put the record in the archive
        dbmanager.addRecord(event.record)

    def setup_database(self):
        """Setup the WeeWX-WD database"""

        # create the database if it doesn't exist and a db manager for the
        # opened database
        dbmanager = self.engine.db_binder.get_manager(self.data_binding,
                                                      initialize=True)
        loginf("wdarchive",
               "Using binding '%s' to database '%s'" % (self.data_binding,
                                                        dbmanager.database_name))

        # FIXME. Is this still required
        # Check if we have any historical data to bring in from the WeeWX
        # archive.
        # first get a dbmanager for the WeeWX archive
        dbmanager_wx = self.engine.db_binder.get_manager(self.data_binding_wx,
                                                         initialize=False)

        # then backfill the WeeWX-WD daily summaries
        loginf("wdarchive", "Starting backfill of daily summaries")
        t1 = time.time()
        nrecs, ndays = dbmanager_wx.backfill_day_summary()
        tdiff = time.time() - t1
        if nrecs:
            loginf("wdarchive",
                   "Processed %d records to backfill %d day summaries in %.2f seconds" % (nrecs,
                                                                                          ndays,
                                                                                          tdiff))
        else:
            loginf("wdarchive", "Daily summaries up to date.")


# ==============================================================================
#                            Class WdGenerateDerived
# ==============================================================================


class WdGenerateDerived(object):
    """ Adds WeeWX-WD derived obs to the output of the wrapped generator."""

    def __init__(self, input_generator):
        """ Initialize an instance of WdGenerateDerived

            input_generator: An iterator which will return dictionary records.
        """
        self.input_generator = input_generator

    def __iter__(self):
        return self

    def next(self):

        # get our next record
        _rec = self.input_generator.next()
        _mwx = weewx.units.to_METRICWX(_rec)

        # get our historical humidex, if not available then calculate it
        if _mwx['extraTemp1'] is not None:
            _mwx['humidex'] = _mwx['extraTemp1']
        else:
            if 'outTemp' in _mwx and 'outHumidity' in _mwx:
                _mwx['humidex'] = weewx.wxformulas.humidexC(_mwx['outTemp'],
                                                            _mwx['outHumidity'])
            else:
                _mwx['humidex'] = None

        # get our historical appTemp, if not available then calculate it
        if _mwx['extraTemp2'] is not None:
            _mwx['appTemp'] = _mwx['extraTemp2']
        else:
            if 'outTemp' in _mwx and 'outHumidity' in _mwx and 'windSpeed' in _mwx:
                _mwx['appTemp'] = weewx.wxformulas.apptempC(_mwx['outTemp'],
                                                            _mwx['outHumidity'],
                                                            _mwx['windSpeed'])
            else:
                _mwx['appTemp'] = None

        # 'calculate' outTempDay and outTempNight
        _mwx['outTempDay'], _mwx['outTempNight'] = calc_day_night(_mwx)

        # return our modified record
        return weewx.units.to_std_system(_mwx, _rec['usUnits'])


# ==============================================================================
#                              Class WdSuppArchive
# ==============================================================================


class WdSuppArchive(weewx.engine.StdService):
    """Service to archive WeeWX-WD supplementary data.


        Collects and archives WU API sourced data, Davis console forecast/storm 
        data and theoretical max solar radiation data in the WeeWX-WD supp
        database. Data is only kept for a limited time before being dropped.
    """

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WdSuppArchive, self).__init__(engine, config_dict)

        # Initialisation is 2 part; 1 part for wdsupp db/loop data, 2nd part for
        # WU API calls. We are only going to invoke our self if we have the
        # necessary config data available in weewx.conf for 1 or both parts. If
        # any essential config data is missing/not set then give a short log
        # message and defer.

        if 'Weewx-WD' in config_dict:
            # we have a [Weewx-WD] stanza
            if 'Supplementary' in config_dict['Weewx-WD']:
                # we have a [[Supplementary]] stanza so we can initialise
                # wdsupp db
                _supp_dict = config_dict['Weewx-WD']['Supplementary']
                
                # setup for archiving of supp data
                # first, get our binding, if it's missing use a default
                self.binding = _supp_dict.get('data_binding',
                                              'wdsupp_binding')
                loginf("wdsupparchive",
                       "WdSuppArchive will use data binding '%s'" % self.binding)
                # how long to keep records in our db (default 8 days)
                self.max_age = _supp_dict.get('max_age', 691200)
                self.max_age = toint(self.max_age, 691200)
                # how often to vacuum the sqlite database (default 24 hours)
                self.vacuum = _supp_dict.get('vacuum', 86400)
                self.vacuum = toint(self.vacuum, 86400)
                # how many times do we retry database failures (default 3)
                self.db_max_tries = _supp_dict.get('database_max_tries', 3)
                self.db_max_tries = int(self.db_max_tries)
                # how long to wait between retries (default 2 sec)
                self.db_retry_wait = _supp_dict.get('database_retry_wait', 2)
                self.db_retry_wait = int(self.db_retry_wait)
                # setup our database if needed
                self.setup_database()
                # ts at which we last vacuumed
                self.last_vacuum = None
                # create holder for Davis Console loop data
                self.loop_packet = {}

                # set the unit groups for our obs
                obs_group_dict["tempRecordHigh"] = "group_temperature"
                obs_group_dict["tempNormalHigh"] = "group_temperature"
                obs_group_dict["tempRecordLow"] = "group_temperature"
                obs_group_dict["tempNormalLow"] = "group_temperature"
                obs_group_dict["tempRecordHighYear"] = "group_count"
                obs_group_dict["tempRecordLowYear"] = "group_count"
                obs_group_dict["stormRain"] = "group_rain"
                obs_group_dict["stormStart"] = "group_time"
                obs_group_dict["maxSolarRad"] = "group_radiation"
                obs_group_dict["forecastIcon"] = "group_count"
                obs_group_dict["currentIcon"] = "group_count"
                obs_group_dict["vantageForecastIcon"] = "group_count"

                # set event bindings
                
                # bind to NEW_LOOP_PACKET so we can capture Davis Vantage forecast
                # data
                self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
                # bind to NEW_ARCHIVE_RECORD to ensure we have a chance to:
                # - update WU data(if necessary)
                # - save our data
                # on each new record
                self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

                # we have everything we need to put a short message re supp 
                # database
                loginf("wdsupparchive", "max_age=%s vacuum=%s" % (self.max_age,
                                                                   self.vacuum))
                
                # setup up any sources
                self.sources = dict()
                self.queues = dict()
                for source in _supp_dict.sections:
                    if source in KNOWN_SOURCES:
                        _source_dict = _supp_dict[source]
                        if _source_dict is not None:
                            # setup the result and control queues
                            self.queues[source] = {'control': Queue.Queue(),
                                                   'result': Queue.Queue()}
                            self.sources[source] = self.source_factory(source,
                                                                       self.queues[source],
                                                                       engine,
                                                                       _source_dict)
                            self.sources[source].start()
                        else:
                            loginf("wdsupparchive",
                                   "Source '%s' will be ignored, incomplete or missing config settings")

                # define some properties for later use
                self.last_ts = None

    @staticmethod
    def source_factory(source, queues_dict, engine, source_dict):
        """Factory to produce a source object."""

        # get the source class
        source_class = KNOWN_SOURCES.get(source)
        if source_class is not None:
            # get the source object
            source_object = source_class(queues_dict['control'],
                                         queues_dict['result'],
                                         engine,
                                         source_dict)
            return source_object

    def new_archive_record(self, event):
        """Action on a new archive record being created.

        Add anything we have to the archive record and then save to our
        database. Grab any forecast/storm loop data and theoretical max
        solar radiation. Archive our data, delete any stale records and
        'vacuum' the database if required.
        """

        # If we have a result queue check to see if we have received
        # any forecast data. Use get_nowait() so we don't block the
        # rtgd control queue. Wrap in a try..except to catch the error
        # if there is nothing in the queue.

        # get time now as a ts
        now = time.time()

        # get any data from the sources
        for source_name, source_object in self.sources.iteritems():
            _result_queue = self.queues[source_name]['result']
            if _result_queue:
                # if packets have backed up in the result queue, trim it until
                # we only have one entry, that will be the latest
                while _result_queue.qsize() > 1:
                    _result_queue.get()
            # now get any data in the queue
            try:
                # use nowait() so we don't block
                _package = _result_queue.get_nowait()
            except Queue.Empty:
                # nothing in the queue so continue
                pass
            else:
                # we did get something in the queue but was it a
                # 'forecast' package
                if isinstance(_package, dict):
                    if 'type' in _package and _package['type'] == 'data':
                        # we have forecast text so log and add it to the archive record
                        logdbg2("wdsupparchive",
                                "received forecast text: %s" % _package['payload'])
                        event.record.update(_package['payload'])

        # update our data record with any stashed loop data
        event.record.update(self.process_loop())

        # get a db manager dict
        dbm_dict = weewx.manager.get_manager_dict_from_config(self.config_dict,
                                                              self.binding)
        # now save the data
        with weewx.manager.open_manager(dbm_dict) as dbm:
            # save the record
            self.save_record(dbm, event.record, self.db_max_tries, self.db_retry_wait)
            # set ts of last packet processed
            self.last_ts = event.record['dateTime']
            # prune older packets and vacuum if required
            if self.max_age > 0:
                self.prune(dbm,
                           self.last_ts - self.max_age,
                           self.db_max_tries,
                           self.db_retry_wait)
                # vacuum the database
                if self.vacuum > 0:
                    if self.last_vacuum is None or ((now + 1 - self.vacuum) >= self.last_vacuum):
                        self.vacuum_database(dbm)
                        self.last_vacuum = now

    def new_loop_packet(self, event):
        """ Save Davis Console forecast data that arrives in loop packets so
            we can save it to archive later.

            The Davis Console forecast data is published in each loop packet.
            There is little benefit in saving this data to database each loop
            period as the data is slow changing so we will stash the data and
            save to database each archive period along with our WU sourced data.
        """

        # update stashed loop packet data
        self.loop_packet['forecastIcon'] = event.packet.get('forecastIcon')
        self.loop_packet['forecastRule'] = event.packet.get('forecastRule')
        self.loop_packet['stormRain'] = event.packet.get('stormRain')
        self.loop_packet['stormStart'] = event.packet.get('stormStart')
        self.loop_packet['maxSolarRad'] = event.packet.get('maxSolarRad')

    def process_loop(self):
        """ Process stashed loop data and populate fields as appropriate.

            Adds following fields (if available) to data dictionary:
                - forecast icon (Vantage only)
                - forecast rule (Vantage only)(Note returns full text forecast)
                - stormRain (Vantage only)
                - stormStart (Vantage only)
                - current theoretical max solar radiation
        """

        # holder dictionary for our gathered data
        _data = dict()
        # vantage forecast icon
        if self.loop_packet['forecastIcon'] is not None:
            _data['vantageForecastIcon'] = self.loop_packet['forecastIcon']
        # vantage forecast rule
        if self.loop_packet['forecastRule'] is not None:
            try:
                _data['vantageForecastRule'] = davis_fr_dict[self.loop_packet['forecastRule']]
            except KeyError:
                logdbg2("wdsupparchive",
                        "Could not decode Vantage forecast code")
        # vantage stormRain
        if self.loop_packet['stormRain'] is not None:
            _data['stormRain'] = self.loop_packet['stormRain']
        # vantage stormStart
        if self.loop_packet['stormStart'] is not None:
            _data['stormStart'] = self.loop_packet['stormStart']
        # theoretical solar radiation value
        _data['maxSolarRad'] = self.loop_packet['maxSolarRad']
        return _data

    @staticmethod
    def save_record(dbm, _data_record, max_tries=3, retry_wait=2):
        """Save a data record to our database."""

        for count in range(max_tries):
            try:
                # save our data to the database
                dbm.addRecord(_data_record)
                break
            except Exception, e:
                logerr("wdsupparchive",
                       "save failed (attempt %d of %d): %s" % ((count + 1),
                                                               max_tries, e))
                logerr("wdsupparchive",
                       "waiting %d seconds before retry" % (retry_wait, ))
                time.sleep(retry_wait)
        else:
            raise Exception("save failed after %d attempts" % max_tries)

    @staticmethod
    def prune(dbm, ts, max_tries=3, retry_wait=2):
        """Remove records older than ts from the database."""

        sql = "delete from %s where dateTime < %d" % (dbm.table_name, ts)
        for count in range(max_tries):
            try:
                dbm.getSql(sql)
                break
            except Exception, e:
                logerr("wdsupparchive",
                       "prune failed (attempt %d of %d): %s" % ((count+1),
                                                                max_tries, e))
                logerr("wdsupparchive",
                       "waiting %d seconds before retry" % (retry_wait, ))
                time.sleep(retry_wait)
        else:
            raise Exception("prune failed after %d attempts" % max_tries)
        return

    @staticmethod
    def vacuum_database(dbm):
        """Vacuum our database to save space."""

        # SQLite databases need a little help to prevent them from continually
        # growing in size even though we prune records from the database.
        # Vacuum will only work on SQLite databases.  It will compact the
        # database file. It should be OK to run this on a MySQL database - it
        # will silently fail.

        # Get time now as a ts
        t1 = time.time()
        # do the vacuum, wrap in try..except in case it fails
        try:
            dbm.getSql('vacuum')
        except Exception, e:
            logerr("wdsupparchive",
                   "Vacuuming database % failed: %s" % (dbm.database_name, e))

        t2 = time.time()
        logdbg("wdsupparchive",
               "vacuum_database executed in %0.9f seconds" % (t2-t1))

    def setup_database(self):
        """Setup the database table we will be using."""

        # This will create the database and/or table if either doesn't exist,
        # then return an opened instance of the database manager.
        dbmanager = self.engine.db_binder.get_database(self.binding,
                                                       initialize=True)
        loginf("wdsupparchive",
               "Using binding '%s' to database '%s'" % (self.binding,
                                                        dbmanager.database_name))

    def shutDown(self):
        """Shut down any threads.

        Would normally do all of a given threads actions in one go but since
        we may have more than one thread and so that we don't have sequential
        (potential) waits of up to 15 seconds we send each thread a shutdown
        signal and then go and check that each has indeed shutdown.
        """

        for source_name, source_object in self.sources.iteritems():
            if self.queues[source_name]['control'] and source_object.isAlive():
                # put a None in the control queue to signal the thread to
                # shutdown
                self.queues[source_name]['control'].put(None)


# ============================================================================
#                           class ThreadedSource
# ============================================================================


class ThreadedSource(threading.Thread):
    """Base class for a threaded external source.

    ThreadedSource constructor parameters:

        control_queue:       A Queue object used by our parent to control
                             (shutdown) this thread.
        result_queue:        A Queue object used to pass data to our parent
        engine:              an instance of weewx.engine.StdEngine
        source_config_dict:  A weeWX config dictionary.

    ThreadedSource methods:

        run.            Thread entry point, controls data fetching, parsing and
                        dispatch. Monitors the control queue.
        get_raw_data.       Obtain the raw data. This method must be written for
                        each child class.
        parse_data.     Parse the raw data and return the final  format data.
                        This method must be written for each child class.
    """

    def __init__(self, control_queue, result_queue, engine, source_config_dict):

        # initialize my superclass
        threading.Thread.__init__(self)

        # setup a some thread things
        self.setDaemon(True)
        # thread name needs to be set in the child class __init__() eg:
        #   self.setName('WdWuThread')

        # save the queues we will use
        self.control_queue = control_queue
        self.result_queue = result_queue

    def run(self):
        """Entry point for the thread."""

        self.setup()
        # since we are in a thread some additional try..except clauses will
        # help give additional output in case of an error rather than having
        # the thread die silently
        try:
            # Run a continuous loop, obtaining data as required and monitoring
            # the control queue for the shutdown signal. Only break out if we
            # receive the shutdown signal (None) from our parent.
            while True:
                # run an inner loop obtaining, parsing and dispatching the data
                # and checking for the shutdown signal
                # first up get the raw data
                _raw_data = self.get_raw_data()
                # if we have a non-None response then we have data so parse it,
                # gather the required data and put it in the result queue
                if _raw_data is not None:
                    # parse the raw data response and extract the required data
                    _data = self.parse_raw_data(_raw_data)
                    # if we have some data then place it in the result queue
                    if _data is not None:
                        # construct our data dict for the queue
                        _package = {'type': 'data',
                                    'payload': _data}
                        self.result_queue.put(_package)
                # now check to see if we have a shutdown signal
                try:
                    # Try to get data from the queue, block for up to 60
                    # seconds. If nothing is there an empty queue exception
                    # will be thrown after 60 seconds
                    _package = self.control_queue.get(block=True, timeout=60)
                except Queue.Empty:
                    # nothing in the queue so continue
                    pass
                else:
                    # something was in the queue, if it is the shutdown signal
                    # then return otherwise continue
                    if _package is None:
                        # we have a shutdown signal so return to exit
                        return
        except Exception, e:
            # Some unknown exception occurred. This is probably a serious
            # problem. Exit with some notification.
            logcrit("rtgd", "Unexpected exception of type %s" % (type(e),))
            weeutil.weeutil.log_traceback('rtgd: **** ')
            logcrit("rtgd", "Thread exiting. Reason: %s" % (e,))

    def setup(self):
        """Perform any post post-__init__() setup.

        This method is executed as the very first thing in the thread run()
        method. It must be defined if required for each child class.
        """

        pass

    def get_raw_data(self):
        """Obtain the raw block data.

        This method must be defined for each child class.
        """

        return None

    def parse_raw_data(self, response):
        """Parse the block response and return the required data.

        This method must be defined if the raw data from the block must be
        further processed to extract the final scroller text.
        """

        return response


# ============================================================================
#                              class WuSource
# ============================================================================


class WuSource(ThreadedSource):
    """Thread that obtains WU API forecast text and places it in a queue.

    The WuSource class queries the WU API and places selected forecast text in
    JSON format in a queue used by the data consumer. The WU API is called at a
    user selectable frequency. The thread listens for a shutdown signal from
    its parent.

    WUThread constructor parameters:

        control_queue:      A Queue object used by our parent to control
                            (shutdown) this thread.
        result_queue:       A Queue object used to pass forecast data to the
                            destination
        engine:             An instance of class weewx.weewx.Engine
        source_config_dict: A weeWX config dictionary.

    WUThread methods:

        run.               Control querying of the API and monitor the control
                           queue.
        query_wu.          Query the API and put selected forecast data in the
                           result queue.
        parse_wu_response. Parse a WU API response and return selected data.
    """

    VALID_FORECASTS = ('3day', '5day', '7day', '10day', '15day')
    VALID_NARRATIVES = ('day', 'day-night')
    VALID_LOCATORS = ('geocode', 'iataCode', 'icaoCode', 'placeid', 'postalKey')
    VALID_UNITS = ('e', 'm', 's', 'h')
    VALID_LANGUAGES = ('ar-AE', 'az-AZ', 'bg-BG', 'bn-BD', 'bn-IN', 'bs-BA',
                       'ca-ES', 'cs-CZ', 'da-DK', 'de-DE', 'el-GR', 'en-GB',
                       'en-IN', 'en-US', 'es-AR', 'es-ES', 'es-LA', 'es-MX',
                       'es-UN', 'es-US', 'et-EE', 'fa-IR', 'fi-FI', 'fr-CA',
                       'fr-FR', 'gu-IN', 'he-IL', 'hi-IN', 'hr-HR', 'hu-HU',
                       'in-ID', 'is-IS', 'it-IT', 'iw-IL', 'ja-JP', 'jv-ID',
                       'ka-GE', 'kk-KZ', 'kn-IN', 'ko-KR', 'lt-LT', 'lv-LV',
                       'mk-MK', 'mn-MN', 'ms-MY', 'nl-NL', 'no-NO', 'pl-PL',
                       'pt-BR', 'pt-PT', 'ro-RO', 'ru-RU', 'si-LK', 'sk-SK',
                       'sl-SI', 'sq-AL', 'sr-BA', 'sr-ME', 'sr-RS', 'sv-SE',
                       'sw-KE', 'ta-IN', 'ta-LK', 'te-IN', 'tg-TJ', 'th-TH',
                       'tk-TM', 'tl-PH', 'tr-TR', 'uk-UA', 'ur-PK', 'uz-UZ',
                       'vi-VN', 'zh-CN', 'zh-HK', 'zh-TW')

    def __init__(self, control_queue, result_queue, engine, source_config_dict):

        # initialize my superclass
        super(WuSource, self).__init__(control_queue, result_queue,
                                       engine, source_config_dict)

        # set thread name
        self.setName('WdWuThread')

        # WuSource debug level
        self.debug = to_int(source_config_dict.get('debug', 0))

        # interval between API calls
        self.interval = to_int(source_config_dict.get('interval', 1800))
        # max no of tries we will make in any one attempt to contact WU via API
        self.max_tries = to_int(source_config_dict.get('max_tries', 3))
        # Get API call lockout period. This is the minimum period between API
        # calls for the same feature. This prevents an error condition making
        # multiple rapid API calls and thus breach the API usage conditions.
        self.lockout_period = to_int(source_config_dict.get('api_lockout_period',
                                                            60))
        # initialise container for timestamp of last WU api call
        self.last_call_ts = None

        # get our API key from weewx.conf
        api_key = source_config_dict.get('api_key')
        if api_key is None:
            raise MissingApiKey("Cannot find valid Weather Underground API key")

        # get the forecast type
        _forecast = source_config_dict.get('forecast_type', '5day').lower()
        # validate forecast type
        self.forecast = _forecast if _forecast in self.VALID_FORECASTS else '5day'

        # get the forecast text to display
        _narrative = source_config_dict.get('forecast_text', 'day-night').lower()
        self.forecast_text = _narrative if _narrative in self.VALID_NARRATIVES else 'day-night'

        # FIXME, Not sure the logic is correct should we get a delinquent location setting
        # get the locator type and location argument to use for the forecast
        # first get the
        _location = source_config_dict.get('location', 'geocode').split(',', 1)
        _location_list = [a.strip() for a in _location]
        # validate the locator type
        self.locator = _location_list[0] if _location_list[0] in self.VALID_LOCATORS else 'geocode'
        if len(_location_list) == 2:
            self.location = _location_list[1]
        else:
            self.locator == 'geocode'
            self.location = '%s,%s' % (engine.stn_info.latitude_f,
                                       engine.stn_info.longitude_f)

        # get units to be used in forecast text
        _units = source_config_dict.get('units', 'm').lower()
        # validate units
        self.units = _units if _units in self.VALID_UNITS else 'm'

        # get language to be used in forecast text
        _language = source_config_dict.get('language', 'en-GB')
        # validate language
        self.language = _language if _language in self.VALID_LANGUAGES else 'en-GB'

        # set format of the API response
        self.format = 'json'

        # get a WeatherUndergroundAPI object to handle the API calls
        self.api = WeatherUndergroundAPIForecast(api_key)

        # log what we will do
        loginf("wdwusource",
               "Weather Underground API will be used for forecast data")
        if self.debug > 0:
            loginf("wdwusource",
                   "interval=%s lockout period=%s max tries=%s" % (self.interval,
                                                                   self.lockout_period,
                                                                   self.max_tries))
            loginf("wdwusource", "forecast=%s units=%s language=%s" % (self.forecast,
                                                                       self.units,
                                                                       self.language))
            loginf("wdwusource", "locator=%s location=%s" % (self.locator,
                                                             self.location))
            loginf("wdwusource", "Weather Underground debug=%s" % self.debug)

    def get_raw_data(self):
        """If required query the WU API and return the response.

        Checks to see if it is time to query the API, if so queries the API
        and returns the raw response in JSON format. To prevent the user
        exceeding their API call limit the query is only made if at least
        self.lockout_period seconds have elapsed since the last call.

        Inputs:
            None.

        Returns:
            The raw WU API response in JSON format.
        """

        # get the current time
        now = time.time()
        if self.debug > 0:
            loginf("wdwusource",
                   "Last Weather Underground API call at %s" % self.last_call_ts)

        # has the lockout period passed since the last call
        if self.last_call_ts is None or ((now + 1 - self.lockout_period) >= self.last_call_ts):
            # If we haven't made an API call previously or if its been too long
            # since the last call then make the call
            if (self.last_call_ts is None) or ((now + 1 - self.interval) >= self.last_call_ts):
                # Make the call, wrap in a try..except just in case
                try:
                    _response = self.api.forecast_request(forecast=self.forecast,
                                                          locator=self.locator,
                                                          location=self.location,
                                                          units=self.units,
                                                          language=self.language,
                                                          format=self.format,
                                                          max_tries=self.max_tries)
                    if self.debug > 0:
                        if _response is not None:
                            loginf("wdwusource",
                                   "Downloaded updated Weather Underground forecast")
                        else:
                            loginf("wdwusource",
                                   "Failed to download updated Weather Underground forecast")

                except Exception, e:
                    # Some unknown exception occurred. Set _response to None,
                    # log it and continue.
                    _response = None
                    loginf("wdwusource",
                           "Unexpected exception of type %s" % (type(e),))
                    weeutil.weeutil.log_traceback('WUThread: **** ')
                    loginf("wdwusource",
                           "Unexpected exception of type %s" % (type(e),))
                    loginf("wdwusource",
                           "Weather Underground API forecast query failed")
                # if we got something back then reset our last call timestamp
                if _response is not None:
                    self.last_call_ts = now
                return _response
        else:
            # API call limiter kicked in so say so
            loginf("wdwusource",
                   "Tried to make a WU API call within %d sec of the previous call." % (self.lockout_period,))
            loginf("        ",
                   "WU API call limit reached. API call skipped.")
        return None

    def parse_raw_data(self, response):
        """ Parse a WU API forecast response and return the forecast text.

        The WU API forecast response contains a number of forecast texts, the
        three main ones are:

        - the full day narrative
        - the day time narrative, and
        - the night time narrative.

        WU claims that night time is for 7pm to 7am and day time is for 7am to
        7pm though anecdotally it appears that the day time forecast disappears
        late afternoon and reappears early morning. If day-night forecast text
        is selected we will look for a day time forecast up until 7pm with a
        fallback to the night time forecast. From 7pm to midnight the nighttime
        forecast will be used. If day forecast text is selected then we will
        use the higher level full day forecast text.

        Input:
            response: A WU API response in JSON format.

        Returns:
            The selected forecast text if it exists otherwise None.
        """

        _text = None
        _icon = None
        # deserialize the response but be prepared to catch an exception if the
        # response can't be deserialized
        try:
            _response_json = json.loads(response)
        except ValueError:
            # can't deserialize the response so log it and return None
            loginf("wdwusource",
                   "Unable to deserialise Weather Underground forecast response")

        # forecast data has been deserialized so check which forecast narrative
        # we are after and locate the appropriate field.
        if self.forecast_text == 'day':
            # we want the full day narrative, use a try..except in case the
            # response is malformed
            try:
                _text = _response_json['narrative'][0]
            except KeyError:
                # could not find the narrative so log and return None
                if self.debug > 0:
                    loginf("wdwusource", "Unable to locate 'narrative' field for "
                                         "'%s' forecast narrative" % self.forecast_text)
        else:
            # we want the day time or night time narrative, but which, WU
            # starts dropping the day narrative late in the afternoon and it
            # does not return until the early hours of the morning. If possible
            # use day time up until 7pm but be prepared to fall back to night
            # if the day narrative has disappeared. Use night narrative for 7pm
            # to 7am but start looking for day again after midnight.
            # get the current local hour
            _hour = datetime.datetime.now().hour
            # helper string for later logging
            if 7 <= _hour < 19:
                _period_str = 'daytime'
            else:
                _period_str = 'nighttime'
            # day_index is the index of the day time forecast for today, it
            # will either be 0 (ie the first entry) or None if today's day
            # forecast is not present. If it is None then the night time
            # forecast is used. Start by assuming there is no day forecast.
            day_index = None
            if _hour < 19:
                # it's before 7pm so use day time, first check if it exists
                try:
                    day_index = _response_json['daypart'][0]['dayOrNight'].index('D')
                except KeyError:
                    # couldn't find a key for one of the fields, log it and
                    # force use of night index
                    if self.debug > 0:
                        loginf("wdwusource", "Unable to locate 'dayOrNight' field for %s "
                                             "'%s' forecast narrative" % (_period_str,
                                                                          self.forecast_text))
                    day_index = None
                except ValueError:
                    # could not get an index for 'D', log it and force use of
                    # night index
                    if self.debug > 0:
                        loginf("wdwusource", "Unable to locate 'D' index for %s "
                                             "'%s' forecast narrative" % (_period_str,
                                                                          self.forecast_text))
                    day_index = None
            # we have a day_index but is it for today or some later day
            if day_index is not None and day_index <= 1:
                # we have a suitable day index so use it
                _index = day_index
            else:
                # no day index for today so try the night index
                try:
                    _index = _response_json['daypart'][0]['dayOrNight'].index('N')
                except KeyError:
                    # couldn't find a key for one of the fields, log it and
                    # return None
                    if self.debug > 0:
                        loginf("wdwusource", "Unable to locate 'dayOrNight' field for %s "
                                             "'%s' forecast narrative" % (_period_str,
                                                                          self.forecast_text))
                except ValueError:
                    # could not get an index for 'N', log it and return None
                    if self.debug > 0:
                        loginf("wdwusource", "Unable to locate 'N' index for %s "
                                             "'%s' forecast narrative" % (_period_str,
                                                                          self.forecast_text))
            # if we made it here we have an index to use so get the required
            # narrative
            try:
                _text = _response_json['daypart'][0]['narrative'][_index]
                _icon = _response_json['daypart'][0]['iconCode'][_index]
            except KeyError:
                # if we can'f find a field log the error and return None
                if self.debug > 0:
                    loginf("wdwusource", "Unable to locate 'narrative' field for "
                                         "'%s' forecast narrative" % self.forecast_text)
            except ValueError:
                # if we can'f find an index log the error and return None
                if self.debug > 0:
                    loginf("wdwusource", "Unable to locate 'narrative' index for "
                                         "'%s' forecast narrative" % self.forecast_text)

            if _text is not None or _icon is not None:
                return {'forecastIcon': _icon,
                        'forecastText': _text}
            else:
                return None


# ============================================================================
#                    class WeatherUndergroundAPIForecast
# ============================================================================


class WeatherUndergroundAPIForecast(object):
    """Obtain a forecast from the Weather Underground API.

    The WU API is accessed by calling one or more features. These features can
    be grouped into two groups, WunderMap layers and data features. This class
    supports access to the API data features only.

    WeatherUndergroundAPI constructor parameters:

        api_key: WeatherUnderground API key to be used.

    WeatherUndergroundAPI methods:

        data_request. Submit a data feature request to the WeatherUnderground
                      API and return the response.
    """

    BASE_URL = 'https://api.weather.com/v3/wx/forecast/daily'

    def __init__(self, api_key, debug=0):
        # initialise a WeatherUndergroundAPIForecast object

        # save the API key to be used
        self.api_key = api_key
        # save debug level
        self.debug = debug

    def forecast_request(self, locator, location, forecast='5day', units='m',
                         language='en-GB', format='json', max_tries=3):
        """Make a forecast request via the API and return the results.

        Construct an API forecast call URL, make the call and return the
        response.

        Parameters:
            forecast:  The type of forecast required. String, must be one of
                       '3day', '5day', '7day', '10day' or '15day'.
            locator:   Type of location used. String. Must be a WU API supported
                       location type.
                       Refer https://docs.google.com/document/d/1RY44O8ujbIA_tjlC4vYKHKzwSwEmNxuGw5sEJ9dYjG4/edit#
            location:  Location argument. String.
            units:     Units to use in the returned data. String, must be one
                       of 'e', 'm', 's' or'h'.
                       Refer https://docs.google.com/document/d/13HTLgJDpsb39deFzk_YCQ5GoGoZCO_cRYzIxbwvgJLI/edit#heading=h.k9ghwen9fj7l
            language:  Language to return the response in. String, must be one
                       of the WU API supported language_setting codes
                       (eg 'en-US', 'es-MX', 'fr-FR').
                       Refer https://docs.google.com/document/d/13HTLgJDpsb39deFzk_YCQ5GoGoZCO_cRYzIxbwvgJLI/edit#heading=h.9ph8uehobq12
            format:    The output format_setting of the data returned by the WU
                       API. String, must be 'json' (based on WU API
                       documentation JSON is the only confirmed supported
                       format_setting.
            max_tries: The maximum number of attempts to be made to obtain a
                       response from the WU API. Default is 3.

        Returns:
            The WU API forecast response in JSON format_setting.
        """

        # construct the locator setting
        location_setting = '='.join([locator, location])
        # construct the units_setting string
        units_setting = '='.join(['units', units])
        # construct the language_setting string
        language_setting = '='.join(['language', language])
        # construct the format_setting string
        format_setting = '='.join(['format', format])
        # construct API key string
        api_key = '='.join(['apiKey', self.api_key])
        # construct the parameter string
        parameters = '&'.join([location_setting, units_setting,
                               language_setting, format_setting, api_key])

        # construct the base forecast url
        f_url = '/'.join([self.BASE_URL, forecast])

        # finally construct the full URL to use
        url = '?'.join([f_url, parameters])

        # if debug >=1 log the URL used but obfuscate the API key
        if weewx.debug >= 1:
            _obf_api_key = '='.join(['apiKey',
                                     '*'*(len(self.api_key) - 4) + self.api_key[-4:]])
            _obf_parameters = '&'.join([location_setting, units_setting,
                                        language_setting, format_setting,
                                        _obf_api_key])
            _obf_url = '?'.join([f_url, _obf_parameters])
            if weewx.debug > 0 or self.debug > 0:
                loginf("wuapiforecast",
                       "Submitting Weather Underground API call using URL: %s" % (_obf_url, ))
        # we will attempt the call max_tries times
        for count in range(max_tries):
            # attempt the call
            try:
                w = urllib2.urlopen(url)
                _response = w.read()
                w.close()
                return _response
            except (urllib2.URLError, socket.timeout), e:
                logerr("wuapiforecast",
                       "Failed to get Weather Underground forecast on attempt %d" % (count+1, ))
                logerr("wuapiforecast", "   **** %s" % e)
        else:
            logerr("wuapiforecast", "Failed to get Weather Underground forecast")
        return None


# ============================================================================
#                           class DarkSkySource
# ============================================================================


class DarkSkySource(ThreadedSource):
    """Thread that obtains Dark Sky data and places it in a queue.

    The DarkskyThread class queries the Darksky API and places selected data in
    JSON format in a queue used by the data consumer. The Dark Sky API is
    called at a user selectable rate. The thread listens for a shutdown signal
    from its parent.

    DarkskyThread constructor parameters:

        control_queue:       A Queue object used by our parent to control
                             (shutdown) this thread.
        result_queue:        A Queue object used to pass forecast data to the
                             destination
        engine:              A weewx.engine.StdEngine object
        source_config_dict:  A source config dictionary.

    DarkskyThread methods:

        run:            Control querying of the API and monitor the control
                        queue.
        get_raw_data:   Query the API and put selected forecast data in the
                        result queue.
        parse_raw_data: Parse a Darksky API response and return selected data.
    """

    # list of valid unit codes
    VALID_UNITS = ['auto', 'ca', 'uk2', 'us', 'si']

    # list of valid language codes
    VALID_LANGUAGES = ('ar', 'az', 'be', 'bg', 'bs', 'ca', 'cs', 'da', 'de',
                       'el', 'en', 'es', 'et', 'fi', 'fr', 'hr', 'hu', 'id',
                       'is', 'it', 'ja', 'ka', 'ko', 'kw', 'nb', 'nl', 'pl',
                       'pt', 'ro', 'ru', 'sk', 'sl', 'sr', 'sv', 'tet', 'tr',
                       'uk', 'x-pig-latin', 'zh', 'zh-tw')

    # default forecast block to be used
    DEFAULT_BLOCK = 'daily'

    def __init__(self, control_queue, result_queue, engine, source_config_dict):

        # initialize my base class:
        super(DarkSkySource, self).__init__(control_queue, result_queue,
                                            engine, source_config_dict)

        # set thread name
        self.setName('WdDarkSkyThread')

        # DarkSkySource debug level
        self.debug = to_int(source_config_dict.get('debug', 0))

        # are we providing forecast data as well as current conditions data
        self.do_forecast = to_bool(source_config_dict.get('forecast', True))

        # Dark Sky uses lat, long to 'locate' the forecast. Check if lat and
        # long are specified in the source_config_dict, if not use station lat
        # and long.
        latitude = source_config_dict.get("latitude", engine.stn_info.latitude_f)
        longitude = source_config_dict.get("longitude", engine.stn_info.longitude_f)

        # interval between API calls
        self.interval = to_int(source_config_dict.get('interval', 1800))
        # max no of tries we will make in any one attempt to contact the API
        self.max_tries = to_int(source_config_dict.get('max_tries', 3))
        # Get API call lockout period. This is the minimum period between API
        # calls for the same feature. This prevents an error condition making
        # multiple rapid API calls and thus breac the API usage conditions.
        self.lockout_period = to_int(source_config_dict.get('api_lockout_period',
                                                            60))
        # initialise container for timestamp of last API call
        self.last_call_ts = None
        # Get our API key from weewx.conf, first look in [RealtimeGaugeData]
        # [[WU]] and if no luck try [Forecast] if it exists. Wrap in a
        # try..except loop to catch exceptions (ie one or both don't exist.
        key = source_config_dict.get('api_key', None)
        if key is None:
            raise MissingApiKey("Cannot find valid Dark Sky key")
        # get a DarkskyForecastAPI object to handle the API calls
        self.api = DarkskyForecastAPI(key, latitude, longitude, self.debug)
        # get units to be used in forecast text
        _units = source_config_dict.get('units', 'ca').lower()
        # validate units
        self.units = _units if _units in self.VALID_UNITS else 'ca'
        # get language to be used in forecast text
        _language = source_config_dict.get('language', 'en').lower()
        # validate language
        self.language = _language if _language in self.VALID_LANGUAGES else 'en'
        # get the Darksky block to be used, default to our default
        self.block = source_config_dict.get('block', self.DEFAULT_BLOCK).lower()

        # log what we will do
        if self.do_forecast:
            loginf("wddarkskysource",
                   "Dark Sky API will be used for current conditions and forecast data")
        else:
            loginf("wddarkskysource",
                   "Dark Sky API will be used for current conditions data only")
        if self.debug > 0:
            loginf("wddarkskysource",
                   "interval=%s lockout period=%s max tries=%s" % (self.interval,
                                                                   self.lockout_period,
                                                                   self.max_tries))
            loginf("wddarkskysource", "units=%s language=%s block=%s" % (self.units,
                                                                         self.language,
                                                                         self.block))
            loginf("wddarkskysource", "Dark Sky debug=%s" % self.debug)

    def get_raw_data(self):
        """If required query the Darksky API and return the JSON response.

        Checks to see if it is time to query the API, if so queries the API
        and returns the raw response in JSON format. To prevent the user
        exceeding their API call limit the query is only made if at least
        self.lockout_period seconds have elapsed since the last call.

        Inputs:
            None.

        Returns:
            The Darksky API response in JSON format or None if no/invalid
            response was obtained.
        """

        # get the current time
        now = time.time()
        if self.debug > 0:
            loginf("wddarkskysource",
                   "Last Dark Sky API call at %s" % weeutil.weeutil.timestamp_to_string(self.last_call_ts))
        # has the lockout period passed since the last call
        if self.last_call_ts is None or ((now + 1 - self.lockout_period) >= self.last_call_ts):
            # If we haven't made an API call previously or if its been too long
            # since the last call then make the call
            if (self.last_call_ts is None) or ((now + 1 - self.interval) >= self.last_call_ts):
                # Make the call, wrap in a try..except just in case
                try:
                    _response = self.api.get_data(block=self.block,
                                                  language=self.language,
                                                  units=self.units,
                                                  max_tries=self.max_tries)
                    if self.debug > 0:
                        if _response is not None:
                            loginf("wddarkskysource",
                                   "Downloaded Dark Sky API response")
                        else:
                            loginf("wddarkskysource",
                                   "Failed downloading Dark Sky API response")

                except Exception, e:
                    # Some unknown exception occurred. Set _response to None,
                    # log it and continue.
                    _response = None
                    loginf("wddarkskysource",
                           "Unexpected exception of type %s" % (type(e),))
                    weeutil.weeutil.log_traceback('wddarkskysource: **** ')
                    loginf("wddarkskysource",
                           "Unexpected exception of type %s" % (type(e),))
                    loginf("wddarkskysource", "Dark Sky API call failed")
                # if we got something back then reset our last call timestamp
                if _response is not None:
                    self.last_call_ts = now
                return _response
        else:
            # API call limiter kicked in so say so
            loginf("wddarkskysource",
                   "Tried to make an Dark Sky API call within %d sec of the previous call." % (self.lockout_period,))
            loginf("        ",
                   "Dark Sky API call limit reached. API call skipped.")
        return None

    def parse_raw_data(self, raw_data):
        """Parse a Darksky raw data.

        Take a Darksky raw_data, check for (Darksky defined) errors then
        extract and return the required data.

        Input:
            raw_data: Darksky API response raw data in JSON format.

        Returns:
            Summary text or None.
        """

        _forecast = None
        _forecast_icon = None
        _current = None
        _current_icon = None
        # There is not too much validation of the data we can do other than
        # looking at the 'flags' object
        if 'flags' in raw_data:
            if 'darksky-unavailable' in raw_data['flags']:
                loginf("wddarkskysource",
                       "Dark Sky data for this location temporarily unavailable")
        else:
            loginf("wddarkskysource", "No flag object in Dark Sky API raw data.")

        # get the summary data to be used
        # is our block available, can't assume it is
        if self.block in raw_data:
            # we have our block, but is the summary there
            if 'summary' in raw_data[self.block]:
                # we have a summary field
                _forecast = raw_data[self.block]['summary'].encode('ascii', 'ignore')
            else:
                # we have no summary field, so log it and return None
                if self.debug > 0:
                    loginf("wddarkskysource", "Summary data not available "
                                              "for '%s' forecast" % (self.block,))
        else:
            if self.debug > 0:
                loginf("wddarkskysource",
                       "Dark Sky %s block not available" % self.block)
        # get the current data and icon
        # is the 'currently' block available, can't assume it is
        if 'currently' in raw_data:
            # we have our currently block, but is the summary there
            if 'summary' in raw_data['currently']:
                # we have a summary field
                _current = raw_data['currently']['summary'].encode('ascii', 'ignore')
            else:
                # we have no summary field, so log it and return None
                if self.debug > 0:
                    loginf("wddarkskysource",
                           "Summary data not available for 'currently' block")
        else:
            if self.debug > 0:
                loginf("wddarkskysource",
                       "Dark Sky 'currently' block not available")

        if _forecast is not None or _forecast_icon is not None:
            return {'forecastIcon': _forecast_icon,
                    'forecastText': _forecast,
                    'currentIcon': _current_icon,
                    'currentText': _current}
        else:
            return None


# ============================================================================
#                         class DarkskyForecastAPI
# ============================================================================


class DarkskyForecastAPI(object):
    """Query the Darksky API and return the API response.

    DarkskyForecastAPI constructor parameters:

        darksky_config_dict: Dictionary keyed as follows:
            key:       Darksky secret key to be used
            latitude:  Latitude of the location concerned
            longitude: Longitude of the location concerned

    DarkskyForecastAPI methods:

        get_data. Submit a data request to the Darksky API and return the
                  response.

        _build_optional: Build a string containing the optional parameters to
                         submitted as part of the API request URL.

        _hit_api: Submit the API request and capture the response.

        obfuscated_key: Property to return an obfuscated secret key.
    """

    # base URL from which to construct an API call URL
    BASE_URL = 'https://api.darksky.net/forecast'
    # blocks we may want to exclude, note we need 'currently' for current
    # conditions
    BLOCKS = ('minutely', 'hourly', 'daily', 'alerts')

    def __init__(self, key, latitude, longitude, debug=0):
        # initialise a DarkskyForecastAPI object

        # save the secret key to be used
        self.key = key
        # save lat and long
        self.latitude = latitude
        self.longitude = longitude
        # save DS debug level
        self.debug = debug

    def get_data(self, block='hourly', language='en', units='auto',
                 max_tries=3):
        """Make a data request via the API and return the response.

        Construct an API call URL, make the call and return the response.

        Parameters:
            block:     Darksky block to be used. None or list of strings, default is None.
            language:  The language to be used in any response text. Refer to
                       the optional parameter 'language' at
                       https://darksky.net/dev/docs. String, default is 'en'.
            units:     The units to be used in the response. Refer to the
                       optional parameter 'units' at https://darksky.net/dev/docs.
                       String, default is 'auto'.
            max_tries: The maximum number of attempts to be made to obtain a
                       response from the API. Number, default is 3.

        Returns:
            The Darksky API response in JSON format.
        """

        # start constructing the API call URL to be used
        url = '/'.join([self.BASE_URL,
                        self.key,
                        '%s,%s' % (self.latitude, self.longitude)])

        # now build the optional parameters string
        optional_string = self._build_optional(block=block,
                                               language=language,
                                               units=units)
        # if it has any content then add it to the URL
        if len(optional_string) > 0:
            url = '?'.join([url, optional_string])

        # if debug >= 1 log the URL used but obfuscate the key
        if weewx.debug > 0 or self.debug > 0:
            _obfuscated_url = '/'.join([self.BASE_URL,
                                        self.obfuscated_key,
                                        '%s,%s' % (self.latitude, self.longitude)])
            _obfuscated_url = '?'.join([_obfuscated_url, optional_string])
            loginf("wddarkskyapi",
                   "Submitting API call using URL: %s" % (_obfuscated_url,))
        # make the API call
        _response = self._hit_api(url, max_tries)
        # if we have a response we need to deserialise it
        json_response = json.loads(_response) if _response is not None else None
        # return the response
        return json_response

    def _build_optional(self, block='hourly', language='en', units='auto'):
        """Build the optional parameters string."""

        # initialise a list of non-None optional parameters and their values
        opt_params_list = []
        # exclude all but our block
        _blocks = [b for b in self.BLOCKS if b != block]
        opt_params_list.append('exclude=%s' % ','.join(_blocks))
        # language
        if language is not None:
            opt_params_list.append('lang=%s' % language)
        # units
        if units is not None:
            opt_params_list.append('units=%s' % units)
        # now if we have any parameters concatenate them separating each with
        # an ampersand
        opt_params = "&".join(opt_params_list)
        # return the resulting string
        return opt_params

    def _hit_api(self, url, max_tries=3):
        """Make the API call and return the result."""

        # we will attempt the call max_tries times
        for count in range(max_tries):
            # attempt the call
            try:
                w = urllib2.urlopen(url)
                response = w.read()
                w.close()
                if self.debug > 1:
                    loginf("wddarkskyapi",
                           "Dark Sky API response=%s" % (response, ))
                return response
            except (urllib2.URLError, socket.timeout), e:
                logerr("wddarkskyapi",
                       "Failed to get API response on attempt %d" % (count + 1,))
                logerr("wddarkskyapi", "   **** %s" % e)
        else:
            logerr("wddarkskyapi", "Failed to get API response")
        return None

    @property
    def obfuscated_key(self):
        """Produce and obfuscated copy of the key."""

        # replace all characters in the key with an asterisk except for the
        # last 4
        return '*' * (len(self.key) - 4) + self.key[-4:]


# ==============================================================================
#                                   Utilities
# ==============================================================================


def toint(string, default):
    """Convert a string to an integer whilst handling None and a default.

        If string cannot be converted to an integer default is returned.

        Input:
            string:  The value to be converted to an integer
            default: The value to be returned if value cannot be converted to
                     an integer
    """

    # is string None or do we have a string and is it some variation of 'None'
    if string is None or (isinstance(string, str) and string.lower() == 'none'):
        # we do so our result will be None
        return None
    # otherwise try to convert it
    else:
        try:
            return int(string)
        except ValueError:
            # we can't convert it so our result will be the default
            return default


def calc_day_night(data_dict):
    """ 'Calculate' value for outTempDay and outTempNight.

        outTempDay and outTempNight are used to determine warmest night
        and coldest day stats. This is done by using two derived
        observations; outTempDay and outTempNight. These observations
        are defined as follows:

        outTempDay:   equals outTemp if time of day is > 06:00 and <= 18:00
                      otherwise it is None
        outTempNight: equals outTemp if time of day is > 18:00 or <= 06:00
                      otherwise it is None

        By adding these derived obs to the schema and loop packet the daily
        summaries for these obs are populated and aggregate stats can be
        accessed as per normal (eg $month.outTempDay.minmax to give the
        coldest max daytime temp in the month). Note that any aggregates that
        rely on the number of records (eg avg) will be meaningless due to
        the way outTempxxxx is calculated.
    """

    if 'outTemp' in data_dict:
        # check if record covers daytime (6AM to 6PM) and if so make field
        # 'outTempDay' = field 'outTemp' otherwise make field 'outTempNight' =
        # field 'outTemp', remember record timestamped 6AM belongs in the night
        # time
        _hour = datetime.fromtimestamp(data_dict['dateTime'] - 1).hour
        if _hour < 6 or _hour > 17:
            # ie the data packet is from before 6am or after 6pm
            return None, data_dict['outTemp']
        else:
            # ie the data packet is from after 6am and before or including 6pm
            return data_dict['outTemp'], None
    else:
        return None, None


def check_enable(cfg_dict, service, *args):

    try:
        wdsupp_dict = accumulateLeaves(cfg_dict[service], max_level=1)
    except KeyError:
        logdbg2("weewxwd: check_enable:",
                "%s: No config info. Skipped." % service)
        return None

    # check to see whether all the needed options exist, and none of them have
    # been set to 'replace_me'
    try:
        for option in args:
            if wdsupp_dict[option] == 'replace_me':
                raise KeyError(option)
    except KeyError, e:
        logdbg2("weewxwd: check_enable:",
                "%s: Missing option %s" % (service, e))
        return None

    return wdsupp_dict


# ============================================================================
#                          Main Entry for Testing
# ============================================================================
"""
Define a main entry point for basic testing without the WeeWX engine and 
services overhead. To invoke this module without WeeWX:

    $ sudo PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/weewxwd.py --option

    where option is one of the following options:
        --help               - display command line help
        --version            - display version
        --get-wu-api-data    - display WU API data
        --get-wu-api-config  - display WU API config parameters to be used 
"""

if __name__ == '__main__':

    # python imports
    import optparse
    import pprint
    import sys

    # WeeWX imports
    import weecfg

    usage = """sudo PYTHONPATH=/home/weewx/bin python
               /home/weewx/bin/user/%prog [--option]"""

    syslog.openlog('weewxwd', syslog.LOG_PID | syslog.LOG_CONS)
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--config', dest='config_path', type=str,
                      metavar="CONFIG_FILE",
                      help="Use configuration file CONFIG_FILE.")
    parser.add_option('--version', dest='version', action='store_true',
                      help='Display module version.')
    parser.add_option('--get-wu-api-data', dest='api_data', 
                      action='store_true',
                      help='Query WU API and display results.')
    parser.add_option('--get-wu-api-config', dest='api_config', 
                      action='store_true',
                      help='Query WU API and display results.')
    (options, args) = parser.parse_args()

    if options.version:
        print "weewxwd version %s" % WEEWXWD_VERSION
        exit(0)

    # get config_dict to use
    config_path, config_dict = weecfg.read_config(options.config_path, args)
    print "Using configuration file %s" % config_path

    # get a WeeWX-WD config dict
    weewxwd_dict = config_dict.get('Weewx-WD', None)
    
    # get a WuData object
    if weewxwd_dict is not None:
        wu_api = WuData(config_dict)
    else:
        exit_str = "'Weewx-WD' stanza not found in config file '%s'. Exiting." % config_path
        sys.exit(exit_str)
    
    if options.api_data:
        _result = wu_api.getWuApiData()
        print
        print "The following data was extracted from the Weather Underground API:"
        print
        pprint.pprint(_result)
        sys.exit(0)

    if options.api_config:
        print
        print "The following config data will be used to access the Weather Underground API:"
        print
        if wu_api.api_key is not None and wu_api.location is not None:
            print "API key: xxxxxxxxxxxx%s" % (wu_api.api_key[-4:],)
            print "Location: %s" % wu_api.location
        else:
            if wu_api.api_key is not None:
                print "API key: xxxxxxxxxxxx%s" % (wu_api.api_key[-4:],)
                print "Cannot find location."
            else:
                print "Cannot find valid Weather Underground API key."
                print "Location: %s" % wu_api.location
            print "Weather Underground API will not be accessed."
        sys.exit(0)

    # if we made it here display our help message

KNOWN_SOURCES = {'WU': WuSource,
                 'DS': DarkSkySource}
