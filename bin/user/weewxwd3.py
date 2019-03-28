# weewxwd3.py
#
# Service classes used by weeWX-WD
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
#  Version: 1.2.0                                      Date: 17 April 2018
#
#  Revision History
#   9 March 2018        v1.2.0
#       - revised for weeWX v3.5.0
#       - moved __main__ code to weewxwd_config utility
#       - now uses appTemp and humidex as provided by StdWXCalculate
#       - simplified WdWXCalculate.new_loop_packet,
#         WdWXCalculate.new_archive_record and WdArchive.new_archive_record
#         methods
#       - simplified outTempDay and outTempNight calculations
#       - simplified function toint()
#       - added support for a weeWX-WD supplementary database for recording 
#         short term information such as theoretical solar max, WU current 
#         conditions, WU forecast and WU almanac data
#       - added WU API language support
#       - added ability to exercise WU aspects of weewxwd3.py without the 
#         overheads of running a weeWX instance
#       - added current_label config option to allow a user defined label to be
#         prepended to the current conditions text
#
# Previous Bitbucket revision history
#   31 March 2017       v1.0.3
#       - no change, version number change only
#   14 December 2016    v1.0.2
#       - no change, version number change only
#   30 November 2016    v1.0.1
#       - now uses humidex and appTemp formulae from weewx.wxformulas
#       - weeWX-WD db management functions moved to wd_database utility
#       - implemented syslog wrapper functions
#       - minor reformatting
#       - replaced calls to superseded DBBinder.get_database method with
#         DBBinder.get_manager method
#       - removed database management utility functions and placed in new
#         wd_database utility
#   10 January 2015     v1.0.0
#       - rewritten for weeWX v3.0
#       - uses separate database for weeWX-WD specific data, no longer
#         recycles existing weeWX database fields
#       - added __main__ to allow command line execution of a number of db
#         management actions
#       - removed --debug option from main()
#       - added --create_archive option to main() to create the weewxwd
#         database
#       - split --backfill_daily into separate --drop_daily and
#         --backfill_daily options
#       - added 'user.' to all weeWX-WD imports
#   18 September 2014   v0.9.4 (never released)
#       - added GNU license text
#   18 May 2014         v0.9.2
#       - removed code that set windDir/windGustDir to 0 if windDir/windGustDir
#         were None respectively
#   30 July 2013        v0.9.1
#       - revised version number to align with weeWX-WD version numbering
#   20 July 2013        v0.1
#       - initial implementation
#

# python imports
import syslog
import threading
import urllib2
import json
import math
import time
from datetime import datetime

# weeWX imports
import weeutil.weeutil
import weewx
import weewx.almanac
import weewx.engine
import weewx.manager
import weewx.units
import weewx.wxformulas

from weewx.units import convert, obs_group_dict
from weeutil.weeutil import to_bool, accumulateLeaves

WEEWXWD_VERSION = '1.2.0'

