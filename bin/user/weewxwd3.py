#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# Version: 1.0.4                                    Date: 20 July 2018
#
# Revision History
#   20 July 2018
#       - fixed bug that occurred on partial packet stations that occasionally 
#         omit outTemp from packets/records
#       - changed behaviour for calculating derived obs. If any one of the 
#         pre-requisite obs are missing then the derived obs is not calculated 
#         and not added to the packet/record. If all of the pre-requisite obs 
#         exist but one or more is None then the derived obs is set to None. If 
#         all pre-requisite obs exist and are non-None then the derived obs is 
#         calculated and added to the packet/record as normal.
#       - simplified WdArchive new_archive_record() method
#   31 March 2017       v1.0.3
#       - no change, version number change only
#   14 December 2016    v1.0.2
#       - no change, version number change only
#   30 November 2016    v1.0.1
#       - now uses humidex and appTemp formulae from weewx.wxformulas
#       - weewx-WD db management functions moved to wd_database utility
#       - implemented syslog wrapper functions
#       - minor reformatting
#       - replaced calls to superseded DBBinder.get_database method with
#         DBBinder.get_manager method
#       - removed database management utility functions and placed in new
#         wd_database utility
#   10 January 2015     v1.0.0
#       - rewritten for Weewx v3.0
#       - uses separate database for weewx-WD specific data, no longer
#         recycles existing weewx database fields
#       - added __main__ to allow command line execution of a number of db
#         management actions
#       - removed --debug option from main()
#       - added --create_archive option to main() to create the weewxwd
#         database
#       - split --backfill_daily into separate --drop_daily and
#         --backfill_daily options
#       - added 'user.' to all weewx-WD imports
#   18 September 2014   v0.9.4 (never relaeased)
#       - added GNU license text
#   18 May 2014         v0.9.2
#       - removed code that set windDir/windGustDir to 0 if windDir/windGustDir
#         were None respectively
#   30 July 2013        v0.9.1
#       - revised version number to align with weewx-WD version numbering
#   20 July 2013        v0.1
#       - initial implementation
#

import syslog
import weewx
import time
import weewx.engine
import weewx.wxformulas
import weewx.units

from datetime import datetime
from weewx.units import obs_group_dict

WEEWXWD_VERSION = '1.0.4'

schema = [('dateTime',     'INTEGER NOT NULL UNIQUE PRIMARY KEY'),
          ('usUnits',      'INTEGER NOT NULL'),
          ('interval',     'INTEGER NOT NULL'),
          ('humidex',      'REAL'),
          ('appTemp',      'REAL'),
          ('outTempDay',   'REAL'),
          ('outTempNight', 'REAL')]

def logmsg(level, src, msg):
    syslog.syslog(level, '%s %s' % (src, msg))

def logdbg(src, msg):
    logmsg(syslog.LOG_DEBUG, src, msg)

def logdbg2(src, msg):
    if weewx.debug >= 2:
        logmsg(syslog.LOG_DEBUG, src, msg)

def loginf(src, msg):
    logmsg(syslog.LOG_INFO, src, msg)

def logerr(src, msg):
    logmsg(syslog.LOG_ERR, src, msg)

def calc_daynighttemps(data):
    """ 'Calculate' value for outTempDay.

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

    if data['outTemp'] is not None:
        # check if record covers daytime (6AM to 6PM) and if so add
        # 'outTemp' to 'outTempDay' remember record timestamped 6AM belongs
        # in the night time
        if datetime.fromtimestamp(data['dateTime']-1).hour < 6 or datetime.fromtimestamp(data['dateTime']-1).hour > 17:
            # ie the data packet is from before 6am or after 6pm
            return (None, data['outTemp'])
        else:
            # ie the data packet is from after 6am and before or including
            # 6pm
            return (data['outTemp'], None)
    else:
        return (None, None)


#=============================================================================
#                            Class WdWXCalculate
#=============================================================================


class WdWXCalculate(weewx.engine.StdService):

    def __init__(self, engine, config_dict):
        super(WdWXCalculate, self).__init__(engine, config_dict)

        # bind ourself to both loop and archive events
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_loop_packet(self, event):
        # get the packet as METRICWX units (makes the calcs easier)
        data_metricwx = weewx.units.to_METRICWX(event.packet)
        # start to build our WD data
        wd_data = {'usUnits': data_metricwx['usUnits']}
        # has weewx already calculated humidex?
        if 'humidex' not in data_metricwx:
            # no, so calculate it ourself and add to our WD data
            if 'outTemp' in data_metricwx and 'outHumidity' in data_metricwx:
                wd_data['humidex'] = weewx.wxformulas.humidexC(data_metricwx['outTemp'],
                                                               data_metricwx['outHumidity'])
        # has weewx already calculated appTemp?
        if 'appTemp' not in data_metricwx:
            # no, so calculate it ourself and add to our WD data
            if 'outTemp' in data_metricwx and 'outHumidity' in data_metricwx and 'windSpeed' in data_metricwx:
                wd_data['appTemp'] = weewx.wxformulas.apptempC(data_metricwx['outTemp'],
                                                               data_metricwx['outHumidity'],
                                                               data_metricwx['windSpeed'])
        # if we have outTemp data 'calculate' our day and night outTemp values
        # and add to our WD data
        if 'outTemp' in data_metricwx:
            wd_data['outTempDay'], wd_data['outTempNight'] = calc_daynighttemps(data_metricwx)

        # convert our WD data back to the original packet units
        wd_data_x = weewx.units.to_std_system(wd_data, event.packet['usUnits'])
        # add the WD data to the packet
        event.packet.update(wd_data_x)

    def new_archive_record(self, event):
        # get the packet as METRICWX units (makes the calcs easier)
        data_metricwx = weewx.units.to_METRICWX(event.record)
        # start to build our WD data
        wd_data = {'usUnits': data_metricwx['usUnits']}
        # has weewx already calculated humidex?
        if 'humidex' not in data_metricwx:
            # no, so calculate it ourself and add to our WD data
            if 'outTemp' in data_metricwx and 'outHumidity' in data_metricwx:
                wd_data['humidex'] = weewx.wxformulas.humidexC(data_metricwx['outTemp'],
                                                               data_metricwx['outHumidity'])
        # has weewx already calculated appTemp?
        if 'appTemp' not in data_metricwx:
            # no, so calculate it ourself and add to our WD data
            if 'outTemp' in data_metricwx and 'outHumidity' in data_metricwx and 'windSpeed' in data_metricwx:
                wd_data['appTemp'] = weewx.wxformulas.apptempC(data_metricwx['outTemp'],
                                                               data_metricwx['outHumidity'],
                                                               data_metricwx['windSpeed'])
        # if we have outTemp data 'calculate' our day and night outTemp values
        # and add to our WD data
        if 'outTemp' in data_metricwx:
            wd_data['outTempDay'], wd_data['outTempNight'] = calc_daynighttemps(data_metricwx)

        # convert our WD data back to the original record units
        wd_data_x = weewx.units.to_std_system(wd_data, event.record['usUnits'])
        # add the WD data to the record
        event.record.update(wd_data_x)


#=============================================================================
#                             Class WdArchive
#=============================================================================


class WdArchive(weewx.engine.StdService):
    """ Service to store weewx-WD specific archive data. """

    def __init__(self, engine, config_dict):
        super(WdArchive, self).__init__(engine, config_dict)

        # Extract our binding from the weewx-WD section of the config file. If
        # it's missing, fill with a default
        if 'WeewxWD' in config_dict:
            self.data_binding = config_dict['WeewxWD'].get('data_binding',
                                                           'wd_binding')
        else:
            self.data_binding = 'wd_binding'

        # Extract the Weewx binding for use when we check the need for backfill
        # from the Weewx archive
        if 'StdArchive' in config_dict:
            self.data_binding_wx = config_dict['StdArchive'].get('data_binding',
                                                                 'wx_binding')
        else:
            self.data_binding_wx = 'wx_binding'

        loginf("WdArchive:", "WdArchive will use data binding %s" % self.data_binding)

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
        """Called when a new archive record has arrived.

           Save WeeWX-WD specific data in the WeeWX-WD archive.
        """

        # Put the record in the archive
        dbmanager = self.engine.db_binder.get_manager(self.data_binding)
        dbmanager.addRecord(event.record)

    def setup_database(self, config_dict):
        """Setup the main database archive"""

        # This will create the database if it doesn't exist, then return an
        # opened instance of the database manager.
        dbmanager = self.engine.db_binder.get_manager(self.data_binding, initialize=True)
        loginf("WdArchive:", "Using binding '%s' to database '%s'" % (self.data_binding,
                                                                      dbmanager.database_name))

        # Check if we have any historical data to suck in from Weewx main
        # archive get a dbmanager for the Weewx archive
        dbmanager_wx = self.engine.db_binder.get_manager(self.data_binding_wx,
                                                         initialize=False)

        # Back fill the daily summaries.
        loginf("WdArchive:", "Starting backfill of daily summaries")
        t1 = time.time()
        nrecs, ndays = dbmanager.backfill_day_summary()
        tdiff = time.time() - t1
        if nrecs:
            _msg = "Processed %d records to backfill %d day summaries in %.2f seconds" % (nrecs,
                                                                                          ndays,
                                                                                          tdiff)
        else:
            _msg = "Daily summaries up to date."
        loginf("WdArchive:", _msg)