# Define a dictionary with our API call query details
WU_queries = [
    {
        'name': 'conditions',
        'interval': None,
        'last': None,
        'def_interval': 1800,
        'response': None,
        'json_title': 'current_observation'
    },
    {
        'name': 'forecast',
        'interval': None,
        'last': None,
        'def_interval': 1800,
        'response': None,
        'json_title': 'forecast'
    },
    {
        'name': 'almanac',
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


def logmsg(level, src, msg):
    syslog.syslog(level, '%s %s' % (src, msg))


def logdbg(src, msg):
    logmsg(syslog.LOG_DEBUG, src, msg)


def logdbg2(src, msg):
    if weewx.debug >= 2:
        logmsg(syslog.LOG_DEBUG, msg)


def loginf(src, msg):
    logmsg(syslog.LOG_INFO, src, msg)


def logerr(src, msg):
    logmsg(syslog.LOG_ERR, src, msg)


# ===============================================================================
#                            Class WdWXCalculate
# ===============================================================================


class WdWXCalculate(weewx.engine.StdService):
    """Service to calculate weeWX-WD specific observations."""

    def __init__(self, engine, config_dict):
        # initialise our parent
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


# ===============================================================================
#                              Class WdArchive
# ===============================================================================


class WdArchive(weewx.engine.StdService):
    """Service to store Weewx-WD specific archive data."""

    def __init__(self, engine, config_dict):
        # initialise our parent
        super(WdArchive, self).__init__(engine, config_dict)

        # Extract our binding from the weeWX-WD section of the config file. If
        # it's missing, fill with a default.
        if 'WeewxWD' in config_dict:
            self.data_binding = config_dict['WeewxWD'].get('data_binding',
                                                           'wd_binding')
        else:
            self.data_binding = 'wd_binding'
        loginf("WdArchive:",
               "WdArchive will use data binding %s" % self.data_binding)

        # extract the weeWX binding for use when we check the need for backfill
        # from the weeWX archive
        if 'StdArchive' in config_dict:
            self.data_binding_wx = config_dict['StdArchive'].get('data_binding',
                                                                 'wx_binding')
        else:
            self.data_binding_wx = 'wx_binding'

        # setup our database if needed
        self.setup_database(config_dict)

        # set the unit groups for our obs
        obs_group_dict["humidex"] = "group_temperature"
        obs_group_dict["appTemp"] = "group_temperature"
        obs_group_dict["outTempDay"] = "group_temperature"
        obs_group_dict["outTempNight"] = "group_temperature"

        # bind ourselves to NEW_ARCHIVE_RECORD event
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_archive_record(self, event):
        """Save the weeWX-WD archive record.

           Use our db manager's addRecord method to save the relevant weeWX-WD
           fields to the weeWX-WD archive.
        """

        # get our db manager
        dbmanager = self.engine.db_binder.get_manager(self.data_binding)
        # now put the record in the archive
        dbmanager.addRecord(event.record)

    def setup_database(self, config_dict):
        """Setup the weeWX-WD database.e"""

        # create the database if it doesn't exist and a db manager for the
        # opened database
        dbmanager = self.engine.db_binder.get_manager(self.data_binding,
                                                      initialize=True)
        loginf("WdArchive:",
               "Using binding '%s' to database '%s'" % (self.data_binding,
                                                        dbmanager.database_name))

        # FIXME. Is this still required
        # Check if we have any historical data to bring in from the weeWX
        # archive.
        # first get a dbmanager for the weeWX archive
        dbmanager_wx = self.engine.db_binder.get_manager(self.data_binding_wx,
                                                         initialize=False)

        # then backfill the weeWX-WD daily summaries
        loginf("WdArchive:", "Starting backfill of daily summaries")
        t1 = time.time()
        nrecs, ndays = dbmanager.backfill_day_summary()
        tdiff = time.time() - t1
        if nrecs:
            loginf("WdArchive:",
                   "Processed %d records to backfill %d day summaries in %.2f seconds" % (nrecs,
                                                                                          ndays,
                                                                                          tdiff))
        else:
            loginf("WdArchive:", "Daily summaries up to date.")


# ===============================================================================
#                           Class WdGenerateDerived
# ===============================================================================


class WdGenerateDerived(object):
    """ Adds weeWX-WD derived obs to the output of the wrapped generator."""

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


# ===============================================================================
#                             Class wdSuppThread
# ===============================================================================


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


# ===============================================================================
#                            Class WdSuppArchive
# ===============================================================================


class WdSuppArchive(weewx.engine.StdService):
    """Service to archive weeWX-WD supplementary data.


        Collects and archives WU API sourced data, Davis console forecast/storm 
        data and theoretical max solar radiation data in the weeWX-WD supp 
        database. Data is only kept for a limited time before being dropped.
    """

    def __init__(self, engine, config_dict):
        # initialise our parent
        super(WdSuppArchive, self).__init__(engine, config_dict)

        # Initialisation is 2 part; 1 part for wdsupp db/loop data, 2nd part
        # for WU API calls. We are only going to invoke ourself if we have the
        # necessary config data available in weewx.conf for 1 or both parts.
        # If any essential config data is missing/not set then give a short log
        # message and defer.

        if 'Weewx-WD' in config_dict:
            # we have a [Weewx-WD} stanza
            if 'Supplementary' in config_dict['Weewx-WD']:
                # we have a [[Supplementary]] stanza so we can initialise
                # wdsupp db
                _supp_dict = config_dict['Weewx-WD']['Supplementary']
                
                # setup for archiving of supp data
                # first, get our binding, if it's missing use a default
                self.binding = _supp_dict.get('data_binding',
                                              'wdsupp_binding')
                loginf("WdSuppArchive:",
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
                self.setup_database(config_dict)
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
                loginf("WdSuppArchive:", "max_age=%s vacuum=%s" % (self.max_age,
                                                                   self.vacuum))
                
                # do we have necessary config info for WU ie a [[[WU]]] stanza,
                # apiKey and location
                _wu_dict = check_enable(_supp_dict, 'WU', 'apiKey')
                if _wu_dict is None:
                    # we are missing some/all essential WU API settings so set a
                    # flag and return
                    self.do_WU = False
                    loginf("WdSuppArchive:", "WU API calls will not be made")
                    loginf("              ", "**** Incomplete or missing config settings")
                    return

                # setup for WU API queries
                
                # get a WuApiQuery object to handle WU API queries
                self.wu_api_query_obj = WuApiQuery(config_dict)


    def new_archive_record(self, event):
        """Kick off in a new thread."""

        t = wdSuppThread(self.wdSupp_main, event)
        t.setName('wdSuppThread')
        t.start()

    def wdSupp_main(self, event):
        """ Take care of getting our data, archiving it and completing any
            database housekeeping.

            Let a WuApiQuery object handle any WU API calls. Grab any 
            forecast/storm loop data and theoretical max solar radiation. 
            Archive our data, delete any stale records and 'vacuum' the 
            database if required.
        """

        # get time now as a ts
        now = time.time()

        # create a holder for our data record
        _rec = {}
        # prepopulate our data record with a few things we may know now
        _rec['dateTime'] = event.record['dateTime']
        _rec['usUnits'] = event.record['usUnits']
        _rec['interval'] = event.record['interval']
        # get any WU API data
        _wu_data = self.wu_api_query_obj.getWuApiData(event)
        # now update out data record with any WU data
        _rec.update(_wu_data)
        # process data from latest loop packet
        _packet = self.process_loop()
        # update our data record with any loop data
        _rec.update(_packet)

        # get a db manager dict
        dbm_dict = weewx.manager.get_manager_dict_from_config(self.config_dict,
                                                              self.binding)
        # now save the data
        with weewx.manager.open_manager(dbm_dict) as dbm:
            # save the record
            self.save_record(dbm, _rec, self.db_max_tries, self.db_retry_wait)
            # set ts of last packet processed
            self.last_ts = _rec['dateTime']
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

    def process_loop(self):
        """ Process latest loop data and populate fields as appropriate.

            Adds following fields (if available) to data dictionary:
                - forecast icon (Vantage only)
                - forecast rule (Vantage only)(Note returns full text forecast)
                - stormRain (Vantage only)
                - stormStart (Vantage only)
                - current theoretical max solar radiation
        """

        # holder dictionary for our gathered data
        _data = {}
        # vantage forecast icon
        if 'forecastIcon' in self.loop_packet:
            _data['vantageForecastIcon'] = self.loop_packet['forecastIcon']
        # vantage forecast rule
        if 'forecastRule' in self.loop_packet:
            try:
                _data['vantageForecastRule'] = davis_fr_dict[self.loop_packet['forecastRule']]
            except KeyError:
                _data['vantageForecastRule'] = ""
                logdbg2("WdSuppArchive:",
                        "Could not decode Vantage forecast code")
        # vantage stormRain
        if 'stormRain' in self.loop_packet:
            _data['stormRain'] = self.loop_packet['stormRain']
        # vantage stormStart
        if 'stormStart' in self.loop_packet:
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
                logerr("WdSuppArchive:",
                       "save failed (attempt %d of %d): %s" % ((count + 1),
                                                               max_tries, e))
                logerr("WdSuppArchive:",
                       "waiting %d seconds before retry" % (retry_wait, ))
                time.sleep(retry_wait)
        else:
            raise Exception("save failed after %d attempts" % max_tries)

    @staticmethod
    def prune(dbm, ts, max_tries = 3, retry_wait = 2):
        """Remove records older than ts from the database."""

        sql = "delete from %s where dateTime < %d" % (dbm.table_name, ts)
        for count in range(max_tries):
            try:
                dbm.getSql(sql)
                break
            except Exception, e:
                logerr("WdSuppArchive:",
                       "prune failed (attempt %d of %d): %s" % ((count+1),
                                                                max_tries, e))
                logerr("WdSuppArchive:",
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
        #do the vacuum, wrap in try..except in case it fails
        try:
            dbm.getSql('vacuum')
        except Exception, e:
            logerr("WdSuppArchive:",
                   "Vacuuming database % failed: %s" % (dbm.database_name, e))

        t2 = time.time()
        logdbg("WdSuppArchive:",
               "vacuum_database executed in %0.9f seconds" % (t2-t1))

    def setup_database(self, config_dict):
        """Setup the database table we will be using."""

        # This will create the database and/or table if either doesn't exist,
        # then return an opened instance of the database manager.
        dbmanager = self.engine.db_binder.get_database(self.binding,
                                                       initialize=True)
        loginf("WdSuppArchive:",
               "Using binding '%s' to database '%s'" % (self.binding,
                                                        dbmanager.database_name))

    def new_loop_packet(self, event):
        """ Save Davis Console forecast data that arrives in loop packets so
            we can save it to archive later.

            The Davis Console forecast data is published in each loop packet.
            There is little benefit in saving this data to database each loop
            period as the data is slow changing so we will stash the data and
            save to database each archive period along with our WU sourced data.
        """

        # update stashed loop packet data, wrap in a try..except just in case
        try:
            if 'forecastIcon' in event.packet:
                self.loop_packet['forecastIcon'] = event.packet['forecastIcon']
            else:
                self.loop_packet['forecastIcon'] = None
            if 'forecastRule' in event.packet:
                self.loop_packet['forecastRule'] = event.packet['forecastRule']
            else:
                self.loop_packet['forecastRule'] = None
            if 'stormRain' in event.packet:
                self.loop_packet['stormRain'] = event.packet['stormRain']
            else:
                self.loop_packet['stormRain'] = None
            if 'stormStart' in event.packet:
                self.loop_packet['stormStart'] = event.packet['stormStart']
            else:
                self.loop_packet['stormStart'] = None
            if 'maxSolarRad' in event.packet:
                self.loop_packet['maxSolarRad'] = event.packet['maxSolarRad']
            else:
                self.loop_packet['maxSolarRad'] = None
        except:
            loginf("WdSuppArchive:",
                   "new_loop_packet: Loop packet data error. Cannot decode packet.")

    def shutDown(self):
        pass


# ===============================================================================
#                            Class WuApiQuery
# ===============================================================================


class WuApiQuery():
    """Class to query the WeatherUnderground API.


        Calling the getWuApiData() method returns a data record of selected WU
        API data.
    """

    def __init__(self, config_dict):

        if 'Weewx-WD' in config_dict:
            # we have a [Weewx-WD] stanza so get the supp dict
            _supp_dict = config_dict['Weewx-WD'].get('Supplementary')

            # Do we have necessary config info for WU ie a [[[WU]]] stanza,
            # apiKey and location. If we were called from WdSuppArchive we 
            # probably do but we may have been called from main() so we need 
            # to check a couple of conditions.
            _wu_dict = check_enable(_supp_dict, 'WU', 'apiKey')
            if _wu_dict is None:
                self.do_WU = False
                # we are missing some/all essential WU API settings so set a
                # flag and return
                loginf("WuApiQuery:", "WU API calls will not be made")
                loginf("              ", "**** Incomplete or missing config settings")
                return

            # if we got this far we have the essential WU API settings so carry
            # on with the rest of the initialisation
            # set a flag indicating we are doing WU API queries
            self.do_WU = True
            # get station info required for almanac/Sun related calcs
            _stn_dict = config_dict.get('Station')
            self.latitude = float(_stn_dict.get('latitude'))
            self.longitude = float(_stn_dict.get('longitude'))
            altitude_t = weeutil.weeutil.option_as_list(_stn_dict.get('altitude', 
                                                        (None, None)))
            altitude_vt = weewx.units.ValueTuple(float(altitude_t[0]), 
                                                 altitude_t[1], 
                                                 "group_altitude")
            self.altitude = convert(altitude_vt, 'meter').value
            # create a list of the WU API calls we need
            self.WU_queries = WU_queries
            # set interval between API calls for each API call type we need
            for q in self.WU_queries:
                q['interval'] = int(_wu_dict.get('%s_interval' % q['name'],
                                                 q['def_interval']))
            # set max no of tries we will make in any one attempt to contact WU
            # via API
            self.max_WU_tries = _wu_dict.get('max_WU_tries', 3)
            self.max_WU_tries = toint(self.max_WU_tries, 3)
            # set API call lockout period in sec (default 60 sec)
            self.api_lockout_period = _wu_dict.get('api_lockout_period', 60)
            self.api_lockout_period = toint(self.api_lockout_period, 60)
            # create holder for last WU API call ts
            self.last_WU_query = None
            # Get our API key
            self.api_key = _wu_dict.get('apiKey')
            # get our 'location' for use in WU API calls. Default to station
            # lat/long.
            self.location = _wu_dict.get('location', '%s,%s' % (self.latitude,
                                                                self.longitude))
            if self.location == 'replace_me':
                self.location = '%s,%s' % (self.latitude, self.longitude)
            # get the language to use, must be one of the WU supported 
            # languages listed at 
            # https://www.wunderground.com/weather/api/d/docs?d=language-support&MR=1
            _language = _wu_dict.get('language', 'English')
            self.language = WU_languages.get(_language.lower(), 'EN')
            # get current condiitons text label
            self.current_label = _wu_dict.get('current_label', '')
            # set fixed part of WU API call url
            self.default_url = 'http://api.wunderground.com/api'
            # we have everything we need to put a short message in the log
            loginf("WuApiQuery:", "WU API calls will be made")
            _m = ["%s interval=%s" % (a['name'], a['interval']) for a in self.WU_queries]
            loginf("WuApiQuery:", " ".join(_m))
            loginf("WuApiQuery:",
                   "api_key=xxxxxxxxxxxx%s location=%s" % (self.api_key[-4:],
                                                           self.location))
            if self.language != 'EN':
                loginf("WuApiQuery:", 
                       "WU API results will use the %s language" % _language.title())

    def getWuApiData(self, event=None):
        """Make a WU API call and return a data dict."""

        if self.do_WU:
            # get time now as a ts
            now = time.time()
            # create a holder dict for our data record
            _rec = {}
        
            # almanac gives more accurate results with current temp and
            # pressure
            # first, initialise some defaults
            temperature_c = 15.0
            pressure_mbar = 1010.0
            _datetime = now
            if event:
                _datetime = event.record['dateTime']

                # get current outTemp and barometer if they exist
                if 'outTemp' in event.record:
                    temperature_c = weewx.units.convert(weewx.units.as_value_tuple(event.record, 'outTemp'),
                                                        "degree_C").value
                if 'barometer' in event.record:
                    pressure_mbar = weewx.units.convert(weewx.units.as_value_tuple(event.record, 'barometer'),
                                                        "mbar").value
            # get an almanac object
            _almanac = weewx.almanac.Almanac(_datetime,
                                             self.latitude,
                                             self.longitude,
                                             self.altitude,
                                             temperature_c,
                                             pressure_mbar)
            # Work out sunrise and sunset ts so we can determine if it is night
            # or day. Needed so we can set day or night icons when translating
            # WU icons to Saratoga icons
            sunrise_ts = _almanac.sun.rise.raw
            sunset_ts = _almanac.sun.set.raw
            # set the night flag
            self.night = not (sunrise_ts < _datetime < sunset_ts)
            # get the fully constructed URL for those API feature calls that
            # are to be made
            _wu_url, _features = self.construct_wu_url(now)
            _response = None
            if _wu_url is not None:
                if self.last_WU_query is None or ((now + 1 - self.api_lockout_period) >= self.last_WU_query):
                    # if we haven't made this API call previously or if its
                    # been too long since the last call then make the call,
                    # wrap in a try..except just in case
                    try:
                        _response = self.get_wu_response(_wu_url,
                                                         self.max_WU_tries)
                        _msg = "Downloaded updated Weather Underground information for %s" % (_features,)
                        logdbg2("getWuApiData:", _msg)
                    except Exception,e:
                        loginf("getWuApiData:",
                               "Weather Underground API query failure: %s" % e)
                    self.last_WU_query = max(q['last'] for q in self.WU_queries)
                else:
                    # API call limiter kicked in so say so
                    _msg = "API call limit reached. Tried to make an API call within %d sec of the previous call. API call skipped." % (self.api_lockout_period, )
                    loginf("getWuApiData:", _msg)
            # parse the WU responses and put into a dictionary
            _tgt_units = _rec['usUnits'] if 'usUnits' in _rec else weewx.METRIC
            _wu_record = self.parse_wu_response(_response, _tgt_units)
            # update the data record with any WU data
            _rec.update(_wu_record)
            # return the updated record
            return _rec

    def construct_wu_url(self, now):
        """ Construct a multi-feature WU API URL

            WU API allows multiple feature requests to be combined into a single
            http request (thus cutting down on API calls. Look at each of our WU
            queries then construct and return a WU API URL string that will
            request all features that are due. If no features are due then
            return None.
        """

        _feature_string = ''
        for _q in self.WU_queries:
            # if we haven't made this feature request previously or if its been
            # too long since the last call then make the call
            if (_q['last'] is None) or ((now + 1 - _q['interval']) >= _q['last']):
                # we need to request this feature so add the feature code to our
                # feature string
                if len(_feature_string) > 0:
                    _feature_string += '/' + _q['name']
                else:
                    _feature_string += _q['name']
                _q['last'] = now
        if len(_feature_string) > 0:
            # we have a feature we need so construct the URL
            url = '%s/%s/%s/lang:%s/pws:1/q/%s.json' % (self.default_url,
                                                        self.api_key,
                                                        _feature_string,
                                                        self.language,
                                                        self.location)
            return (url, _feature_string)
        return (None, None)

    @staticmethod
    def get_wu_response(url, max_tries):
        """Make a WU API call and return the raw response."""

        # we will attempt the call max_tries times
        for count in range(max_tries):
            # attempt the call
            try:
                w = urllib2.urlopen(url)
                _response = w.read()
                w.close()
                return _response
            except:
                loginf("WdSuppArchive:",
                       "Failed to get Weather Underground API response on attempt %d" % (count + 1,))
        else:
            loginf("WdSuppArchive:",
                   "Failed to get Weather Underground API response")
        return None

    def parse_wu_response(self, response, units):
        """ Parse a WU response and construct a packet packet."""

        # create a holder dict for the data we will gather
        _data = {}
        # do some pre-processing and error checking
        if response is not None:
            # we have a response so deserialise our JSON response
            _json_response = json.loads(response)
            # check for recognised format
            if not 'response' in _json_response:
                loginf("WdSuppArchive:",
                       "Unknown format in Weather Underground API response")
                return _data
            # get the WU 'response' field so we can check for errors
            _response = _json_response['response']
            # check for WU provided error otherwise start pulling in the
            # fields/data we want
            if 'error' in _response:
                loginf("WdSuppArchive:",
                       "Error in Weather Underground API response")
                return _data
            # pull out our individual 'feature' responses, this way in the
            # future we can populate our results even if we did not get a
            # 'feature' response that time round
            for _q in self.WU_queries:
                if _q['json_title'] in _json_response:
                    _q['response'] = _json_response[_q['json_title']]
        # iterate over each of possible queries and parse as required
        for _q in self.WU_queries:
            _resp = _q['response']
            # forecast data
            if _q['name'] == 'forecast' and _resp is not None:
                # Look up Saratoga icon number given WU icon name
                _data['forecastIcon'] = icon_dict[_resp['txt_forecast']['forecastday'][0]['icon']]
                _data['forecastText'] = _resp['txt_forecast']['forecastday'][0]['fcttext']
                _data['forecastTextMetric'] = _resp['txt_forecast']['forecastday'][0]['fcttext_metric']
            # conditions data
            elif _q['name'] == 'conditions' and _resp is not None:
                # WU does not seem to provide day/night icon name in their
                # 'conditions' response so we need to do. Just need to add
                # 'nt_' to front of name before looking up in out Saratoga
                # icons dictionary
                if self.night:
                    _data['currentIcon'] = icon_dict['nt_' + _resp['icon']]
                else:
                    _data['currentIcon'] = icon_dict[_resp['icon']]
                # get the current conditions text prepending a label if we have 
                # one
                if _resp['weather']:
                    _data['currentText'] = ''.join((self.current_label, 
                                                    _resp['weather']))
                else:
                    _data['currentText'] = None
            # almanac data
            elif _q['name'] == 'almanac' and _resp is not None:
                if units is weewx.US:
                    _data['tempRecordHigh'] = _resp['temp_high']['record']['F']
                    _data['tempNormalHigh'] = _resp['temp_high']['normal']['F']
                    _data['tempRecordLow'] = _resp['temp_low']['record']['F']
                    _data['tempNormalLow'] = _resp['temp_low']['normal']['F']
                else:
                    _data['tempRecordHigh'] = _resp['temp_high']['record']['C']
                    _data['tempNormalHigh'] = _resp['temp_high']['normal']['C']
                    _data['tempRecordLow'] = _resp['temp_low']['record']['C']
                    _data['tempNormalLow'] = _resp['temp_low']['normal']['C']
                _data['tempRecordHighYear'] = _resp['temp_high']['recordyear']
                _data['tempRecordLowYear'] = _resp['temp_low']['recordyear']
        return _data


# ===============================================================================
#                                 Utilities
# ===============================================================================


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
            return (None, data_dict['outTemp'])
        else:
            # ie the data packet is from after 6am and before or including 6pm
            return (data_dict['outTemp'], None)
    else:
        return (None, None)

def check_enable(cfg_dict, service, *args):

    try:
        wdsupp_dict = accumulateLeaves(cfg_dict[service], max_level = 1)
    except KeyError:
        logdbg2("weewxwd3: check_enable:",
                "%s: No config info. Skipped." % service)
        return None

    # check to see whether all the needed options exist, and none of them have
    # been set to 'replace_me'
    try:
        for option in args:
            if wdsupp_dict[option] == 'replace_me':
                raise KeyError(option)
    except KeyError, e:
        logdbg2("weewxwd3: check_enable:",
                "%s: Missing option %s" % (service, e))
        return None

    return wdsupp_dict


# ============================================================================
#                          Main Entry for Testing
# ============================================================================

# Define a main entry point for basic testing without the weeWX engine and
# service overhead. To invoke this module without weeWX:
#
# $ sudo PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/weewxwd3.py --option
#
# where option is one of the following options:
#   --help               - display command line help
#   --version            - display version
#   --get-wu-api-data    - display WU API data
#   --get-wu-api-config  - display WU API config parameters to be used 
#


if __name__ == '__main__':

    # python imports
    import optparse
    import pprint
    import sys

    # weeWX imports
    import weecfg


    usage = """sudo PYTHONPATH=/home/weewx/bin python
               /home/weewx/bin/user/%prog [--option]"""

    syslog.openlog('weewxwd3', syslog.LOG_PID | syslog.LOG_CONS)
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
        print "weewxwd3 version %s" % WEEWXWD_VERSION
        exit(0)

    # get config_dict to use
    config_path, config_dict = weecfg.read_config(options.config_path, args)
    print "Using configuration file %s" % config_path

    # get a WeeWX-WD config dict
    weewxwd_dict = config_dict.get('Weewx-WD', None)
    
    # get a WuApiQuery object
    if weewxwd_dict is not None:
        wu_api = WuApiQuery(config_dict)
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

