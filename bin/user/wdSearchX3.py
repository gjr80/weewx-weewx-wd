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
# Version: 1.0.3                                    Date: 31 March 2017
#
# Revision History
#   31 March 2017       v1.0.3
#       - fix bug in wdMonthStats SLE that caused problems with monthRainMax_vh
#         for archives with small amounts (partial months) of data
#       - removed two lines of old commented out code from wdMonthStats SLE
#   14 December 2016    v1.0.2
#       - no change, version number change only
#   30 November 2016    v1.0.1
#       - revised for weewx v3.4.0
#       - implemented a second debug level (ie debug = 2)
#       - minor reformatting
#       - added heatColorWord, feelsLike and density tags to wdSundryTags SLE
#       - added day_windrun, yest_windrun, week_windrun, seven_day_windrun,
#         month_windrun, year_windrun tags and alltime_windrun tags to
#         wdWindRunTags SLE
#   10 January 2015     v1.0.0
#       - rewritten for weewx v3.0.0
#       - added wdManualAverages SLE
#       - fixed issues with wdRainThisDay SLE affecting databases with limited
#         historical data
#       - fixed bug in wdTimeSpanTags that was causing unit issues with
#         $alltime tags
#       - removed use of total_seconds() attribute in wdRainThisDay
#       - fixed error in wdHourRainTags
#       - removed redundant code in wdHourRainTags
#       - fixed errors in wdTesttagsRainAgo
#       - removed redundant wdClientrawRainAgo SLE
#   dd September 2014   v0.9.4 (never released)
#       - added execution time debug messages for all SLEs
#       - added additional tags to wdMonthStats SLE
#       - wdClientrawAgotags and wdTesttagsAgotags SLEs now use max_delta on
#         archive queries
#       - added additional tags to wdMaxAvgWindTags SLE
#       - wdSundryTags SLE now provides current_text and current_icon from
#         current conditions text file if it exists
#       - added additional tags to wdWindRunTags SLE
#       - new SLEs wdGdDays, wdForToday, wdRainThisDay and wdRainDays
#       - added helper functions get_first_day and doygen
#       - added GNU license text
#   August 2013         v0.1
#       - initial implementation
#
import datetime
import time
import itertools
import user.wdTaggedStats3
import weewx
import weeutil.weeutil
import weewx.almanac
import weewx.units
import syslog
import math
import calendar
import weewx.tags

from weewx.cheetahgenerator import SearchList
from weewx.tags import TimeBinder, TimespanBinder
from weeutil.weeutil import TimeSpan, archiveDaySpan, archiveMonthSpan, genMonthSpans, genDaySpans, startOfDay, option_as_list, isMidnight
from weewx.units import ValueHelper, getStandardUnitType, ValueTuple
from datetime import date

WEEWXWD_SLE_VERSION = '1.0.3'

def logmsg(level, msg):
    syslog.syslog(level, 'weewxWd: %s' % msg)

def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)

def logdbg2(msg):
   if weewx.debug >= 2:
        logmsg(syslog.LOG_DEBUG, msg)

def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)

def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)

def get_first_day(dt, d_years=0, d_months=0):
    """Function to return date object holding 1st of month containing dt
       d_years, d_months are offsets that may be applied to dt
    """

    # Get year number and month number applying offset as required
    _y, _m = dt.year + d_years, dt.month + d_months
    # Calculate actual month number taking into account EOY rollover
    _a, _m = divmod(_m-1, 12)
    # Calculate and return date object
    return date(_y+_a, _m+1, 1)

def doygen(start_ts, stop_ts):
    """Generator function yielding a timestamp of midnight for a given date
       each year.

       Yields a sequence of timestamps for midnight on the day of the year
       containing start_ts. Generator continues until stop_ts is reached unless
       stop_ts is midnight in current year in which case this years timestamp
       is not returned. See the example below.

       Example:

       >>> startstamp = 1143550356
       >>> print datetime.datetime.fromtimestamp(startstamp)
       2006-03-28 22:52:36
       >>> stopstamp = 1409230470
       >>> print datetime.datetime.fromtimestamp(stopstamp)
       2014-08-28 22:54:30

       >>> for span in doygen(startstamp, stopstamp):
       ...     print span
       2006-03-28 00:00:00
       2007-03-28 00:00:00
       2008-03-28 00:00:00
       2009-03-28 00:00:00
       2010-03-28 00:00:00
       2011-03-28 00:00:00
       2012-03-28 00:00:00
       2013-03-28 00:00:00
       2014-03-28 00:00:00

       start_ts: The start of the first interval in unix epoch time.

       stop_ts: The end of the last interval will be equal to or less than this.

       yields: A sequence of unix epoch timestamps. Each timestamp will be have time set to midnight
    """

    d1 = datetime.date.fromtimestamp(start_ts)
    stop_d = datetime.date.fromtimestamp(stop_ts)
    stop_dt = datetime.datetime.fromtimestamp(stop_ts)

    if stop_d >= d1:
        while d1 <= stop_d :
            t_tuple = d1.timetuple()
            year = t_tuple[0]
            month = t_tuple[1]
            day = t_tuple[2]
            if year != stop_dt.year or (stop_dt.hour != 0 and stop_dt.minute != 0):
                ts = time.mktime(t_tuple)
                yield ts
            if not calendar.isleap(year) or month != 2 or day != 29:
                year += 1
            else:
                year +=4
                if not calendar.isleap(year):
                    year +=4
            d1 = d1.replace(year=year)

def get_date_ago(dt, d_months=1):
    """Function to return date object d_months before dt.
       If d_months ago is an invalid date (eg 30 February) then the end of the
       month is returned. If dt is the end of the month then the end of the
       month concerned is returned.
    """

    _one_day = datetime.timedelta(days = 1)
    # Get year number and month number applying offset as required
    _y, _m, _d = dt.year, dt.month - d_months, dt.day
    # Calculate actual month number taking into account EOY rollover
    _a, _m = divmod(_m, 12)
    # Calculate eom of date to be returned
    _eom = datetime.date(_y + _a, _m + 1, 1) - _one_day
    # Calculate and return date object
    # If we are not on the last of the month or our day is invalid return
    # the end of the month
    if dt.month != (dt + _one_day).month or dt.day >= _eom.day:
        return _eom
    # Otherwise return the eom using our day
    return _eom.replace(day=dt.day)

class wdMonthStats(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def getMonthAveragesHighs(self, timespan, db_lookup):
        """Function to calculate alltime monthly:
           - average rainfall
           - record high temp
           - record low temp
           - average temp

           Results are calculated using daily data from stats database. Average
           rainfall is calculated by summing rainfall over each Jan, Feb...Dec
           then averaging these totals over the number of Jans, Febs... Decs
           in our data. Average temp
           Record high and low temps are max and min over all of each month.
           Partial months at start and end of our data are ignored. Assumes
           rest of our data is contiguous.

           Returned values are lists of ValueHelpers representing results for
           Jan, Feb thru Dec. Months that have no data are returned as None.
        """

        #
        # Set up those things we need to get going
        #

        # Get archive interval
        current_rec = db_lookup().getRecord(timespan.stop)
        _interval = current_rec['interval']
        # Get our UoMs and Groups
        (rain_type, rain_group) = getStandardUnitType(current_rec['usUnits'], 'rain')
        (outTemp_type, outTemp_group) = getStandardUnitType(current_rec['usUnits'], 'outTemp')
        # Set up a list to hold our average values
        monthRainAvg = [0 for x in range(12)]
        monthRainAvgNow = [None for x in range(12)]
        monthTempAvg = [0 for x in range(12)]
        monthTempAvgNow = [None for x in range(12)]
        # Set up lists to hold our results in ValueHelpers
        monthRainAvg_vh = [0 for x in range(12)]
        monthRainAvgNow_vh = [0 for x in range(12)]
        monthRainMax_vh = [0 for x in range(12)]
        monthTempAvg_vh = [0 for x in range(12)]
        monthTempAvgNow_vh = [0 for x in range(12)]
        monthTempMax_vh = [0 for x in range(12)]
        monthTempMin_vh = [0 for x in range(12)]

        # Set up a 2D list to hold our month running total and number of months
        # so we can calculate an average
        monthRainBin = [[0 for x in range(2)] for x in range(12)]
        monthTempBin = [[0 for x in range(2)] for x in range(12)]
        # Set up lists to hold our max and min records
        monthRainMax = [None for x in range(12)]
        monthRainMax_ts = None
        monthRainMaxNow = [None for x in range(12)] # used for max month rain this year
        monthTempMax = [None for x in range(12)]
        monthTempMin = [None for x in range(12)]
        # Get time object for midnight
        _mn_time = datetime.time()
        # Get timestamp for our first (earliest) and last (most recent) records
        _start_ts = db_lookup().firstGoodStamp()
        _end_ts = timespan.stop

        # Get these as datetime objects
        _start_dt = datetime.datetime.fromtimestamp(_start_ts)
        _end_dt = datetime.datetime.fromtimestamp(_end_ts)
        # If we do not have a complete month of data then we really have not much to do
        if (_start_dt.hour != 0 or _start_dt.minute != 0 or _start_dt.day != 1) and ((_start_dt.month == _end_dt.month and _start_dt.year == _end_dt.year) or (_end_dt < datetime.datetime.combine(get_first_day(_start_dt,0,2), _mn_time))):
            # We do not have a complete month of data so get record highs/lows, set everything else to None and return
            # Set our results to None


            for monthNum in range (12):
                # Set our month averages/max/min to None
                monthRainAvg[monthNum] = ValueTuple(None, rain_type, rain_group)
                monthRainAvgNow[monthNum] = ValueTuple(None, rain_type, rain_group)
                monthTempAvg[monthNum] = ValueTuple(None, outTemp_type, outTemp_group)
                monthTempAvgNow[monthNum] = ValueTuple(None, outTemp_type, outTemp_group)
                monthTempMax[monthNum] = ValueTuple(None, outTemp_type, outTemp_group)
                monthTempMin[monthNum] = ValueTuple(None, outTemp_type, outTemp_group)
                # Save our ValueTuples as ValueHelpers
                monthRainAvg_vh[monthNum] = ValueHelper(monthRainAvg[monthNum],
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                monthRainAvgNow_vh[monthNum] = ValueHelper(monthRainAvgNow[monthNum],
                                                           formatter=self.generator.formatter,
                                                           converter=self.generator.converter)
                monthRainMax_vh[monthNum] = ValueHelper((monthRainMax[monthNum], rain_type, rain_group),
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                monthTempAvg_vh[monthNum] = ValueHelper(monthTempAvg[monthNum],
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                monthTempAvgNow_vh[monthNum] = ValueHelper(monthTempAvgNow[monthNum],
                                                           formatter=self.generator.formatter,
                                                           converter=self.generator.converter)

                monthTempMax_vh[monthNum] = ValueHelper(monthTempMax[monthNum],
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                monthTempMin_vh[monthNum] = ValueHelper(monthTempMin[monthNum],
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
            # Process max/min for month containing _start_ts
            month_timespan = archiveMonthSpan(_start_ts)
            # get our max and min
            monthTempMax_tuple = db_lookup().getAggregate(month_timespan, 'outTemp', 'max')
            # Get the min temp for the month concerned
            monthTempMin_tuple = db_lookup().getAggregate(month_timespan, 'outTemp', 'min')
            # Save our max/min to the correct month bin
            monthTempMax_vh[_start_dt.month - 1] = ValueHelper(monthTempMax_tuple,
                                                               formatter=self.generator.formatter,
                                                               converter=self.generator.converter)
            monthTempMin_vh[_start_dt.month - 1] = ValueHelper(monthTempMin_tuple,
                                                               formatter=self.generator.formatter,
                                                               converter=self.generator.converter)
            # Do we have a 2nd month to process
            if (_end_dt < datetime.datetime.combine(get_first_day(_start_dt,0,2), _mn_time)):
                # We do cross a month boundary. Process max/min for month containing _end_ts
                month_timespan = archiveMonthSpan(_end_ts)
                # get our max and min
                monthTempMax_tuple = db_lookup().getAggregate(month_timespan, 'outTemp', 'max')
                # Get the min temp for the month concerned
                monthTempMin_tuple = db_lookup().getAggregate(month_timespan, 'outTemp', 'min')
                # Save our max/min to the correct month bin
                monthTempMax_vh[_end_dt.month - 1] = ValueHelper(monthTempMax_tuple,
                                                                 formatter=self.generator.formatter,
                                                                 converter=self.generator.converter)
                monthTempMin_vh[_end_dt.month - 1] = ValueHelper(monthTempMin_tuple,
                                                                 formatter=self.generator.formatter,
                                                                 converter=self.generator.converter)
            ymaxrainmonth = None
            ymaxrainyear = None
            yearmaxmonthrain_vh = ValueHelper((None, rain_type, rain_group),
                                              formatter=self.generator.formatter,
                                              converter=self.generator.converter)
        else:
            # We have more than a complete month of data so things are a bit more complex
            #
            # Work out our start times for looping through the months
            #

            # Determine timestamp of first record we will use. Will be midnight on
            # first of a month. We are using stats data to calculate our results
            # and the stats datetime for each day is midnight. We have obtained our
            # starting time from archive data where the first obs of the day has a
            # datetime of (archive interval) minutes after midnight. Need to take
            # this into account when choosing our start time. Need to skip any
            # partial months data at the start of data.

            # Get the datetime from ts of our first data record
            _day_date = datetime.datetime.fromtimestamp(_start_ts)
            # If this is not the 1st of the month or if its after
            # (archive interval) after midnight on 1st then we have a partial
            # month and we need to skip to next month.
            if _day_date.day > 1 or _day_date.hour > 0 or _day_date.minute > (_interval):
                _start_ts = int(time.mktime(datetime.datetime.combine(get_first_day(_day_date,0,1),_mn_time).timetuple()))
            # If its midnight on the 1st of the month then leave it as is
            elif _day_date.day == 1 and _day_date.hour == 0 and _day_date.minute == 0:
                pass
            # Otherwise its (archive interval) past midnight on 1st so we have the
            # right day just need to set our timestamp to midnight.
            else:
                _start_ts = int(time.mktime((_day_date.year, _day_date.month,_day_date.day,0,0,0,0,0,0)))
            # Determine timestamp of last record we will use. Will be midnight on
            # last of a month. We are using stats data to calculate our average
            # and the stats datetime for each day is midnight. We have obtained our
            # starting time from archive data where the first obs of the day has a
            # datetime of (archive interval) minutes after midnight. Need to take
            # this into account when choosing our start time. Need to skip any
            # partial months data at the start of data.
            #
            # Get the datetime from our ending point timestamp
            _day_date = datetime.datetime.fromtimestamp(_end_ts)
            if _day_date.day == 1 and _day_date.hour == 0 and _day_date.minute == 0:
                pass
            else:
                _end_ts = int(time.mktime((_day_date.year, _day_date.month,1,0,0,0,0,0,0)))

            # Determine timestamp to start our 'now' month stats ie stats for the last 12 months
            # If we are part way though a month then want midnight on 1st of month 11.something months ago
            # eg if its 5 November 2014 we want midnight 1 December 2013.
            # If we are (archive_interval) minutes after midnight on 1st of month we want midnight
            # 12 months and (archive_interval) minutes ago
            # If we are at midnight on 1st of month we want midnight 12 months ago

            # We have a partial month so go back 11.something months
            if _day_date.day > 1 or _day_date.hour > 0 or _day_date.minute >= (_interval):
                _start_now_ts = int(time.mktime(datetime.datetime.combine(get_first_day(_day_date,0,-11),_mn_time).timetuple()))
            # Otherwise its midnight on the 1st of the month and we just need to go back 12 months
            else:
                _start_now_ts = int(time.mktime(datetime.datetime.combine(get_first_day(_day_date,1,0),_mn_time).timetuple()))
            # Loop through each month timespan between our start and end timestamps
            for month_timespan in genMonthSpans(_start_ts, timespan.stop):
                # Work out or month bin number
                _month_bin = datetime.datetime.fromtimestamp(month_timespan.start).month-1
                # Get our data
                # Get the total rain for the month concerned
                monthRain_tuple = db_lookup().getAggregate(month_timespan, 'rain', 'sum')
                # Get the 'avg' temp for the month concerned
                monthTemp_tuple = db_lookup().getAggregate(month_timespan, 'outTemp', 'avg')
                # Get the max temp for the month concerned
                monthTempMax_tuple = db_lookup().getAggregate(month_timespan, 'outTemp', 'max')
                # Get the min temp for the month concerned
                monthTempMin_tuple = db_lookup().getAggregate(month_timespan, 'outTemp', 'min')
                # recordhigh/low, monthrainavg and monthtempavg all omit the current (partial) month so
                # check that we are not in that partial month
                if month_timespan.stop <= _end_ts:  # Not in a partial month so update
                    if monthRain_tuple[0] is not None:
                        # Update our total rain for that month
                        monthRainBin[_month_bin][0] += monthRain_tuple[0]
                        # Increment our count
                        monthRainBin[_month_bin][1] += 1
                    if monthTemp_tuple[0] is not None:
                        # Update our 'total' temp for that month
                        monthTempBin[_month_bin][0] += monthTemp_tuple[0] * (get_first_day(datetime.datetime.fromtimestamp(month_timespan.start).date(),0,1)-get_first_day(datetime.datetime.fromtimestamp(month_timespan.start).date(),0,0)).days
                        # Increment our count, in this case by the number of days in the month
                        monthTempBin[_month_bin][1] += (get_first_day(datetime.datetime.fromtimestamp(month_timespan.start).date(),0,1)-get_first_day(datetime.datetime.fromtimestamp(month_timespan.start).date(),0,0)).days
                    # Check if we are within the last 12 odd months for 'now' stats
                    # If so start accumulating. Averages are simply:
                    # rain - the total (sum) for the month
                    # temp - the avg for the month
                    if month_timespan.start >= _start_now_ts:
                        monthRainAvgNow[_month_bin] = monthRain_tuple[0]
                        monthRainMaxNow[_month_bin] = monthRain_tuple[0]
                        monthTempAvgNow[_month_bin] = monthTemp_tuple[0]
                # Update our max rain for the month
                if monthRain_tuple[0] is not None:
                    if monthRain_tuple[0] > monthRainMax[_month_bin]:
                        monthRainMax[_month_bin] = monthRain_tuple[0]
                        monthRainMax_ts = month_timespan.start
                if monthTempMax_tuple[0] is not None:
                    # If our record list holds None then the current value must be the new max
                    if monthTempMax[_month_bin] == None:
                        monthTempMax[_month_bin] = monthTempMax_tuple[0]
                    # If the current value is greater than our record list then update the list
                    elif monthTempMax_tuple[0] > monthTempMax[_month_bin]:
                        monthTempMax[_month_bin] = monthTempMax_tuple[0]
                if monthTempMin_tuple[0] is not None:
                    # If our record list holds None then the current value must be the new min
                    if monthTempMin[_month_bin] == None:
                        monthTempMin[_month_bin] = monthTempMin_tuple[0]
                    # If the current value is greater than our record list then update the list
                    elif monthTempMin_tuple[0] < monthTempMin[_month_bin]:
                        monthTempMin[_month_bin] = monthTempMin_tuple[0]

            # Loop through each month:
            #  - calculating averages and saving as a ValueTuple
            #  - converting monthly averages, max and min ValueHelpers
            for monthNum in range (12):
                # If we have a total > 0 then calc a simple average
                if monthRainBin[monthNum][1] != 0:
                    monthRainAvg[monthNum] = ValueTuple(monthRainBin[monthNum][0]/monthRainBin[monthNum][1], rain_type, rain_group)
                # If our sum == 0 and our count > 0 then set our average to 0
                elif monthRainBin[monthNum][1] > 0:
                    monthRainAvg[monthNum] = ValueTuple(0, rain_type, rain_group)
                # Otherwise we must have no data for that month so set our average
                # to None
                else:
                    monthRainAvg[monthNum] = ValueTuple(None, rain_type, rain_group)
                # If we have a total > 0 then calc a simple average
                if monthTempBin[monthNum][1] != 0:
                    monthTempAvg[monthNum] = (monthTempBin[monthNum][0]/monthTempBin[monthNum][1], outTemp_type, outTemp_group)
                # If our sum == 0 and our count > 0 then set our average to 0
                elif monthTempBin[monthNum][1] > 0:
                    monthTempAvg[monthNum] = (0, outTemp_type, outTemp_group)
                # Otherwise we must have no data for that month so set our average
                # to None
                else:
                    monthTempAvg[monthNum] = (None, outTemp_type, outTemp_group)

                # Save our ValueTuple as a ValueHelper
                monthRainAvg_vh[monthNum] = ValueHelper(monthRainAvg[monthNum],
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                monthTempAvg_vh[monthNum] = ValueHelper(monthTempAvg[monthNum],
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                # Save our max/min results as ValueHelpers
                monthRainMax_vh[monthNum] = ValueHelper((monthRainMax[monthNum], rain_type, rain_group),
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                monthTempMax_vh[monthNum] = ValueHelper((monthTempMax[monthNum], outTemp_type, outTemp_group),
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                monthTempMin_vh[monthNum] = ValueHelper((monthTempMin[monthNum], outTemp_type, outTemp_group),
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)
                # Save our 'now' results as ValueHelpers
                monthRainAvgNow_vh[monthNum] = ValueHelper((monthRainAvgNow[monthNum], rain_type, rain_group),
                                                           formatter=self.generator.formatter,
                                                           converter=self.generator.converter)
                monthTempAvgNow_vh[monthNum] = ValueHelper((monthTempAvgNow[monthNum], outTemp_type, outTemp_group),
                                                           formatter=self.generator.formatter,
                                                           converter=self.generator.converter)
            curr_month = datetime.date.fromtimestamp(timespan.stop).month
            ymaxrain = None
            ymaxrainmonth = None
            ymaxrainyear = datetime.date.fromtimestamp(timespan.stop).year
            for _month in range(curr_month):
                if monthRainMaxNow[_month] > ymaxrain:
                    ymaxrain = monthRainMaxNow[_month]
                    ymaxrainmonth = _month + 1

            # Save our year max month rain as ValueHelper
            yearmaxmonthrain_vh = ValueHelper((ymaxrain, rain_type, rain_group),
                                              formatter=self.generator.formatter,
                                              converter=self.generator.converter)

        # Return our lists of ValueHelpers
        return monthRainAvg_vh, monthRainAvgNow_vh, monthTempAvg_vh, monthTempAvgNow_vh, monthRainMax_vh, monthTempMax_vh, monthTempMin_vh, yearmaxmonthrain_vh, ymaxrainmonth, ymaxrainyear, monthRainMax_ts

    def get_extension_list(self, timespan, db_lookup):
        """Returns month avg/max/min stats based upon archive data.

        Provides:
        - avg rain
        - avg rain now (monthly rain for last 12 months incl current month)
        - avg temp
        - avg temp now (month avg temp for last 12 months incl current month)
        - record high temp
        - record low temp

        for January, February,..., December

        based upon all archive data with the exception of any partial months data at
        the start and end of the database (except for avgrainxxnow and avgtempxxnow which
        include current month.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.
        """

        t1 = time.time()

        # Get current month number
        curr_month = datetime.date.fromtimestamp(timespan.stop).month

        # Call getMonthAveragesHighs method to calculate average rain, temp
        # and max/min temps for each month
        monthRainAvg_vh, monthRainAvgNow_vh, monthTempAvg_vh, monthTempAvgNow_vh, monthRainMax_vh, monthTempMax_vh, monthTempMin_vh, yearmaxmonthrain_vh, ymaxrainmonth, ymaxrainyear, monthRainMax_ts = self.getMonthAveragesHighs(timespan, db_lookup)
        maxmonthrainmonth = datetime.datetime.fromtimestamp(monthRainMax_ts).month if monthRainMax_ts is not None else None
        maxmonthrainyear = datetime.datetime.fromtimestamp(monthRainMax_ts).year if monthRainMax_ts is not None else None
        # Returned values are already ValueHelpers so can add each entry straight to the search list
        # Create a dictionary with the tag names (keys) we want to use
        search_list_extension = {'avrainjan' : monthRainAvg_vh[0], 'avrainfeb' : monthRainAvg_vh[1],
                                 'avrainmar' : monthRainAvg_vh[2], 'avrainapr' : monthRainAvg_vh[3],
                                 'avrainmay' : monthRainAvg_vh[4], 'avrainjun' : monthRainAvg_vh[5],
                                 'avrainjul' : monthRainAvg_vh[6], 'avrainaug' : monthRainAvg_vh[7],
                                 'avrainsep' : monthRainAvg_vh[8], 'avrainoct' : monthRainAvg_vh[9],
                                 'avrainnov' : monthRainAvg_vh[10], 'avraindec' : monthRainAvg_vh[11],
                                 'avrainjannow' : monthRainAvgNow_vh[0], 'avrainfebnow' : monthRainAvgNow_vh[1],
                                 'avrainmarnow' : monthRainAvgNow_vh[2], 'avrainaprnow' : monthRainAvgNow_vh[3],
                                 'avrainmaynow' : monthRainAvgNow_vh[4], 'avrainjunnow' : monthRainAvgNow_vh[5],
                                 'avrainjulnow' : monthRainAvgNow_vh[6], 'avrainaugnow' : monthRainAvgNow_vh[7],
                                 'avrainsepnow' : monthRainAvgNow_vh[8], 'avrainoctnow' : monthRainAvgNow_vh[9],
                                 'avrainnovnow' : monthRainAvgNow_vh[10], 'avraindecnow' : monthRainAvgNow_vh[11],
                                 'avtempjan' : monthTempAvg_vh[0], 'avtempfeb' : monthTempAvg_vh[1],
                                 'avtempmar' : monthTempAvg_vh[2], 'avtempapr' : monthTempAvg_vh[3],
                                 'avtempmay' : monthTempAvg_vh[4], 'avtempjun' : monthTempAvg_vh[5],
                                 'avtempjul' : monthTempAvg_vh[6], 'avtempaug' : monthTempAvg_vh[7],
                                 'avtempsep' : monthTempAvg_vh[8], 'avtempoct' : monthTempAvg_vh[9],
                                 'avtempnov' : monthTempAvg_vh[10], 'avtempdec' : monthTempAvg_vh[11],
                                 'avtempjannow' : monthTempAvgNow_vh[0], 'avtempfebnow' : monthTempAvgNow_vh[1],
                                 'avtempmarnow' : monthTempAvgNow_vh[2], 'avtempaprnow' : monthTempAvgNow_vh[3],
                                 'avtempmaynow' : monthTempAvgNow_vh[4], 'avtempjunnow' : monthTempAvgNow_vh[5],
                                 'avtempjulnow' : monthTempAvgNow_vh[6], 'avtempaugnow' : monthTempAvgNow_vh[7],
                                 'avtempsepnow' : monthTempAvgNow_vh[8], 'avtempoctnow' : monthTempAvgNow_vh[9],
                                 'avtempnovnow' : monthTempAvgNow_vh[10], 'avtempdecnow' : monthTempAvgNow_vh[11],
                                 'recordhighrainjan' : monthRainMax_vh[0], 'recordhighrainfeb' : monthRainMax_vh[1],
                                 'recordhighrainmar' : monthRainMax_vh[2], 'recordhighrainapr' : monthRainMax_vh[3],
                                 'recordhighrainmay' : monthRainMax_vh[4], 'recordhighrainjun' : monthRainMax_vh[5],
                                 'recordhighrainjul' : monthRainMax_vh[6], 'recordhighrainaug' : monthRainMax_vh[7],
                                 'recordhighrainsep' : monthRainMax_vh[8], 'recordhighrainoct' : monthRainMax_vh[9],
                                 'recordhighrainnov' : monthRainMax_vh[10], 'recordhighraindec' : monthRainMax_vh[11],
                                 'recordhightempjan' : monthTempMax_vh[0], 'recordhightempfeb' : monthTempMax_vh[1],
                                 'recordhightempmar' : monthTempMax_vh[2], 'recordhightempapr' : monthTempMax_vh[3],
                                 'recordhightempmay' : monthTempMax_vh[4], 'recordhightempjun' : monthTempMax_vh[5],
                                 'recordhightempjul' : monthTempMax_vh[6], 'recordhightempaug' : monthTempMax_vh[7],
                                 'recordhightempsep' : monthTempMax_vh[8], 'recordhightempoct' : monthTempMax_vh[9],
                                 'recordhightempnov' : monthTempMax_vh[10], 'recordhightempdec' : monthTempMax_vh[11],
                                 'recordlowtempjan' : monthTempMin_vh[0], 'recordlowtempfeb' : monthTempMin_vh[1],
                                 'recordlowtempmar' : monthTempMin_vh[2], 'recordlowtempapr' : monthTempMin_vh[3],
                                 'recordlowtempmay' : monthTempMin_vh[4], 'recordlowtempjun' : monthTempMin_vh[5],
                                 'recordlowtempjul' : monthTempMin_vh[6], 'recordlowtempaug' : monthTempMin_vh[7],
                                 'recordlowtempsep' : monthTempMin_vh[8], 'recordlowtempoct' : monthTempMin_vh[9],
                                 'recordlowtempnov' : monthTempMin_vh[10], 'recordlowtempdec' : monthTempMin_vh[11],
                                 'currentmonthavrain' : monthRainAvg_vh[curr_month - 1],
                                 'currentmonthrecordrain' : monthRainMax_vh[curr_month - 1],
                                 'yearmaxmonthrain' : yearmaxmonthrain_vh, 'yearmaxmonthrainmonth' : ymaxrainmonth,
                                 'yearmaxmonthrainyear' : ymaxrainyear,
                                 'maxmonthrainmonth' : maxmonthrainmonth, 'maxmonthrainyear' : maxmonthrainyear
                                }

        t2 = time.time()
        logdbg2("wdMonthStats SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdTesttagsAgoRainTags(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with agoxxxrain tags.
           Rainfall trend data on wxtrends.php page needs to be cumulative
           since the start of the day. $agoxx.rain only provides the
           rainfall over the archive period (eg 5 minutes) ending xx
           minutes ago. $agoxxrain tags have been implemented to work around
           this and provide correct cumulative rainfall.
           ago periods implemented are 5, 10, 15, 20, 30, 45, 60, 75, 90,
           105, 120 minutes. These can be extended by altering the list below.
           Result is a ValueHelper that is added to the search list so normal
           Weewx unit conversion and formatting is available

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          agoxrain: A list of ValueHelpers containing the days rain to the time
                    x minutes ago. Rain is calculated from midnight. x is 5, 10,
                    15, 20, 30, 45, 60, 75, 90, 105 or 120.
        """

        t1 = time.time()

        ##
        ## Get units for use later with ValueHelpers
        ##

        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get the unit in use for each group
        rainUnitType = getStandardUnitType(current_rec['usUnits'], 'rain')

        search_list_extension={}
        # step through our 'ago' times. Additional times can be added to this
        # list (in minutes)
        for ago in (5, 10, 15, 20, 30, 45, 60, 75, 90, 105, 120):
            # want a TimeSpan from start of today to the time 'ago' minutes ago

            # first get timestamp 'ago' minutes ago
            rain_ts = timespan.stop - ago * 60
            # get TimeSpan for the entire day containing rain_ts
            rain_ts_TimeSpan = archiveDaySpan(rain_ts)
            # get a TimeSpan for our query
            rain_tspan = TimeSpan(rain_ts_TimeSpan.start, rain_ts)

            # enclose our query in a try..except block in case the earlier records
            # do not exist
            try:
                (time_start_vt, time_stop_vt, rain_vt) = db_lookup().getSqlVectors(rain_tspan, 'rain', 'sum',
                                                                         rain_tspan.stop - rain_tspan.start)
                rain_vh = ValueHelper((rain_vt[0][0], rain_vt[1], rain_vt[2]), formatter=self.generator.formatter,
                                      converter=self.generator.converter)
            except:
                rain_vh = ValueHelper((None, rainUnitType[0], rainUnitType[1]), formatter=self.generator.formatter,
                                      converter=self.generator.converter)

            search_list_extension['ago'+str(ago)+'rain'] = rain_vh

        t2 = time.time()
        logdbg2("wdTesttagsAgoRainTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdLastRainTags(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with datetime of last rain.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          last_rain: A ValueHelper containing the datetime of the last rain
        """

        t1 = time.time()

        ##
        ## Get date and time of last rain
        ##
        ## Returns unix epoch of archive period of last rain
        ##
        ## Result is returned as a ValueHelper so standard Weewx formatting
        ## is available eg $last_rain.format("%d %m %Y")
        ##

        # Get ts for day of last rain from statsdb
        # Value returned is ts for midnight on the day the rain occurred
        _row = db_lookup().getSql("SELECT MAX(dateTime) FROM archive_day_rain WHERE sum > 0")
        lastrain_ts = _row[0]
        # Now if we found a ts then use it to limit our search on the archive
        # so we can find the last archive record during which it rained. Wrap
        # in a try statement just in case
        if lastrain_ts is not None:
            try:
                _row = db_lookup().getSql("SELECT MAX(dateTime) FROM archive WHERE rain > 0 AND dateTime > ? AND dateTime <= ?", (lastrain_ts, lastrain_ts + 86400))
                lastrain_ts = _row[0]
            except:
                lastrain_ts = None
        # Wrap our ts in a ValueHelper
        lastrain_vt = (lastrain_ts, 'unix_epoch', 'group_time')
        lastrain_vh = ValueHelper(lastrain_vt, formatter=self.generator.formatter,
                                  converter=self.generator.converter)
        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'last_rain' : lastrain_vh}

        t2 = time.time()
        logdbg2("wdLastRainTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdTimeSpanTags(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """ Returns a search list extension with all time and last seven days
            stats.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          tspan_binder: A TimespanBinder object that allows a data binding to
                        be specified (default to None) when calling $alltime
                        eg $alltime.outTemp.max for the all time high outside
                           temp.
                           $alltime($data_binding='wd_binding').humidex.max
                           for the all time high humidex where humidex
                           resides in the 'wd_binding' database.

                        Standard Weewx unit conversion and formatting options
                        are available.
        """

        t1 = time.time()

        class wdBinder(TimeBinder):

            def __init__(self, db_lookup, report_time,
                         formatter=weewx.units.Formatter(), converter=weewx.units.Converter(), **option_dict):
                """Initialize an instance of wdBinder.

                db_lookup: A function with call signature db_lookup(data_binding), which
                returns a database manager and where data_binding is an optional binding
                name. If not given, then a default binding will be used.

                report_time: The time for which the report should be run.

                formatter: An instance of weewx.units.Formatter() holding the formatting
                information to be used. [Optional. If not given, the default
                Formatter will be used.]

                converter: An instance of weewx.units.Converter() holding the target unit
                information to be used. [Optional. If not given, the default
                Converter will be used.]

                option_dict: Other options which can be used to customize calculations.
                [Optional.]
                """
                self.db_lookup = db_lookup
                self.report_time = report_time
                self.formatter = formatter
                self.converter = converter
                self.option_dict = option_dict

            # Give it a method "alltime", with optional parameter data_binding
            def alltime(self, data_binding=None):
                # to avoid problems where our data_binding might have a first
                # good timestamp that is different to timespan.start (and thus
                # change which manager is used) we need to reset our
                # timespan.start to the first good timestamp of our data_binding

                # get a manager
                db_manager = db_lookup(data_binding)
                # get our first good timestamp
                start_ts = db_manager.firstGoodStamp()
                # reset our timespan
                alltime_tspan = TimeSpan(start_ts, timespan.stop)

                return TimespanBinder(alltime_tspan,
                                      self.db_lookup, context='alltime',
                                      data_binding=data_binding, # overrides the default
                                      formatter=self.formatter,
                                      converter=self.converter)

            # Give it a method "seven_day", with optional parameter data_binding
            def seven_day(self, data_binding=None):

                # Calculate the time at midnight, seven days ago.
                seven_day_dt = datetime.date.fromtimestamp(timespan.stop) - datetime.timedelta(weeks=1)
                # Now convert it to unix epoch time:
                seven_day_ts = time.mktime(seven_day_dt.timetuple())
                # get our 7 day timespan
                seven_day_tspan = TimeSpan(seven_day_ts, timespan.stop)
                # Now form a TimespanBinder object, using the ts we just calculated:

                return TimespanBinder(seven_day_tspan,
                                      self.db_lookup, context='seven_day',
                                      data_binding=data_binding, # overrides the default
                                      formatter=self.formatter,
                                      converter=self.converter)

        tspan_binder = wdBinder(db_lookup,
                                timespan.stop,
                                self.generator.formatter,
                                self.generator.converter)

        t2 = time.time()
        logdbg2("wdTimeSpanTags SLE executed in %0.3f seconds" % (t2-t1))

        return [tspan_binder]

class wdMaxAvgWindTags(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list with various average and max average wind
           speed stats.

           Due to Weewx combining windSpeed and windGust to create hybrid
           'wind' stat, Weewx cannot natively provide windSpeed (only) stats
           such as $day.windSpeed.max etc. This SLE utilises the windAv stat
           generated by Weewx-WD to generate today's max and avg windSpeed
           along with associated directions and times.
           xx minute average wind speeds and direction utilise the
           standard Weewx wind related fields stored in the archive db.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          max_avg_wind: A ValueHelper containing today's max windSpeed
                        (ie max average archive period wind speed - not gust).
                        Standard Weewx unit conversion and formatting is
                        available.
          max_avg_wind_dir: A ValueHelper containing the direction of today's
                            max windSpeed. Standard Weewx unit conversion and
                            formatting is available.
          max_avg_wind_time: A ValueHelper containing the epoch time of today's
                            max windSpeed. Standard Weewx unit conversion and
                            formatting is available.
          yest_max_avg_wind: A ValueHelper containing yesterday's max windSpeed
                             (ie max average archive period wind speed - not
                             gust). Standard Weewx unit conversion and
                             formatting is available.
          yest_max_avg_wind_dir: A ValueHelper containing the direction of
                                 yesterday's max windSpeed. Standard Weewx unit
                                 conversion and formatting is available.
          yest_max_avg_wind_time: A ValueHelper containing the epoch time of
                                  yesterday's max windSpeed. Standard Weewx unit
                                  conversion and formatting is available.
          avwind120: Average wind speed over the past 120 minutes.
          avwind60: Average wind speed over the past 60 minutes.
          avwind30: Average wind speed over the past 30 minutes.
          avwind15: Average wind speed over the past 15 minutes.
          avwind10: Average wind speed over the past 10 minutes.
          avdir10: Average wind direction over the last 10 minutes.
        """

        t1 = time.time()

        ##
        ## Get units for use later with ValueHelpers
        ##
        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get the unit in use for each group
        (windSpeed_type, windSpeed_group) = getStandardUnitType(current_rec['usUnits'],
                                                                'windSpeed')
        (windDir_type, windDir_group) = getStandardUnitType(current_rec['usUnits'],
                                                            'windDir')
        (dateTime_type, dateTime_group) = getStandardUnitType(current_rec['usUnits'],
                                                              'dateTime')

        ##
        ## For Today and Yesterdays stats we need some midnight timestamps
        ##
        # Get time obj for midnight
        midnight_t = datetime.time(0)
        # Get datetime obj for now
        today_dt = datetime.datetime.today()
        # Get datetime obj for midnight at start of today (our start time)
        midnight_dt = datetime.datetime.combine(today_dt, midnight_t)
        # Get timestamp for midnight at start of today (our start time)
        midnight_ts = time.mktime(midnight_dt.timetuple())
        # Our start is 1 day earlier than current (midnight today)
        midnight_yest_dt = midnight_dt - datetime.timedelta(days=1)
        # Get it as a timestamp
        midnight_yest_ts = time.mktime(midnight_yest_dt.timetuple())

        ##
        ## Todays windSpeed stats
        ##
        # Get today's windSpeed obs as a ValueTuple and convert them
        (time_start_vt, time_stop_vt, wind_speed_vt) = db_lookup().getSqlVectors(TimeSpan(midnight_ts, timespan.stop),
                                                                                 'windSpeed')
        wind_speed_vt = self.generator.converter.convert(wind_speed_vt)
        # Get today's windDir obs as a ValueTuple and convert them
        (time_start_vt, time_stop_vt, wind_dir_vt) = db_lookup().getSqlVectors(TimeSpan(midnight_ts, timespan.stop),
                                                                               'windDir')
        wind_dir_vt = self.generator.converter.convert(wind_dir_vt)
        # Convert the times
        wind_speed_time_vt = self.generator.converter.convert(time_stop_vt)
        # Find the max windSpeed
        max_avg_wind = max(wind_speed_vt[0])
        # Find its location in the list
        maxindex = wind_speed_vt[0].index(max_avg_wind)
        # Get the corresponding direction
        max_avg_dir = wind_dir_vt[0][maxindex]
        # Get the corresponding time
        max_avg_wind_time = wind_speed_time_vt[0][maxindex]
        # Wrap results in a ValueHelper to provide formatting and unit info
        max_avg_wind_vt = (max_avg_wind, windSpeed_type, windSpeed_group)
        max_avg_wind_vh = ValueHelper(max_avg_wind_vt,
                                      formatter=self.generator.formatter,
                                      converter=self.generator.converter)
        max_avg_wind_dir_vt = (max_avg_dir, windDir_type, windDir_group)
        max_avg_wind_dir_vh = ValueHelper(max_avg_wind_dir_vt,
                                          formatter=self.generator.formatter,
                                          converter=self.generator.converter)
        max_avg_wind_time_vt = (max_avg_wind_time, dateTime_type, dateTime_group)
        max_avg_wind_time_vh = ValueHelper(max_avg_wind_time_vt,
                                           formatter=self.generator.formatter,
                                           converter=self.generator.converter)

        ##
        ## Yesterdays windSpeed stats
        ##
        # Get yesterday's windSpeed obs as a ValueTuple and convert them
        (time_start_vt, time_stop_vt, wind_speed_vt) = db_lookup().getSqlVectors(TimeSpan(midnight_yest_ts, midnight_ts),
                                                                                 'windSpeed')
        wind_speed_vt = self.generator.converter.convert(wind_speed_vt)
        # Get yesterday's windDir obs as a ValueTuple and convert them
        (time_start_vt, time_stop_vt, wind_dir_vt) = db_lookup().getSqlVectors(TimeSpan(midnight_yest_ts, midnight_ts),
                                                                               'windDir')
        wind_dir_vt = self.generator.converter.convert(wind_dir_vt)
        # Convert the times
        wind_speed_time_vt = self.generator.converter.convert(time_stop_vt)
        # Find the max windSpeed. Wrap in try statement in case it does not exist
        try:
            yest_max_avg_wind = max(wind_speed_vt[0])
            # Find its location in the list
            maxindex = wind_speed_vt[0].index(yest_max_avg_wind)
            # Get the corresponding direction
            yest_max_avg_dir = wind_dir_vt[0][maxindex]
            # Get the corresponding time
            yest_max_avg_wind_time = wind_speed_time_vt[0][maxindex]
        except:
            yest_max_avg_wind = None
            yest_max_avg_dir = None
            yest_max_avg_wind_time = None
        # Wrap results in a ValueHelper to provide formatting and unit info
        yest_max_avg_wind_vt = (yest_max_avg_wind,
                                windSpeed_type,
                                windSpeed_group)
        yest_max_avg_wind_vh = ValueHelper(yest_max_avg_wind_vt,
                                           formatter=self.generator.formatter,
                                           converter=self.generator.converter)
        yest_max_avg_wind_dir_vt = (yest_max_avg_dir,
                                    windDir_type,
                                    windDir_group)
        yest_max_avg_wind_dir_vh = ValueHelper(yest_max_avg_wind_dir_vt,
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
        yest_max_avg_wind_time_vt = (yest_max_avg_wind_time,
                                     dateTime_type,
                                     dateTime_group)
        yest_max_avg_wind_time_vh = ValueHelper(yest_max_avg_wind_time_vt,
                                                formatter=self.generator.formatter,
                                                converter=self.generator.converter)

        # Get our last xx minute average wind speeds
        # 120 minutes
        (time_start_vt, time_stop_vt, avwind120_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop - 7200, timespan.stop),
                                                                                'windSpeed', 'avg', 7200)
        # 60 minutes
        (time_start_vt, time_stop_vt, avwind60_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop - 3600, timespan.stop),
                                                                               'windSpeed', 'avg', 3600)
        # 30 minutes
        (time_start_vt, time_stop_vt, avwind30_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop - 1800, timespan.stop),
                                                                               'windSpeed', 'avg', 1800)
        # 15 minutes
        (time_start_vt, time_stop_vt, avwind15_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop - 900, timespan.stop),
                                                                               'windSpeed', 'avg', 900)
        # 10 minutes
        (time_start_vt, time_stop_vt, avwind10_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop - 600, timespan.stop),
                                                                               'windSpeed', 'avg', 600)
        # 10 minute average wind direction
        (time_start_vt, time_stop_vt, avdir10_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop - 600, timespan.stop),
                                                                              'windvec', 'avg', 600)
        # our _vt holds x and an y component of wind direction, need to use
        # some trigonometry to get the angle
        # wrap in try..except in case we get a None in there somewhere
        try:
            avdir10 = 90.0 - math.degrees(math.atan2(avdir10_vt[0][0].imag, avdir10_vt[0][0].real))
            avdir10 = round(avdir10,0) if avdir10 >= 0 else round(avdir10 + 360.0,0)
        except:
            avdir10 = None
        # put our results into ValueHelpers
        avwind120_vh = ValueHelper((avwind120_vt[0][0], avwind120_vt[1], avwind120_vt[2]),
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)
        avwind60_vh = ValueHelper((avwind60_vt[0][0], avwind60_vt[1], avwind60_vt[2]),
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)
        avwind30_vh = ValueHelper((avwind30_vt[0][0], avwind30_vt[1], avwind30_vt[2]),
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)
        avwind15_vh = ValueHelper((avwind15_vt[0][0], avwind15_vt[1], avwind15_vt[2]),
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)
        avwind10_vh = ValueHelper((avwind10_vt[0][0], avwind10_vt[1], avwind10_vt[2]),
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)
        avdir10_vh = ValueHelper((avdir10, windDir_type, windDir_group),
                                 formatter=self.generator.formatter,
                                 converter=self.generator.converter)

        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'max_avg_wind' : max_avg_wind_vh,
                                 'max_avg_wind_dir' : max_avg_wind_dir_vh,
                                 'max_avg_wind_time' : max_avg_wind_time_vh,
                                 'yest_max_avg_wind' : yest_max_avg_wind_vh,
                                 'yest_max_avg_wind_dir' : yest_max_avg_wind_dir_vh,
                                 'yest_max_avg_wind_time' : yest_max_avg_wind_time_vh,
                                 'avwind120' : avwind120_vh,
                                 'avwind60' : avwind60_vh,
                                 'avwind30' : avwind30_vh,
                                 'avwind15' : avwind15_vh,
                                 'avwind10' : avwind10_vh,
                                 'avdir10' : avdir10_vh}

        t2 = time.time()
        logdbg2("wdMaxAvgWindTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdMaxWindGustTags(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with various max wind gust tags.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          max_24h_gust_wind: A ValueHelper containing the max windGust over the
                             preceding 24 hours. Standard Weewx unit conversion
                             and formatting is available.
          max_24h_gust_wind_time: A ValueHelper containing the max windGust
                                  over the preceding 24 hours. Standard Weewx
                                  unit conversion and formatting is available.

          max_10_gust_wind: A ValueHelper containing the max windGust over the
                            preceding 10 minutes. Standard Weewx unit
                            conversion and formatting is available.
        """

        t1 = time.time()

        ##
        ## Get units for use later with ValueHelpers
        ##
        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get the unit in use for each group
        (windSpeed_type, windSpeed_group) = getStandardUnitType(current_rec['usUnits'], 'windSpeed')
        (dateTime_type, dateTime_group) = getStandardUnitType(current_rec['usUnits'], 'dateTime')

        ##
        ## Last 24 hours windGust stats
        ##
        # Get last 24 hour's windGust obs as a ValueTuple and convert them
        (time_start_vt, time_stop_vt, wind_gust_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop-86400, timespan.stop), 'windGust')
        wind_gust_vt = self.generator.converter.convert(wind_gust_vt)
        # Convert the times
        wind_gust_time_vt = self.generator.converter.convert(time_stop_vt)
        # Find the max windGust
        max_gust_wind = max(wind_gust_vt[0])
        # Find its location in the list
        maxindex = wind_gust_vt[0].index(max_gust_wind)
        # Get the corresponding time
        max_gust_wind_time = wind_gust_time_vt[0][maxindex]
        # Wrap results in a ValueHelper to provide formatting and unit info
        max_gust_wind_vt = (max_gust_wind, windSpeed_type, windSpeed_group)
        max_gust_wind_vh = ValueHelper(max_gust_wind_vt, formatter=self.generator.formatter, converter=self.generator.converter)
        max_gust_wind_time_vt = (max_gust_wind_time, dateTime_type, dateTime_group)
        max_gust_wind_time_vh = ValueHelper(max_gust_wind_time_vt, formatter=self.generator.formatter, converter=self.generator.converter)

        ##
        ## Last 10 min windGust stats
        ##
        # Get last 10 minutes max windGust obs as a ValueTuple and convert them
        (time_start_vt, time_stop_vt, wind_gust_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop-600, timespan.stop), 'windGust', 'max', 600)
        # Do any necessary conversion
        wind_gust_vt = self.generator.converter.convert(wind_gust_vt)
        # Wrap results in a ValueHelper to provide formatting and unit info
        max_10_gust_wind_vt = (wind_gust_vt[0][0], windSpeed_type, windSpeed_group)
        max_10_gust_wind_vh = ValueHelper(max_10_gust_wind_vt,
                                          formatter=self.generator.formatter,
                                          converter=self.generator.converter)

        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'max_24h_gust_wind' : max_gust_wind_vh,
                                 'max_24h_gust_wind_time' : max_gust_wind_time_vh,
                                 'max_10_gust_wind' : max_10_gust_wind_vh}

        t2 = time.time()
        logdbg2("wdMaxWindGustTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdSundryTags(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns various tags.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                    the start and stop times of the domain of valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          forecast_text:  A string with weather forecast text read from a file
                          specified in the relevant skin.conf.
          forecast_icon:  An integer representing the weather forecast icon
                          read from a file specified in the relevant skin.conf.
          current_text:   A string with the current weather conditions summary
                          read from a file specified in the relevant skin.conf.
          current_icon:   An integer representing the weather forecast icon read
                          from a file specified in the relevant skin.conf.
          start_time:     A ValueHelper containing the epoch time that weewx was
                          started. Standard Weewx unit conversion and formatting
                          is available.
          nineamrain:     A ValueHelper containing the rainfall since 9am. Note
                          that if it is before 9am the result will be the total
                          rainfall since 9am the previous day. At 9am the value
                          is None.
          heatColorWord:  A string describing the current temperature
                          conditions. Based on outTemp, outHumidity and humidex.
          feelsLike:      A ValueHelper representing the perceived temperature.
                          Based on outTemp, windchill and humidex.
          density:        A number representing the current air density in kg/m3.
          beaufort:       The windSpeed as an integer on the Beaufort scale.
          beaufortDesc:   The textual description/name of the current beaufort
                          wind speed.
          wetBulb:        A ValueHelper containing the current wetbulb
                          temperature.
          cbi:            A ValueHelper containing the current Chandler Burning
                          Index.
          cbitext:        A string containing the current Chandler Burning Index
                          descriptive text.
          cloudbase:      A ValueHelper containing the current cloudbase.
          Easter:         A ValueHelper containing the date of the next Easter
                          Sunday. The time represented is midnight at the start
                          of Easter Sunday.
          trend_60_baro:  A string representing the 1 hour barometer trend.
          trend_180_baro: A string representing the 3 hour barometer trend.
        """

        t1 = time.time()

        ##
        ## A forecast data text file can be used to provide forecast_text,
        ## forecast_icon, current_text and current_icon tags. The format of the
        ## file is text only with the forecast_text value being on the 1st line,
        ## the forecast_icon value on the 2nd line, current_text value being on
        ## the 3rd line and current_icon on the 4th line. No other lines are
        ## read. This file is specified in the [Extras] section of the the
        ## skin.conf concerned as follows:
        ## [Extras]
        ##     [[Forecast]]
        ##         Forecast_File_Location = /path/to/filename.txt
        ##
        ## Where filename.txt is the name of the file holding the forecast data.
        ##

        # Get forecast file setting
        forecastfile = self.generator.skin_dict['Extras']['Forecast'].get('Forecast_File_Location')
        # If the file exists open it, get the data and close it
        if (forecastfile):
            f = open(forecastfile, "r")
            raw_text = f.readline()
            forecast_text = raw_text.strip(' \t\n\r')
            raw_text = f.readline()
            forecast_icon = int(raw_text.strip(' \t\n\r'))
            raw_text = f.readline()
            current_text = raw_text.strip(' \t\n\r')
            raw_text = f.readline()
            current_icon = raw_text.strip(' \t\n\r')
            f.close()

        # Otherwise set the forecast data to empty strings
        else:
            forecast_text = ""
            forecast_icon = None
            current_text = ""
            current_icon = None
        ##
        ## Get units for possible use later with ValueHelpers
        ##

        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        self.generator.gen_wd_ts = db_lookup('wd_binding').lastGoodStamp()
        curr_rec = db_lookup().getRecord(self.generator.gen_ts)
        curr_wd_rec = db_lookup().getRecord(self.generator.gen_wd_ts)
        # Get the unit in use for each group
        (rain_type, rain_group) = getStandardUnitType(curr_rec['usUnits'], 'rain')
        (dateTime_type, dateTime_group) = getStandardUnitType(curr_rec['usUnits'],
                                                              'dateTime')

        ##
        ## Get ts Weewx was launched
        ##
        try:
            starttime = weewx.launchtime_ts
        except ValueError:
            starttime = time.time()
        # Wrap in a ValueHelper
        starttime_vt = (starttime, dateTime_type, dateTime_group)
        starttime_vh = ValueHelper(starttime_vt,
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)

        ##
        ## Get rainfall since 9am
        ##
        # Need a ts for '9am', but is it 9am today or 9am yesterday
        # Get datetime obj for the time of our report
        today_dt = datetime.datetime.fromtimestamp(timespan.stop)
        # Get time obj for midnight
        midnight_t = datetime.time(0)
        # Get datetime obj for midnight at start of today
        midnight_dt = datetime.datetime.combine(today_dt, midnight_t)
        # If its earlier than 9am want 9am yesterday
        if today_dt.hour < 9:
            nineam_dt = midnight_dt - datetime.timedelta(hours=15)
        # Otherwise we want 9am today
        else:
            nineam_dt = midnight_dt + datetime.timedelta(hours=9)
        # Get it as a timestamp
        nineam_ts = time.mktime(nineam_dt.timetuple())
        try:
            (time_start_vt, time_stop_vt, rain_vt) = db_lookup().getSqlVectors(TimeSpan(nineam_ts, timespan.stop),
                                                                               'rain', 'sum',
                                                                               (timespan.stop - nineam_ts))
            rain_vh = ValueHelper((rain_vt[0][0], rain_type, rain_group),
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)
        except:
            rain_vh = ValueHelper((None, rain_type, rain_group),
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)

        #
        # HeatColorWord
        #
        heatColorWords = ['Unknown', 'Extreme Heat Danger', 'Heat Danger',
                          'Extreme Heat Caution', 'Extremely Hot',
                          'Uncomfortably Hot', 'Hot', 'Warm', 'Comfortable',
                          'Cool', 'Cold', 'Uncomfortably Cold', 'Very Cold',
                          'Extreme Cold']
        curr_rec_metric = weewx.units.to_METRIC(curr_rec)
        curr_wd_rec_metric = weewx.units.to_METRIC(curr_wd_rec)
        if 'outTemp' in curr_rec_metric:
            outTemp_C = curr_rec_metric['outTemp']
        else:
            outTemp_C = None
        if 'windchill' in curr_rec_metric:
            windchill_C = curr_rec_metric['windchill']
        else:
            windchill_C = None
        if 'humidex' in curr_wd_rec_metric:
            humidex_C = curr_wd_rec_metric['humidex']
        else:
            humidex_C = None
        heatColorWord = heatColorWords[0]
        if curr_rec_metric['outTemp'] is not None:
            if curr_rec_metric['outTemp'] > 32:
                if humidex_C is not None:
                    if humidex_C > 54:
                        heatColorWord = heatColorWords[1]
                    elif humidex_C > 45:
                        heatColorWord = heatColorWords[2]
                    elif humidex_C > 39:
                        heatColorWord = heatColorWords[4]
                    elif humidex_C > 29:
                        heatColorWord = heatColorWords[6]
                else:
                    heatColorWord = heatColorWords[0]
            elif windchill_C is not None:
                if windchill_C < 16:
                    if windchill_C < -18:
                        heatColorWord = heatColorWords[13]
                    elif windchill_C < -9:
                        heatColorWord = heatColorWords[12]
                    elif windchill_C < -1:
                        heatColorWord = heatColorWords[11]
                    elif windchill_C < 8:
                        heatColorWord = heatColorWords[10]
                    elif windchill_C < 16:
                        heatColorWord = heatColorWords[9]
                elif windchill_C >= 16 and outTemp_C <= 32:
                    if outTemp_C < 26:
                        heatColorWord = heatColorWords[8]
                    else:
                        heatColorWord = heatColorWords[7]
                else:
                    heatColorWord = heatColorWords[0]
            else:
                heatColorWord = heatColorWords[0]
        else:
            heatColorWord = heatColorWords[0]

        #
        # Feelslike
        #
        if outTemp_C is not None:
            if outTemp_C <= 16:
                feelsLike_vt = ValueTuple(windchill_C, 'degree_C', 'group_temperature')
            elif outTemp_C >= 27:
                feelsLike_vt = ValueTuple(humidex_C, 'degree_C', 'group_temperature')
            else:
                feelsLike_vt = ValueTuple(outTemp_C, 'degree_C', 'group_temperature')
        else:
            feelsLike_vt = ValueTuple(None, 'degree_C', 'group_temperature')
        feelsLike_vh = ValueHelper(feelsLike_vt,
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)

        #
        # Air density
        #
        if 'dewpoint' in curr_rec_metric:
            dpC = curr_rec_metric['dewpoint']
        else:
            dpC = None
        if 'pressure' in curr_rec_metric:
            Phpa = curr_rec_metric['pressure']
        else:
            Phpa = None
        if dpC is not None and outTemp_C is not None and Phpa is not None:
            Tk = outTemp_C + 273.15
            p = (0.99999683 + dpC *(-0.90826951E-2 + dpC * (0.78736169E-4 +
                dpC * (-0.61117958E-6 + dpC * (0.43884187E-8 +
                dpC * (-0.29883885E-10 + dpC * (0.21874425E-12 +
                dpC * (-0.17892321E-14 + dpC * (0.11112018E-16 +
                dpC * (-0.30994571E-19))))))))))
            Pv = 100 * 6.1078 / (p**8)
            Pd = Phpa * 100 - Pv
            density = round((Pd/(287.05 * Tk)) + (Pv/(461.495 * Tk)),3)
        else:
            density = 0

        #
        # Beaufort wind
        #
        if 'windSpeed' in curr_rec_metric:
            if curr_rec_metric['windSpeed'] is not None:
                wS = curr_rec_metric['windSpeed']
                if wS >= 117.4:
                    beaufort = 12
                    beaufortDesc = "Hurricane"
                elif wS >= 102.4:
                    beaufort = 11
                    beaufortDesc = "Violent Storm"
                elif wS >= 88.1:
                    beaufort = 10
                    beaufortDesc = "Storm"
                elif wS >= 74.6:
                    beaufort = 9
                    beaufortDesc = "Strong Gale"
                elif wS >= 61.8:
                    beaufort = 8
                    beaufortDesc = "Gale"
                elif wS >= 49.9:
                    beaufort = 7
                    beaufortDesc = "Moderate Gale"
                elif wS >= 38.8:
                    beaufort = 6
                    beaufortDesc = "Strong Breeze"
                elif wS >= 28.7:
                    beaufort = 5
                    beaufortDesc = "Fresh Breeze"
                elif wS >= 19.7:
                    beaufort = 4
                    beaufortDesc = "Moderate Breeze"
                elif wS >= 11.9:
                    beaufort = 3
                    beaufortDesc = "Gentle Breeze"
                elif wS >= 5.5:
                    beaufort = 2
                    beaufortDesc = "Light Breeze"
                elif wS >= 1.1:
                    beaufort = 1
                    beaufortDesc = "Light Air"
                else:
                    beaufort = 0
                    beaufortDesc = "Calm"
            else:
                beaufort = 0
                beaufortDesc = "Calm"
        else:
            beaufort = None
            beaufortDesc = "N/A"

        #
        # Wet bulb
        #
        if 'outHumidity' in curr_rec_metric:
            outHumidity = curr_rec_metric['outHumidity']
        else:
            outHumidity = None
        if outTemp_C is not None and outHumidity is not None and Phpa is not None:
            Tc = outTemp_C
            RH = outHumidity
            P = Phpa
            Tdc = ((  Tc - (14.55 + 0.114 *   Tc) * (1 - (0.01 *   RH)) - ((2.5 + 0.007 *   Tc) * (1 - (0.01 *   RH))) ** 3 - (15.9 + 0.117 *   Tc) * (1 - (0.01 *   RH)) ** 14))
            E = (6.11 * 10 ** (7.5 *   Tdc / (237.7 +   Tdc)))
            WBc = (((0.00066 *   P) *   Tc) + ((4098 *   E) / ((Tdc + 237.7) ** 2) *   Tdc)) / ((0.00066 *   P) + (4098 *   E) / ((  Tdc + 237.7) ** 2))
            WB_vt = ValueTuple(WBc, 'degree_C', 'group_temperature')
        else:
            WB_vt = ValueTuple(None, 'degree_C', 'group_temperature')
        WB_vh = ValueHelper(feelsLike_vt,
                            formatter=self.generator.formatter,
                            converter=self.generator.converter)

        #
        # Chandler Burning Index
        #
        if outHumidity is not None and outTemp_C is not None:
          cbi = max(0.0, round((((110 - 1.373 * outHumidity) - 0.54 * (10.20 - outTemp_C)) * (124 * 10**(-0.0142 * outHumidity)))/60,1))
        else:
          cbi = 0.0
        cbi_vt = ValueTuple(cbi, 'count', 'group_count')
        cbi_vh = ValueHelper(cbi_vt,
                             formatter=self.generator.formatter,
                             converter=self.generator.converter)
        if (cbi > 97.5):
          cbitext = "EXTREME"
        elif (cbi >="90"):
          cbitext = "VERY HIGH"
        elif (cbi >= "75"):
          cbitext = "HIGH"
        elif (cbi >= "50"):
          cbitext = "MODERATE"
        else:
          cbitext="LOW"

        #
        # Cloud base
        #
        altitude_vt = weewx.units.convert(self.generator.stn_info.altitude_vt, 'foot')
        if outTemp_C is not None and dpC is not None and altitude_vt[0] is not None:
            spread = outTemp_C - dpC
            cloudbase = max(0, 1000 * spread / 2.5 + altitude_vt[0])
        else:
            cloudbase = 0
        cloudbase_vt = ValueTuple(cloudbase, 'foot', 'group_altitude')
        cloudbase_vh = ValueHelper(cloudbase_vt,
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)

        #
        # Easter. Calculate date for Easter Sunday this year
        #
        def calcEaster(years):

            g = years % 19
            e = 0
            century = years / 100
            h = (century - century / 4 - (8 * century + 13) / 25 + 19 * g + 15) % 30
            i = h - (h / 28) * (1 - (h / 28) * (29 / (h + 1)) * ((21 - g) / 11))
            j = (years + years / 4 + i + 2 - century + century / 4) % 7
            p = i - j + e
            _days = 1 + (p + 27 + (p + 6) / 40) % 31
            _months = 3 + (p + 26) / 30
            Easter_dt = datetime.datetime(year=years, month=_months, day=_days)
            Easter_ts = time.mktime(Easter_dt.timetuple())
            return Easter_ts

        _years = date.today().year
        Easter_ts = calcEaster(_years)
        # Check to see if we have past this calculated date
        # If so we want next years date so increment year and recalculate
        if date.fromtimestamp(Easter_ts) < date.today():
            Easter_ts = calcEaster(_years + 1)
        Easter_vt = ValueTuple(Easter_ts, 'unix_epoch', 'group_time')
        Easter_vh = ValueHelper(Easter_vt,
                                formatter=self.generator.formatter,
                                converter=self.generator.converter)

        #
        # Barometer trend
        #
        if 'barometer' in curr_rec_metric and curr_rec_metric['barometer'] is not None:
            curr_baro_hpa = curr_rec_metric['barometer']
            # 1 hour trend
            rec_60 = db_lookup().getRecord(self.generator.gen_ts - 3600, 300)
            if rec_60:
                rec_60_metric = weewx.units.to_METRIC(rec_60)
                if 'barometer' in rec_60_metric and rec_60_metric['barometer'] is not None:
                    baro_60_hpa = rec_60_metric['barometer']
                    trend_60_hpa = curr_baro_hpa - baro_60_hpa
                    if trend_60_hpa >= 2:
                        trend_60 = "Rising Rapidly"
                    elif trend_60_hpa >= 0.7:
                        trend_60 = "Rising Slowly"
                    elif trend_60_hpa <= -2:
                        trend_60 = "Falling Rapidly"
                    elif trend_60_hpa <= -0.7:
                        trend_60 = "Falling Slowly"
                    else:
                        trend_60 = "Steady"
                else:
                    trend_60 = "N/A"
            else:
                trend_60 = "N/A"
            # 3 hour trend
            rec_180 = db_lookup().getRecord(self.generator.gen_ts - 10800, 300)
            if rec_180:
                rec_180_metric = weewx.units.to_METRIC(rec_180)
                if 'barometer' in rec_180_metric and rec_180_metric['barometer'] is not None:
                    baro_180_hpa = rec_180_metric['barometer']
                    trend_180_hpa = curr_baro_hpa - baro_180_hpa
                    if trend_180_hpa >= 2:
                        trend_180 = "Rising Rapidly"
                    elif trend_180_hpa >= 0.7:
                        trend_180 = "Rising Slowly"
                    elif trend_180_hpa <= -2:
                        trend_180 = "Falling Rapidly"
                    elif trend_180_hpa <= -0.7:
                        trend_180 = "Falling Slowly"
                    else:
                        trend_180 = "Steady"
                else:
                    trend_180 = "N/A"
            else:
                trend_180 = "N/A"
        else:
            trend_60 = "N/A"
            trend_180 = "N/A"

        #
        # System free memory
        #
        meminfo = {}
        try:
            f=open('/proc/meminfo')
            for line in f:
                meminfo[line.split(':')[0]] = line.split(':')[1].strip()
            freemem = meminfo['MemFree']
        except:
            freemem = None

        #
        # Time of next update
        #
        if 'interval' in curr_rec:
            if curr_rec['interval'] is not None:
                _next_update_ts = timespan.stop + 60.0 * curr_rec['interval']
            else:
                _next_update_ts = None
        else:
            _next_update_ts = None
        next_update_vt = ValueTuple(_next_update_ts, 'unix_epoch', 'group_time')
        next_update_vh = ValueHelper(next_update_vt,
                                     formatter=self.generator.formatter,
                                     converter=self.generator.converter)

        #
        # Latitude and Longitude
        #
        def ll_to_str(_ll_f):

            if _ll_f:
                _sign = math.copysign(1.0, _ll_f)
                (_min_f, _deg_i) = math.modf(abs(_ll_f))
                (_sec_f, _min_i) = math.modf(_min_f * 60.0)
                _sec_i = int(round(_sec_f * 60.0))
                if _sec_i == 60:
                    _min_i += 1
                    _sec_i = 0
                if _min_i == 60.0:
                    _deg_i += 1
                    _min_i = 0
                ll_str = "%d:%d:%d" % (_sign * _deg_i, _min_i, _sec_i)
            else:
                ll_str = "N/A"
            return ll_str

        # Latitude
        _lat_f = self.generator.stn_info.latitude_f
        lat_str = ll_to_str(_lat_f)

        # Longitude
        _long_f = self.generator.stn_info.longitude_f
        long_str = ll_to_str(_long_f)

        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'forecast_text':  forecast_text,
                                 'forecast_icon':  forecast_icon,
                                 'current_text':   current_text,
                                 'current_icon':   current_icon,
                                 'start_time':     starttime_vh,
                                 'nineamrain':     rain_vh,
                                 'heatColorWord':  heatColorWord,
                                 'feelsLike':      feelsLike_vh,
                                 'density':        density,
                                 'beaufort':       beaufort,
                                 'beaufortDesc':   beaufortDesc,
                                 'wetBulb':        WB_vh,
                                 'cbi':            cbi,
                                 'cbitext':        cbitext,
                                 'cloudbase':      cloudbase_vh,
                                 'Easter':         Easter_vh,
                                 'trend_60_baro':  trend_60,
                                 'trend_180_baro': trend_180,
                                 'freeMemory':     freemem,
                                 'next_update':    next_update_vh,
                                 'lat_dms':        lat_str,
                                 'long_dms':       long_str}

        t2 = time.time()
        logdbg2("wdSundryTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdTaggedStats(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with custom tagged stats
           drawn from stats database. Permits the syntax
           $stat_type.observation.agg_type where:
           stat_type is:
             weekdaily - week of stats aggregated by day
             monthdaily - month of stats aggregated by day
             yearmonthy - year of stats aggregated by month
           observation is any weewx observation recorded in the stats database
           eg outTemp or humidity
           agg_type is:
             maxQuery - returns maximums/highs over the aggregate period
             minQuery - returns minimums/lows over the aggregate period
             avgQuery - returns averages over the aggregate period
             sumQuery - returns sum over the aggregate period
             vecdirQuery - returns vector direction over the aggregate period

           Also supports the $stat_type.observation.exists and
           $stat_type.observation.has_data properties which are true if the
           relevant observation exists and has data respectively

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          A list of ValueHelpers for custom stat concerned as follows:
            weekdaily - list of 7 ValueHelpers. Item [0] is the earliest day,
                        item [6] is the current day
            monthdaily - list of 31 ValueHelpers. Item [0] is the day 31 days ago,
                         item [30] is the current day
            yearmonthy - list of 31 ValueHelpers. Item [0] is the month 12
                         months ago, item [11] is the current month

          So $weekdaily.outTemp.maxQuery.degree_F woudl return a list of the
          max temp in Fahrenheit for each day over the last 7 days.
          $weekdaily.outTemp.maxQuery[1].degree_C would return the max temp in
          Celcius of the day 6 days ago.
          """

        t1 = time.time()

        # Get a WDTaggedStats structure. This allows constructs such as
        # WDstats.monthdaily.outTemp.max
        WDstats = user.wdTaggedStats3.WdTimeBinder(db_lookup, timespan.stop,
                                                   formatter = self.generator.formatter,
                                                   converter = self.generator.converter)

        t2 = time.time()
        logdbg2("wdTaggedStats SLE executed in %0.3f seconds" % (t2-t1))

        return [WDstats]

class wdTaggedArchiveStats(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with custom tagged stats
           drawn from archive database. Permits the syntax
           $stat_type.observation.agg_type where:
           stat_type is:
             minute - hour of stats aggregated by minute
             fifteenminute - day of stats aggregated by 15 minutes
             hour - day of stats aggregated by hour
             sixhour - week of stats aggegated by 6 hours
           observation is any weewx observation recorded in the archive database
           eg outTemp or humidity
           agg_type is:
             maxQuery - returns maximums/highs over the aggregate period
             minQuery - returns minimums/lows over the aggregate period
             avgQuery - returns averages over the aggregate period
             sumQuery - returns sum over the aggregate period
             datetimeQuery - returns datetime over the aggregate period

           Also supports the $stat_type.observation.exists and
           $stat_type.observation.has_data properties which are true if the
           relevant observation exists and has data respectively

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          A list of ValueHelpers for custom stat concerned as follows:
            minute - list of 60 ValueHelpers. Item [0] is the minute commencing
                     60 minutes ago, item [59] is the minute immediately before
                     valid_timespan.stop. For archive periods greater than
                     60 seconds the intervening minutes between archive records
                     are extrapolated linearly.
            fifteenminute - list of 96 ValueHelpers. Item [0] is the 15 minute
                            period commencing 24 hours ago, item [95] is the
                            15 minute period ending at valid_timespan.stop.
            hour - list of 24 ValueHelpers. Item [0] is the hours commencing
                   24 hours ago, item [23] is the hour ending at
                   valid_timespan.stop.
            sixhour - list of 42 ValueHelpers. Item [0] is the 6 hour period
                      commencing 192 hours ago, item [41] is the 6 hour period
                      ending at valid_timespan.stop.

          So $fifteenminute.outTemp.maxQuery.degree_F would return a list of the
          max temp in Fahrenheit for each 15 minute period over the last 24 hours.
          $fifteenminute.outTemp.maxQuery[1].degree_C would return the max temp in
          Celcius of the 15 minute period commencing 23hr 45min ago.
          """

        t1 = time.time()

        # Get a WDTaggedStats structure. This allows constructs such as
        # WDstats.minute.outTemp.max
        WDarchivestats = user.wdTaggedStats3.WdArchiveTimeBinder(db_lookup,
                                                                 timespan.stop,
                                                                 formatter = self.generator.formatter,
                                                                 converter = self.generator.converter)
        t2 = time.time()
        logdbg2("wdTaggedArchiveStats SLE executed in %0.3f seconds" % (t2-t1))

        return [WDarchivestats]

class wdYestAlmanac(SearchList):
    """Class that implements the '$yestAlmanac' tag to support change of day
       length calcs.

    Parameters:
      SearchList:
    """

    def __init__(self, generator):
        t1 = time.time()

        SearchList.__init__(self, generator)

        celestial_ts = generator.gen_ts

        # For better accuracy, the almanac requires the current temperature
        # and barometric pressure, so retrieve them from the default archive,
        # using celestial_ts as the time

        temperature_C = pressure_mbar = None

        db = generator.db_binder.get_manager()
        ## NEED TO FIX - what if there is no record 24 hours ago
        if not celestial_ts:
            celestial_ts = db.lastGoodStamp() - 86400
        rec = db.getRecord(celestial_ts, max_delta=3600)

        if rec is not None:
            outTemp_vt = weewx.units.as_value_tuple(rec, 'outTemp')
            pressure_vt = weewx.units.as_value_tuple(rec, 'barometer')

            if not isinstance(outTemp_vt, weewx.units.UnknownType):
                temperature_C = weewx.units.convert(outTemp_vt, 'degree_C')[0]
            if not isinstance(pressure_vt, weewx.units.UnknownType):
                pressure_mbar = weewx.units.convert(pressure_vt, 'mbar')[0]
        if temperature_C is None: temperature_C = 15.0
        if pressure_mbar is None: pressure_mbar = 1010.0

        self.moonphases = generator.skin_dict.get('Almanac', {}).get('moon_phases', weeutil.Moon.moon_phases)

        altitude_vt = weewx.units.convert(generator.stn_info.altitude_vt, "meter")

        self.yestAlmanac = weewx.almanac.Almanac(celestial_ts,
                                                 generator.stn_info.latitude_f,
                                                 generator.stn_info.longitude_f,
                                                 altitude=altitude_vt[0],
                                                 temperature=temperature_C,
                                                 pressure=pressure_mbar,
                                                 moon_phases=self.moonphases,
                                                 formatter=generator.formatter)

        t2 = time.time()
        logdbg2("wdYestAlmanac SLE executed in %0.3f seconds" % (t2-t1))

class wdSkinDict(SearchList):
    """Simple class that makes skin settings available in reports."""

    def __init__(self, generator):
        t1 = time.time()

        SearchList.__init__(self, generator)
        self.skin_dict = generator.skin_dict

        t2 = time.time()
        logdbg2("wdSkinDict SLE executed in %0.3f seconds" % (t2-t1))

class wdMonthlyReportStats(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with various date/time tags
           used in WD monthly report template.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          month_name - abbreviated month name eg Dec of start of timespan
          month_long_name - long month name eg December of start of timespan
          month_number - month number eg 12 for December of start of timespan
          year_name - 4 digit year eg 2013 of start of timespan
          curr_minute - current minute of time of last record
          curr_hour - current hour of time of last record
          curr_day - day of time of last archive record
          curr_month - month of time of last archive record
          curr_year - year of time of last archive record
        """

        t1 = time.time()

        # Get a required times and convert to time tuples
        timespan_start_tt = time.localtime(timespan.start)
        stop_ts = db_lookup().lastGoodStamp()
        stop_tt = time.localtime(stop_ts)

        # Create a small dictionary with the tag names (keys) we want to use

        searchList = {'month_name':      time.strftime("%b", timespan_start_tt),
                      'month_long_name': time.strftime("%B", timespan_start_tt),
                      'month_number':    timespan_start_tt[1],
                      'year_name' :      timespan_start_tt[0],
                      'curr_minute':     stop_tt[4],
                      'curr_hour' :      stop_tt[3],
                      'curr_day':        stop_tt[2],
                      'curr_month':      stop_tt[1],
                      'curr_year':       stop_tt[0]}

        t2 = time.time()
        logdbg2("wdMonthlyReportStats SLE executed in %0.3f seconds" % (t2-t1))

        return [searchList]

class wdWindroseTags(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)
        try:
            self.period = int(generator.skin_dict['Extras']['WindrosePeriod'].get('period', 21600))
        except KeyError:
            self.period = 21600    # 6 hours

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with windrose data for
           customclientraw.txt (steelseries gauges).
           This extension queries the last x hours of windSpeed/windDir
           records and generates a 16 element list containing the windrose
           data. The windrose timeframe can be set in skin.conf and defaults
           to 6 hours.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          windroseData: A 16 element list containing the windrose data.
        """

        t1 = time.time()

        # Create windroseList container and initialise to all 0s
        windroseList = [0.0 for x in range(16)]
        # Get last x hours windSpeed obs as a ValueTuple. No need to
        # convert them as the steelseries code autoscales so untis are
        # meaningless.
        (time_start_vt, time_stop_vt, wind_speed_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop - self.period, timespan.stop), 'windSpeed')
        # Get last x hours windDir obs as a ValueTuple. Again no need to
        # convert them as the steelseries code autoscales so untis are
        # meaningless.
        (time_start_vt, time_stop_vt, wind_dir_vt) = db_lookup().getSqlVectors(TimeSpan(timespan.stop - self.period, timespan.stop), 'windDir')
        x = 0
        # Step through each windDir and add corresponding windSpeed to windroseList
        while x < len(wind_dir_vt[0]):
            # Only want to add windSpeed if both windSpeed and windDir have a vlaue
            if wind_speed_vt[0][x] is not None and wind_dir_vt[0][x] is not None:
                # Add the windSpeed value to the corresponding element of our windrose list
                windroseList[int((wind_dir_vt[0][x]+11.25)/22.5)%16] += wind_speed_vt[0][x]
            x += 1
        # Step through our windrose list and round all elements to
        # 1 decimal place
        y = 0
        while y < len(windroseList):
            windroseList[y] = round(windroseList[y],1)
            y += 1
        # Need to return a string of the list elements comma separated, no spaces and
        # bounded by [ and ]
        windroseData = '[' + ','.join(str(z) for z in windroseList) + ']'
        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'windroseData' : windroseData}

        t2 = time.time()
        logdbg2("wdWindroseTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdWindRunTags(SearchList):
    """ Search list extension to return windrun over variou speriods. Also
        returns max day windrun and the date on which this occurred.

        Whilst weewx supports windrun through inclusion of distance units and
        groups weewx only provides as cumulative daily windrun in each
        loop/archive record. This cumulative value is reset at midnight each
        day. Consequently, a SLE is required to provide windrun
        statistics/aggregates over various standard timespans.

        Definition:

        Windrun. The total distance of travelled wind over a period of time.
        Windrun is independent of any directional properties of the wind.
        For fixed periods windrun is calculated by the average wind speed over
        the period times the length of the period (eg 1 day). For variable
        length periods windrun is calculated by breaking the variable length
        period into a number of fixed length periods finding the sum of the
        periods time the average wind speed for the period. Special
        consideration is needed for partial periods.
    """

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """ Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

            Returns:
            day_windrun       : windrun from midnight to current time
            yest_windrun      : yesterdays windrun
            week_windrun      : windrun so far this weeke. Start of week as per
                                weewx.conf week_start setting
            seven_days_windrun: windrun over the last 7 days (today is included)
            month_windrun     : this months windrun to date
            year_windrun      : this years windrun to date
            alltime_windrun   : alltime windrun
            max_windrun         : max daily windrun seen
            max_windrun_ts      : timestamp (midnight) of max daily windrun
            max_year_windrun    : max daily windrun this year
            max_year_windrun_ts : timestamp (midnight) of max daily windrun
                                  this year
            max_month_windrun   : max daily windrun this month
            max_month_windrun_ts: timestamp (midnight) of max windrun this
                                  month
        """

        t1 = time.time()

        ##
        ## Get windSpeed units for use later
        ##

        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get the unit in use
        _usUnits = current_rec['usUnits']
        (windrun_type, windrun_group) = getStandardUnitType(_usUnits,
                                                            'windrun')
        (windSpeed_type, windSpeed_group) = getStandardUnitType(_usUnits,
                                                                'windSpeed')
        (dateTime_type, dateTime_group) = getStandardUnitType(_usUnits,
                                                              'dateTime')

        # Get timestamp for our first (earliest) and last record
        _first_ts = db_lookup().firstGoodStamp()
        _last_ts = timespan.stop

        ##
        ## Get timestamps for midnight at the start of our various periods
        ##
        # Get time obj for midnight
        _mn_t = datetime.time(0)
        # Get date obj for now
        _today_d = datetime.datetime.today()
        # Get ts for midnight at the end of period
        _mn_ts = weeutil.weeutil.startOfDay(timespan.stop)
        # Go back 24hr to get midnight at start of yesterday as a timestamp
        _mn_yest_ts = _mn_ts - 86400
        # Get our 'start of week' as a timestamp
        # First day of week depends on a setting in weewx.conf
        _week_start = int(self.generator.config_dict['Station'].get('week_start', 6))
        _day_of_week = _today_d.weekday()
        _delta = _day_of_week - _week_start
        if _delta < 0: _delta += 7
        _week_date = _today_d - datetime.timedelta(days=_delta)
        _week_dt = datetime.datetime.combine(_week_date, _mn_t)
        _mn_week_ts = time.mktime(_week_dt.timetuple())
        # Go back 7 days to get midnight 7 days ago as a timestamp
        _mn_seven_days_ts = _mn_ts - 604800
        # Get midnight 1st of the month as a datetime object and then get it as a
        # timestamp
        first_of_month_dt = get_first_day(_today_d)
        _mn_first_of_month_dt = datetime.datetime.combine(first_of_month_dt, _mn_t)
        _mn_first_of_month_ts = time.mktime(_mn_first_of_month_dt.timetuple())
        # Get midnight 1st of the year as a datetime object and then get it as a
        # timestamp
        _first_of_year_dt = get_first_day(_today_d, 0, 1-_today_d.month)
        _mn_first_of_year_dt = datetime.datetime.combine(_first_of_year_dt, _mn_t)
        _mn_first_of_year_ts = time.mktime(_mn_first_of_year_dt.timetuple())

        # Todays windrun
        # First get todays elapsed hours
        if _first_ts <= _mn_ts:
            # We have from midnight to now
            _day_hours = (_last_ts - _mn_ts)/3600.0
        else:
            # Our data starts some time after midnight
            _day_hours = (_last_ts - _first_ts)/3600.0
        # Get todays average wind speed
        windSpeed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_ts, _last_ts),
                                                    'windSpeed', 'avg')
        if windSpeed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _day_run = windSpeed_avg_vt.value * _day_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _day_run = windSpeed_avg_vt.value * _day_hours
        else:
            # No avg wind speed so set to None
            _day_run = None
        # Get our results as a ValueTuple
        day_run_vt = ValueTuple(_day_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        day_run_vh = ValueHelper(day_run_vt,
                                 formatter=self.generator.formatter,
                                 converter=self.generator.converter)

        # Yesterdays windrun
        # First get yesterdays elapsed hours
        if _first_ts <= _mn_yest_ts:
            # We have data for a full day
            _yest_hours = 24.0
        else:
            # Our data starts some time after midnight
            _yest_hours = (_mn_ts - _first_ts)/3600.0
        # Get yesterdays average wind speed
        windSpeed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_yest_ts, _mn_ts),
                                                    'windSpeed', 'avg')
        if windSpeed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _yest_run = windSpeed_avg_vt.value * _yest_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _yest_run = windSpeed_avg_vt.value * _yest_hours
        else:
            # No avg wind speed so set to None
            _yest_run = None
        # Get our results as a ValueTuple
        yest_run_vt = ValueTuple(_yest_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        yest_run_vh = ValueHelper(yest_run_vt,
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)


        # Week windrun
        # First get week elapsed hours
        if _first_ts <= _mn_week_ts:
            # We have data from midnight at start of week to now
            _week_hours = (_last_ts - _mn_week_ts)/3600.0
        else:
            # Our data starts some time after midnight on start of week
            _week_hours = (_last_ts - _first_ts)/3600.0
        # Get week average wind speed
        windSpeed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_week_ts, _last_ts),
                                                    'windSpeed', 'avg')
        if windSpeed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _week_run = windSpeed_avg_vt.value * _week_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _week_run = windSpeed_avg_vt.value * _week_hours
        else:
            # No avg wind speed so set to None
            _week_run = None
        # Get our results as a ValueTuple
        week_run_vt = ValueTuple(_week_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        week_run_vh = ValueHelper(week_run_vt,
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)

        # Seven days windrun
        # First get seven days elapsed hours
        if _first_ts <= _mn_seven_days_ts:
            # We have a data since midnight 7 days ago
            _seven_days_hours = 168.0
        else:
            # Our data starts some time after midnight
            _seven_days_hours = (_last_ts - _first_ts)/3600.0
        # Get 'seven days' average wind speed
        windSpeed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_seven_days_ts, _last_ts),
                                                    'windSpeed', 'avg')
        if windSpeed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _seven_days_run = windSpeed_avg_vt.value * _seven_days_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _seven_days_run = windSpeed_avg_vt.value * _seven_days_hours
        else:
            # No avg wind speed so set to None
            _seven_days_hours = None
        # Get our results as a ValueTuple
        seven_days_run_vt = ValueTuple(_seven_days_hours, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        seven_days_run_vh = ValueHelper(seven_days_run_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)

        # Month windrun
        # First get month elapsed hours
        if _first_ts <= _mn_first_of_month_ts:
            # We have a data since midnight on 1st of month
            _month_hours = (_last_ts - _mn_first_of_month_ts)/3600.0
        else:
            # Our data starts some time after midnight on 1st of month
            _month_hours = (_last_ts - _first_ts)/3600.0
        # Get month average wind speed
        windSpeed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_first_of_month_ts, _last_ts),
                                                    'windSpeed', 'avg')
        if windSpeed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _month_run = windSpeed_avg_vt.value * _month_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _month_run = windSpeed_avg_vt.value * _month_hours
        else:
            # No avg wind speed so set to None
            _month_run = None
        # Get our results as a ValueTuple
        month_run_vt = ValueTuple(_month_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        month_run_vh = ValueHelper(month_run_vt,
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)

        # Year windrun
        # First get year elapsed hours
        if _first_ts <= _mn_first_of_year_ts:
            # We have a data since midnight on 1 Jan
            _year_hours = (_last_ts - _mn_first_of_year_ts)/3600.0
        else:
            # Our data starts some time after midnight on 1 Jan
            _year_hours = (_last_ts - _first_ts)/3600.0
        # Get year average wind speed
        windSpeed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_first_of_year_ts, _last_ts),
                                                    'windSpeed', 'avg')
        if windSpeed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _year_run = windSpeed_avg_vt.value * _year_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _year_run = windSpeed_avg_vt.value * _year_hours
        else:
            # No avg wind speed so set to None
            _year_run = None
        # Get our results as a ValueTuple
        year_run_vt = ValueTuple(_year_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        year_run_vh = ValueHelper(year_run_vt,
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)

        # Alltime windrun
        # First get alltime elapsed hours
        _alltime_hours = (_last_ts - _first_ts)/3600.0
        # Get alltime average wind speed
        windSpeed_avg_vt = db_lookup().getAggregate(TimeSpan(_first_ts, _last_ts),
                                                    'windSpeed', 'avg')
        if windSpeed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _alltime_run = windSpeed_avg_vt.value * _alltime_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _alltime_run = windSpeed_avg_vt.value * _alltime_hours
        else:
            # No avg wind speed so set to None
            _alltime_run = None
        # Get our results as a ValueTuple
        alltime_run_vt = ValueTuple(_alltime_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        alltime_run_vh = ValueHelper(alltime_run_vt,
                                     formatter=self.generator.formatter,
                                     converter=self.generator.converter)

        #
        # Max day windrun over various periods (timespans)
        #

        # Alltime
        # Get alltime max day average wind excluding today and first day if its
        # a partial day
        if not isMidnight(_first_ts):
            _start_ts = startOfDay(_first_ts) + 86400
        else:
            _start_ts = _first_ts
        _row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed WHERE dateTime >= ? AND dateTime < ?", (_start_ts, _mn_ts))
        # Now get our max_day_windrun excluding first day and today
        if _row:
            if _row[0] is not None:
                _max_windrun_ts = _row[0]
                if _max_windrun_ts > _first_ts:
                    # Our data is for a full day
                    hours = 24.0
                else:
                    # Our data is for the first day in our archive and its a partial day
                    hours = (86400 - (_first_ts - _max_windrun_ts))/3600.0

                if _row[1] is not None:
                    if _usUnits == weewx.METRICWX:
                        # METRICWX so wind speed is m/s, div by 1000 for km
                        _max_windrun = _row[1] * hours / 1000.0
                    else:
                        # METRIC or US so its just a straight multiply
                        _max_windrun = _row[1] * hours
                else:
                    # No avg wind speed so set to None
                    _max_windrun = None
                    _max_windrun_ts = None
            else:
                # No max wind speed ts so set to None
                _max_windrun = None
                _max_windrun_ts = None
        else:
            # No result so set all to None
            _max_windrun_ts = None
            _max_windrun = None

        # Get our first days windrun and ts
        _first_mn_ts = startOfDay(_first_ts)
        _first_row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed WHERE dateTime = ?", (_first_mn_ts,))
        if _first_row:
            if _first_row[0] is not None:
                _first_windrun_ts = _first_row[0]
                hours = (_start_ts - _first_ts)/3600.0
                if _first_row[1] is not None:
                    if _usUnits == weewx.METRICWX:
                        # METRICWX so wind speed is m/s, div by 1000 for km
                        _first_windrun = _first_row[1] * hours / 1000.0
                    else:
                        # METRIC or US so its just a straight multiply
                        _first_windrun = _first_row[1] * hours
                else:
                    _first_windrun = None
                    _first_windrun_ts = None
            else:
                _first_windrun = None
                _first_windrun_ts = None
        else:
            _first_windrun = None
            _first_windrun_ts = None

        # Get today's windrun and ts.
        _today_windrun = _day_run
        _today_windrun_ts = _mn_ts if _day_run is not None else None

        # If today's partial day windrun is greater than max of any of previous
        # days then change our max_day_windrun
        if _max_windrun and _today_windrun:
            # We have values for both so compare
            if _today_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _today_windrun
                _max_windrun_ts = _today_windrun_ts
        elif _today_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _today_windrun
            _max_windrun_ts = _today_windrun_ts
        # If first day's windrun is greater than our max so far then change our
        # max_day_windrun
        if _max_windrun and _first_windrun:
            # We have values for both so compare
            if _first_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _first_windrun
                _max_windrun_ts = _first_windrun_ts
        elif _first_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _first_windrun
            _max_windrun_ts = _first_windrun_ts

        # Convert our results to ValueTuple and then ValueHelper
        max_windrun_vt = ValueTuple(_max_windrun, windrun_type, windrun_group)
        max_windrun_vh = ValueHelper(max_windrun_vt,
                                     formatter=self.generator.formatter,
                                     converter=self.generator.converter)
        max_windrun_ts_vt = ValueTuple(_max_windrun_ts,
                                       'unix_epoch',
                                       'group_time')
        max_windrun_ts_vh = ValueHelper(max_windrun_ts_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)

        # Year
        # Get ts and MAX(avg) of windSpeed from statsdb
        # ts value returned is ts for midnight on the day the MAX(avg) occurred
        _row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed WHERE dateTime >= ? AND dateTime < ?", (_mn_first_of_year_ts, _mn_ts))
        # Now get our max_day_windrun excluding first day and today
        if _row:
            if _row[0] is not None:
                _max_windrun_ts = _row[0]
                if _max_windrun_ts > _first_ts:
                    # Our data is for a full day
                    hours = 24.0
                else:
                    # Our data is for the first day in our archive and its a partial day
                    hours = (86400 - (_first_ts - _max_windrun_ts))/3600.0

                if _row[1] is not None:
                    if _usUnits == weewx.METRICWX:
                        # METRICWX so wind speed is m/s, div by 1000 for km
                        _max_windrun = _row[1] * hours / 1000.0
                    else:
                        # METRIC or US so its just a straight multiply
                        _max_windrun = _row[1] * hours
                else:
                    # No avg wind speed so set to None
                    _max_windrun = None
                    _max_windrun_ts = None
            else:
                # No max wind speed ts so set to None
                _max_windrun = None
                _max_windrun_ts = None
        else:
            # No result so set all to None
            _max_windrun_ts = None
            _max_windrun = None

        # Get our first days windrun and ts
        if _first_ts > _mn_first_of_year_ts:
            # we have a partial day that will not have been included
            _first_mn_ts = startOfDay(_first_ts)
            _first_row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed WHERE dateTime = ?", (_first_mn_ts,))
            if _first_row:
                if _first_row[0] is not None:
                    _first_windrun_ts = _first_row[0]
                    hours = (86400 - (_first_ts - _first_mn_ts))/3600.0
                    if _first_row[1] is not None:
                        if _usUnits == weewx.METRICWX:
                            # METRICWX so wind speed is m/s, div by 1000 for km
                            _first_windrun = _first_row[1] * hours / 1000.0
                        else:
                            # METRIC or US so its just a straight multiply
                            _first_windrun = _first_row[1] * hours
                    else:
                        _first_windrun = None
                        _first_windrun_ts = None
                else:
                    _first_windrun = None
                    _first_windrun_ts = None
            else:
                _first_windrun = None
                _first_windrun_ts = None
        else:
            _first_windrun = None
            _first_windrun_ts = None

        # Get today's windrun and ts.
        _today_windrun = _day_run
        _today_windrun_ts = _mn_ts if _day_run is not None else None

        # If today's partial day windrun is greater than max of any of previous
        # days then change our max_day_windrun
        if _max_windrun and _today_windrun:
            # We have values for both so compare
            if _today_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _today_windrun
                _max_windrun_ts = _today_windrun_ts
        elif _today_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _today_windrun
            _max_windrun_ts = _today_windrun_ts
        # If first day's windrun is greater than our max so far then change our
        # max_day_windrun
        if _max_windrun and _first_windrun:
            # We have values for both so compare
            if _first_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _first_windrun
                _max_windrun_ts = _first_windrun_ts
        elif _first_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _first_windrun
            _max_windrun_ts = _first_windrun_ts

        # Convert our results to ValueTuple and then ValueHelper
        max_year_windrun_vt = ValueTuple(_max_windrun,
                                         windrun_type,
                                         windrun_group)
        max_year_windrun_vh = ValueHelper(max_year_windrun_vt,
                                          formatter=self.generator.formatter,
                                          converter=self.generator.converter)
        max_year_windrun_ts_vt = ValueTuple(_max_windrun_ts,
                                            'unix_epoch',
                                            'group_time')
        max_year_windrun_ts_vh = ValueHelper(max_year_windrun_ts_vt,
                                             formatter=self.generator.formatter,
                                             converter=self.generator.converter)

        # Month
        # Get ts and MAX(avg) of windSpeed from statsdb
        # ts value returned is ts for midnight on the day the MAX(avg) occurred
        _row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed WHERE dateTime >= ? AND dateTime < ?", (_mn_first_of_month_ts, _mn_ts))
        # Now get our max_day_windrun excluding first day and today
        if _row:
            if _row[0] is not None:
                _max_windrun_ts = _row[0]
                if _max_windrun_ts > _first_ts:
                    # Our data is for a full day
                    hours = 24.0
                else:
                    # Our data is for the first day in our archive and its a partial day
                    hours = (86400 - (_first_ts - _max_windrun_ts))/3600.0

                if _row[1] is not None:
                    if _usUnits == weewx.METRICWX:
                        # METRICWX so wind speed is m/s, div by 1000 for km
                        _max_windrun = _row[1] * hours / 1000.0
                    else:
                        # METRIC or US so its just a straight multiply
                        _max_windrun = _row[1] * hours
                else:
                    # No avg wind speed so set to None
                    _max_windrun = None
                    _max_windrun_ts = None
            else:
                # No max wind speed ts so set to None
                _max_windrun = None
                _max_windrun_ts = None
        else:
            # No result so set all to None
            _max_windrun_ts = None
            _max_windrun = None

        # Get our first days windrun and ts
        if _first_ts > _mn_first_of_month_ts:
            # we have a partial day that will not have been included
            _first_mn_ts = startOfDay(_first_ts)
            _first_row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed WHERE dateTime = ?", (_first_mn_ts,))
            if _first_row:
                if _first_row[0] is not None:
                    _first_windrun_ts = _first_row[0]
                    hours = (86400 - (_first_ts - _first_mn_ts))/3600.0
                    if _first_row[1] is not None:
                        if _usUnits == weewx.METRICWX:
                            # METRICWX so wind speed is m/s, div by 1000 for km
                            _first_windrun = _first_row[1] * hours / 1000.0
                        else:
                            # METRIC or US so its just a straight multiply
                            _first_windrun = _first_row[1] * hours
                    else:
                        _first_windrun = None
                        _first_windrun_ts = None
                else:
                    _first_windrun = None
                    _first_windrun_ts = None
            else:
                _first_windrun = None
                _first_windrun_ts = None
        else:
            _first_windrun = None
            _first_windrun_ts = None

        # Get today's windrun and ts.
        _today_windrun = _day_run
        _today_windrun_ts = _mn_ts if _day_run is not None else None

        # If today's partial day windrun is greater than max of any of previous
        # days then change our max_day_windrun
        if _max_windrun and _today_windrun:
            # We have values for both so compare
            if _today_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _today_windrun
                _max_windrun_ts = _today_windrun_ts
        elif _today_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _today_windrun
            _max_windrun_ts = _today_windrun_ts
        # If first day's windrun is greater than our max so far then change our
        # max_day_windrun
        if _max_windrun and _first_windrun:
            # We have values for both so compare
            if _first_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _first_windrun
                _max_windrun_ts = _first_windrun_ts
        elif _first_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _first_windrun
            _max_windrun_ts = _first_windrun_ts

        # Convert our results to ValueTuple and then ValueHelper
        max_month_windrun_vt = ValueTuple(_max_windrun,
                                          windrun_type,
                                          windrun_group)
        max_month_windrun_vh = ValueHelper(max_month_windrun_vt,
                                           formatter=self.generator.formatter,
                                           converter=self.generator.converter)
        max_month_windrun_ts_vt = ValueTuple(_max_windrun_ts,
                                             'unix_epoch',
                                             'group_time')
        max_month_windrun_ts_vh = ValueHelper(max_month_windrun_ts_vt,
                                              formatter=self.generator.formatter,
                                              converter=self.generator.converter)

        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'day_windrun':            day_run_vh,
                                 'yest_windrun':           yest_run_vh,
                                 'week_windrun':           week_run_vh,
                                 'seven_days_windrun':     seven_days_run_vh,
                                 'month_windrun':          month_run_vh,
                                 'year_windrun':           year_run_vh,
                                 'alltime_windrun':        alltime_run_vh,
                                 'month_max_windrun':      max_month_windrun_vh,
                                 'month_max_windrun_ts':   max_month_windrun_ts_vh,
                                 'year_max_windrun':       max_year_windrun_vh,
                                 'year_max_windrun_ts':    max_year_windrun_ts_vh,
                                 'alltime_max_windrun':    max_windrun_vh,
                                 'alltime_max_windrun_ts': max_windrun_ts_vh}

        t2 = time.time()
        logdbg2("wdWindRunTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdHourRainTags(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """ Returns a search list extension with the maximum 1 hour rainfall
            and the time this occurred for current day.

            A sliding 1 hour window is used to find the 1 hour window that has
            the max rainfall. the 1 hour window aligns on the archive period
            boundary (ie for 5 min archive period the window could be from
            01:05 to 02:05 but not 01:03 to 02:03). The time returned is the
            end time of the one hour window with the max rain. As the end time
            is returned, the 1 hour window starts at 23:00:01 the previous day
            and slides to 23:00 on the current day.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          maxHourRainToday: Max rain that fell in any 1 hour window today.
                            Returned as a ValueHelper so that standard
                            Weewx unit conversion and formatting options
                            are available.
          maxHourRainTodayTime: End time of 1 hour window during which max
                                1 hour rain fell today. Returned as a
                                ValueHelper so that standard Weewx unit
                                conversion and formatting options are available.
        """

        t1 = time.time()

        # Get time obj for midnight
        midnight_t = datetime.time(0)
        # Get datetime obj for now
        today_dt = datetime.datetime.today()
        # Get datetime obj for midnight at start of today
        midnight_dt = datetime.datetime.combine(today_dt, midnight_t)
        # Our start is 23:00:01 yesterday so go back 0:59:59
        start_dt = midnight_dt - datetime.timedelta(minutes=59, seconds=59)
        # Get it as a timestamp
        start_ts = time.mktime(start_dt.timetuple())
        # Our end time is 23:00 today so go forward 23 hours
        end_dt = midnight_dt + datetime.timedelta(hours=23)
        # Get it as a timestamp
        end_ts = time.mktime(end_dt.timetuple())
        # Get midnight as a timestamp
        midnight_ts = time.mktime(midnight_dt.timetuple())
        # enclose our query in a try..except block in case the earlier records
        # do not exist
        try:
            (time_start_vt, time_stop_vt, rain_vt) = db_lookup().getSqlVectors(weeutil.weeutil.TimeSpan(start_ts, end_ts), 'rain')
        except:
            loginf("wdHourRainTags: getSqlVectors exception")
        # set a few variables beforehand
        hour_start_ts = None
        hour_rain = []
        max_hour_rain = 0
        max_hour_rain_ts = midnight_ts
        # step through our records
        for time_t, rain_t in zip(time_stop_vt[0], rain_vt[0]):
            if time_t is not None and hour_start_ts is None: # our first non-None record
                hour_start_ts = time_t
                hour_rain.append([time_t, rain_t if rain_t is not None else 0.0])
            elif time_t is not None: # subsequent non-None records
                # add on our new rain record
                hour_rain.append([time_t, rain_t if rain_t is not None else 0.0])
                # delete any records older than 1 hour
                old_ts = time_t - 3600
                hour_rain = [r for r in hour_rain if  r[0] > old_ts]
                # get the total rain for the hour in our list
                this_hour_rain = sum(rr[1] for rr in hour_rain)
                # if it is more than our current max then update our stats
                if this_hour_rain > max_hour_rain:
                    max_hour_rain = this_hour_rain
                    max_hour_rain_ts = time_t
        # wrap our results as ValueHelpers
        max_hour_rain_vh = ValueHelper((max_hour_rain, rain_vt[1], rain_vt[2]),
                                       formatter=self.generator.formatter,
                                       converter=self.generator.converter)
        max_hour_rain_time_vh = ValueHelper((max_hour_rain_ts, time_stop_vt[1], time_stop_vt[2]),
                                            formatter=self.generator.formatter,
                                            converter=self.generator.converter)
        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'maxHourRainToday': max_hour_rain_vh,
                                 'maxHourRainTodayTime': max_hour_rain_time_vh}

        t2 = time.time()
        logdbg2("wdHourRainTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdGdDays(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)
        # Get temperature group - determines whether we return GDD in F or C
        # Enclose in try..except just in case. Default to degree_C if any errors
        try:
            self.temp_group = generator.skin_dict['Units']['Groups'].get('group_temperature', 'degree_C')
        except KeyError:
            self.temp_group = 'degree_C'
        # Get GDD base temp and save as a ValueTuple
        # Enclose in try..except just in case. Default to 10 deg C if any errors
        try:
            _base_t = weeutil.weeutil.option_as_list(generator.skin_dict['Extras']['GDD'].get('base', (10, 'degree_C')))
            self.gdd_base_vt = (float(_base_t[0]), _base_t[1], 'group_temperature')
        except KeyError:
            self.gdd_base_vt = (10.0, 'degree_C', 'group_temperature')

    def get_extension_list(self, timespan, db_lookup):
        """Returns Growing Degree Days tags.

           Returns a number representing to date Growing Degree Days (GDD) for
           various periods. GDD can be represented as GGD Fahrenheit (GDD F) or
           GDD Celsius (GDD C), 5 GDD C = 9 GDD F. As the standard
           Fahrenheit/Celsius conversion formula cannot be used to convert
           between GDD F and GDD C Weew ValueTuples cannot be used for the
           results and hence the results are returned in the group_temperature
           units specified in the associated skin.conf.

           The base temperature used in calculating GDD can be set using the
           'base' parameter under [Extras][[GDD]] in the associated skin.conf
           file. The base parameter consists of a numeric value followed by a
           unit string eg 10, degree_C or 50, degree_F. If the parameter is
           omitted or cannot be decoded then a default of 10, degree_C is used.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          month_gdd:    Growing Degree Days to date this month. Numeric value
                        only, not a ValueTuple.
          year_gdd:     Growing Degree Days to date this year. Numeric value
                        only, not a ValueTuple.
        """

        t1 = time.time()

        ##
        ## Get units for use later with ValueHelpers
        ##

        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get the unit in use for each group
        (outTemp_type, outTemp_group) = getStandardUnitType(current_rec['usUnits'], 'outTemp')

        ##
        ## Get timestamps we need for the periods of interest
        ##
        # Get ts for midnight at the end of period
        _mn_stop_ts = weeutil.weeutil.startOfDay(timespan.stop)
        # Get time obj for midnight
        _mn_t = datetime.time(0)
        # Get datetime obj for now
        _today_dt = datetime.datetime.today()
        # Get midnight 1st of the month as a datetime object and then get it as a
        # timestamp
        first_of_month_dt = get_first_day(_today_dt)
        _mn_first_of_month_dt = datetime.datetime.combine(first_of_month_dt, _mn_t)
        _mn_first_of_month_ts = time.mktime(_mn_first_of_month_dt.timetuple())
        # Get midnight 1st of the year as a datetime object and then get it as a
        # timestamp
        _first_of_year_dt = get_first_day(_today_dt, 0, 1-_today_dt.month)
        _mn_first_of_year_dt = datetime.datetime.combine(_first_of_year_dt, _mn_t)
        _mn_first_of_year_ts = time.mktime(_mn_first_of_year_dt.timetuple())

        interDict = {'start' : _mn_first_of_month_ts,
                     'stop'  : _mn_stop_ts-1}
        _row = db_lookup().getSql("SELECT SUM(max), SUM(min), COUNT(*) FROM archive_day_outTemp WHERE dateTime >= ? AND dateTime < ? ORDER BY dateTime", (_mn_first_of_month_ts, _mn_stop_ts-1))
        try:
            _t_max_sum = _row[0]
            _t_min_sum = _row[1]
            _count = _row[2]
            _month_gdd = (_t_max_sum + _t_min_sum)/2 - weewx.units.convert(self.gdd_base_vt, outTemp_type)[0] * _count
            if outTemp_type == self.temp_group:  # so our input is in the same units as our output
                _month_gdd = round(_month_gdd, 1)
            elif self.temp_group == 'degree_C':     # input if deg F and but want output in deg C
                _month_gdd = round(_month_gdd * 1.8, 1)
            else:   # input if deg C and but want output in deg F
                _month_gdd = round(_month_gdd * 5 / 9, 1)
            if _month_gdd < 0.0:
                _month_gdd = 0.0
        except:
            _month_gdd = None
        interDict = {'start' : _mn_first_of_year_ts,
                     'stop'  : _mn_stop_ts-1}
        _row = db_lookup().getSql("SELECT SUM(max), SUM(min), COUNT(*) FROM archive_day_outTemp WHERE dateTime >= ? AND dateTime < ? ORDER BY dateTime", (_mn_first_of_year_ts, _mn_stop_ts-1))
        try:
            _t_max_sum = _row[0]
            _t_min_sum = _row[1]
            _count = _row[2]
            _year_gdd = (_t_max_sum + _t_min_sum)/2 - weewx.units.convert(self.gdd_base_vt, outTemp_type)[0] * _count
            if outTemp_type == self.temp_group:  # so our input is in the same units as our output
                _year_gdd = round(_year_gdd, 1)
            elif self.temp_group == 'degree_C':     # input if deg F and but want output in deg C
                _year_gdd = round(_year_gdd * 1.8, 1)
            else:   # input if deg C and but want output in deg F
                _year_gdd = round(_year_gdd * 5 / 9, 1)
            if _year_gdd < 0.0:
                _year_gdd = 0.0
        except:
            _year_gdd = None

        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'month_gdd': _month_gdd,
                                 'year_gdd': _year_gdd
                                }

        t2 = time.time()
        logdbg2("wdGdDays SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdForToday(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns max and min temp for this day as well as the year each
           occurred.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          max_temp_today: Max temperature for this day of year from all
                          recorded data.
          max_temp_today_year: Year that max temperature for this day occurred.
          min_temp_today: Min temperature for this day of year from all
                          recorded data.
          min_temp_today_year: Year that min temperature for this day occurred.
        """

        t1 = time.time()

        ##
        ## Get units for use later with ValueHelpers
        ##

        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get the unit in use for each group
        (outTemp_type, outTemp_group) = getStandardUnitType(current_rec['usUnits'], 'outTemp')

        ##
        ## Get the dates/times we require for our queries
        ##

        # Get timestamp for our first (earliest) record
        _first_good_ts = db_lookup().firstGoodStamp()
        # as a date object
        _first_good_d = datetime.date.fromtimestamp(_first_good_ts)
        # year of first (earliest) record
        _first_good_year = _first_good_d.year
        # get our stop time as a date object
        _stop_d = datetime.date.fromtimestamp(timespan.stop)
        # get our stop month and day
        _stop_month = _stop_d.month
        _stop_day = _stop_d.day
        # get a date object for todays day/month in the year of our first
        # (earliest) record
        _today_first_year_d = _stop_d.replace(year=_first_good_year)
        # Get a date object for the first occurrence of current day/month in
        # our recorded data. Need to handle Leap years differently
        if _stop_month != 2 or _stop_day != 29: # if its anything but 29 Feb
                                                # then its either this year or
                                                # next
            # do we have day/month in this year or will we have to look later
            if _today_first_year_d < _first_good_d:
                # No - jump to next year
                _today_first_year_d = _stop_d.replace(year=_first_good_year + 1)
        else:   # its 29 Feb so we need to find a leap year
            # do we have 29 Feb in this year of data? If not start by trying
            # next year, if we do lets try this year
            if _today_first_year_d < _first_good_d:
                _year = _first_good_d.year + 1
            else:
                _year = _first_good_d.year
            # check for a leap year and if not increment our year
            while not calendar.isleap(_year):
                _year += 1
            # get our date object with a leap year
            _today_first_year_d = _stop_d.replace(year=_year)

        # get our start and stop timestamps
        _start_ts = time.mktime(_today_first_year_d.timetuple())
        _stop_ts = timespan.stop
        # set our max/min and times
        _max_temp_today = None
        _max_temp_today_ts = None
        _min_temp_today = None
        _min_temp_today_ts = None

        # call our generator to step through the designated day/month each year
        for _ts in doygen(_start_ts, _stop_ts):
            # Set a dictionary with our start and stop time for the query
            interDict = {'start': _ts,
                         'stop':  _ts + 86399}
            # Execute our query. The answer is a ValueTuple in _row[0]
            _row = db_lookup().getSql("SELECT datetime, max, min FROM archive_day_outTemp WHERE dateTime >= %(start)s AND dateTime < %(stop)s" % interDict)
            if _row is not None:
                # update our max temp and timestamp if necessary
                if _max_temp_today is None:
                    if _row[1] is not None:
                        _max_temp_today = _row[1]
                        _max_temp_today_ts = _row[0]
                else:
                    if _row[1] > _max_temp_today:
                        _max_temp_today = _row[1]
                        _max_temp_today_ts = _row[0]
                # update our min temp and timestamp if necessary
                if _min_temp_today is None:
                    if _row[2] is not None:
                        _min_temp_today = _row[2]
                        _min_temp_today_ts = _row[0]
                else:
                    if _row[2] < _min_temp_today:
                        _min_temp_today = _row[2]
                        _min_temp_today_ts = _row[0]

        # get our max/min as ValueTuples
        _max_temp_today_vt = (_max_temp_today, outTemp_type, outTemp_group)
        _min_temp_today_vt = (_min_temp_today, outTemp_type, outTemp_group)
        # convert them to ValueHelpers
        _max_temp_today_vh = ValueHelper(_max_temp_today_vt,
                                         formatter=self.generator.formatter,
                                         converter=self.generator.converter)
        _min_temp_today_vh = ValueHelper(_min_temp_today_vt,
                                         formatter=self.generator.formatter,
                                         converter=self.generator.converter)
        # get our years of max/min
        _max_temp_today_year = datetime.date.fromtimestamp(_max_temp_today_ts).timetuple()[0] if _max_temp_today_ts is not None else None
        _min_temp_today_year = datetime.date.fromtimestamp(_min_temp_today_ts).timetuple()[0] if _min_temp_today_ts is not None else None

        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'max_temp_today':      _max_temp_today_vh,
                                 'max_temp_today_year': _max_temp_today_year,
                                 'min_temp_today':      _min_temp_today_vh,
                                 'min_temp_today_year': _min_temp_today_year,
                                }

        t2 = time.time()
        logdbg2("wdForToday SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdRainThisDay(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns rain to date for this time last month and this time
           last year.

           Defining 'this time last month/year' presents some challenges when
           the previous month has a different nubmer of days to the present
           month. In this SLE the following algorithm is used to come up with
           'this time last month/year':

           - If 'this date' last month or last year is invalid (eg 30 Feb) then
             last day of month concerned is used.
           - If it is the last day of this month (eg 30 Nov) then last day of
             previous month is used.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          rain_this_time_last_month: Total month rainfall to date for this time last month
          rain_this_time_last_year: Total year rainfall to date for this time last year
        """

        t1 = time.time()

        ##
        ## Get units for use later with ValueHelpers
        ##

        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get the rain units
        (rain_type, rain_group) = getStandardUnitType(current_rec['usUnits'], 'rain')

        ##
        ## Get the dates/times we require for our queries
        ##

        # Get timestamp for our first (earliest) record
        _first_good_ts = db_lookup().firstGoodStamp()
        # get midnight as a time object
        _mn_t = datetime.time(0)
        # get our stop time as a datetime object
        _stop_dt = datetime.datetime.fromtimestamp(timespan.stop)
        # get a datetime object for 1 month before our stop time
        _month_ago_dt = get_date_ago(_stop_dt, 1)
        # get date time object for midnight of that day
        _mn_month_ago_dt = datetime.datetime.combine(_month_ago_dt, _mn_t)
        # get timestamp for midnight of that day
        _mn_month_ago_td = _mn_month_ago_dt - datetime.datetime.fromtimestamp(0)
        _mn_month_ago_ts = _mn_month_ago_td.days * 86400 + _mn_month_ago_td.seconds
        # get datetime object for 1st of that month
        _first_month_ago_dt = get_first_day(_month_ago_dt)
        # get date time object for midnight on the 1st of that month
        _mn_first_month_ago_dt = datetime.datetime.combine(_first_month_ago_dt, _mn_t)
        # get timestamp for midnight on the 1st of that month
        _mn_first_month_ago_td = _mn_first_month_ago_dt - datetime.datetime.fromtimestamp(0)
        _mn_first_month_ago_ts = _mn_first_month_ago_td.days * 86400 + _mn_first_month_ago_td.seconds
        # get a datetime object for 1 year before our stop time
        _year_ago_dt = get_date_ago(_stop_dt, 12)
        # get a datetime object for midnight of that day
        _mn_year_ago_dt = datetime.datetime.combine(_year_ago_dt, _mn_t)
        # get a timestamp for midnight of that day
        _mn_year_ago_td = _mn_year_ago_dt - datetime.datetime.fromtimestamp(0)
        _mn_year_ago_ts = _mn_year_ago_td.days * 86400 + _mn_year_ago_td.seconds
        # get datetime object for 1 Jan of that year
        _first_year_ago_dt = get_first_day(_year_ago_dt, 0, 1-_year_ago_dt.month)
        # get a datetime object for midnight of that day
        _mn_first_year_ago_dt = datetime.datetime.combine(_first_year_ago_dt, _mn_t)
        # get a timestamp for midnight of that day
        _mn_first_year_ago_td = _mn_first_year_ago_dt - datetime.datetime.fromtimestamp(0)
        _mn_first_year_ago_ts = _mn_first_year_ago_td.days * 86400 + _mn_first_year_ago_td.seconds
        # get todays elapsed seconds
        today_seconds = _stop_dt.hour * 3600 + _stop_dt.minute * 60 + _stop_dt.second

        ##
        ## Month ago queries
        ##
        ## Month ago results are derived from 2 queries, first a query on
        ## statsdb to get the total rainfall from 1st of previous month to
        ## midnight this day last month and secondly a query on archive to
        ## get the total rain from midnight a month ago to this time a month
        ## ago. 2 part query is used as it is (mostly) substantially faster
        ## than a single query on archive.

        # Get start/stop parameters for our 'month ago' query

        # Start time for stats query is midnight on the 1st of previous month
        _start_stats_ts = _mn_first_month_ago_ts
        # Start time for our archive query is 1 second after midnight of this
        # day 1 month ago
        _start_archive_ts = _mn_month_ago_ts + 1
        # Stop time for our stats query is 1 second before midnight on the this
        # day 1 month ago
        _stop_stats_ts = _mn_month_ago_ts - 1
        # Stop time for our archive query is this time on this day 1 month ago
        _stop_archive_ts = _mn_month_ago_ts + today_seconds

        # Do we have data for last month ?
        if _first_good_ts <= _stop_archive_ts:
            if _first_good_ts <= _stop_stats_ts:
                # Set a dictionary with our start and stop time for the stats query
                interDict = {'start': _start_stats_ts,
                             'stop':  _stop_stats_ts}
                # Execute our stats query. The answer is a ValueTuple in _row[0]
                _row = db_lookup().getSql("SELECT SUM(sum) FROM archive_day_rain WHERE dateTime >= ? AND dateTime < ?", (_start_stats_ts, _stop_stats_ts))
            else:
                _row = (None,)
            if today_seconds != 0:  # ie it's not midnight
                # archive db query aggregate interval is the period from midnight until
                # this time less 1 second
                archive_agg = today_seconds - 1
                # execute our archive query, rain_vt is a ValueTuple with our result
                (time_start_vt, time_stop_vt, rain_vt) = db_lookup().getSqlVectors(TimeSpan(_start_archive_ts, _stop_archive_ts), 'rain', 'sum', archive_agg)
            else:
                rain_vt = ([None,], rain_type, rain_group)
        else:
            _row = (None,)
            rain_vt = ([None,], rain_type, rain_group)

        # add our two query results being careful in case or both is None
        # filter is slower than nested if..else but what's a few milliseconds
        # for the sake of neater code
        if rain_vt[0] != []:
            month_rain_vt = ((sum(filter(None, [rain_vt[0][0],_row[0]])),rain_type, rain_group) if not (rain_vt[0][0] is None or _row[0] is None) else (None, None, None))
            month_rain_vh = ValueHelper(month_rain_vt, formatter=self.generator.formatter, converter=self.generator.converter)
        else:
            month_rain_vh = ValueHelper((None, None, None), formatter=self.generator.formatter, converter=self.generator.converter)

        ##
        ## Year ago queries
        ##
        ## Year ago results are derived from 2 queries, first a query on
        ## statsdb to get the total rainfall from 1st Jan to midnight this day
        ## last year and secondly a query on archive to get the total rain
        ## from midnight a year ago to this time a year ago. 2 part query is
        ## used as it is (mostly) substantially faster than a single query on
        ## archive.

        # Get parameters for our 'year ago' queries

        # Start time for stats query is midnight on the 1st of Jan the previous
        # year
        _start_stats_ts = _mn_first_year_ago_ts
        # Start time for our archive query is 1 second after midnight of this
        # day 1 year ago
        _start_archive_ts = _mn_year_ago_ts + 1
        # Stop time for our stats query is 1 second before midnight on the this
        # day 1 year ago
        _stop_stats_ts = _mn_year_ago_ts - 1
        # Stop time for our archive query is this time on this day 1 year ago
        _stop_archive_ts = _mn_year_ago_ts + today_seconds

        # Do we have data for last year ?
        if _first_good_ts <= _stop_archive_ts:
            if _first_good_ts <= _stop_stats_ts:
                # Set a dictionary with our start and stop time for the stats query
                interDict = {'start': _start_stats_ts,
                             'stop':  _stop_stats_ts}
                # Execute our stats query. The answer is a ValueTuple in _row[0]
                _row = db_lookup().getSql("SELECT SUM(sum) FROM archive_day_rain WHERE dateTime >= ? AND dateTime < ?", (_start_stats_ts, _stop_stats_ts))
            else:
                _row = (None,)
            if today_seconds != 0:  # ie it's not midnight
                # archive db query aggregate interval is the period from midnight until
                # this time less 1 second
                archive_agg = today_seconds - 1
                # execute our archive query, rain_vt is a ValueTuple with our result
                (time_start_vt, time_stop_vt, rain_vt) = db_lookup().getSqlVectors(TimeSpan(_start_archive_ts, _stop_archive_ts), 'rain', 'sum', archive_agg)
            else:
                rain_vt = ([0,], rain_type, rain_group)
        else:
            _row = (None,)
            rain_vt = ([None,], rain_type, rain_group)

        # add our two query results being careful in case or both is None
        # filter is slower than nested if..else but what's a few milliseconds
        # for the sake of neater code
        if rain_vt[0] != []:
            year_rain_vt = ((sum(filter(None, [rain_vt[0][0],_row[0]])),rain_type, rain_group) if not (rain_vt[0][0] is None or _row[0] is None) else (None, None, None))
            year_rain_vh = ValueHelper(year_rain_vt,
                                       formatter=self.generator.formatter,
                                       converter=self.generator.converter)
        else:
            year_rain_vh = ValueHelper((None, None, None),
                                       formatter=self.generator.formatter,
                                       converter=self.generator.converter)

        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'rain_this_time_last_month' : month_rain_vh,
                                 'rain_this_time_last_year'  : year_rain_vh}

        t2 = time.time()
        logdbg2("wdRainThisDay SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdRainDays(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns various tags related to longest periods of rainy/dry days.

           This SLE uses the stats database daily rainfall totals to determine
           the longest runs of consecutive dry or wet days over various periods
           (month, year, alltime). The SLE also determines the start date of
           each run.

           Period (xxx_days) tags are returned as integer numbers of days.
           Times (xx_time) tags are returned as dateTime ValueHelpers set to
           midnight (at start) of the first day of the run concerned. If the
           length of the run is 0 then the corresponding start time of the run
           is returned as None.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          month_con_dry_days:        Length of longest run of consecutive dry
                                     days in current month
          month_con_dry_days_time:   Start dateTime of longest run of
                                     consecutive dry days in current month
          month_con_wet_days:        Length of longest run of consecutive wet
                                     days in current month
          month_con_wet_days_time:   Start dateTime of longest run of
                                     consecutive wet days in current month
          year_con_dry_days:         Length of longest run of consecutive dry
                                     days in current year
          year_con_dry_days_time:    Start dateTime of longest run of
                                     consecutive dry days in current year
          year_con_wet_days:         Length of longest run of consecutive wet
                                     days in current year
          year_con_wet_days_time:    Start dateTime of longest run of
                                     consecutive wet days in current year
          alltime_con_dry_days:      Length of alltime longest run of
                                     consecutive dry days
          alltime_con_dry_days_time: Start dateTime of alltime longest run of
                                     consecutive dry days
          alltime_con_wet_days:      Length of alltime longest run of
                                     consecutive wet days
          alltime_con_wet_days_time: Start dateTime of alltime longest run of
                                     consecutive wet days
        """

        t1= time.time()

        ##
        ## Get units for use later with ValueHelpers
        ##
        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get our time unit
        (dateTime_type, dateTime_group) = getStandardUnitType(current_rec['usUnits'], 'dateTime')

        ##
        ## Get timestamps we need for the periods of interest
        ##
        # Get time obj for midnight
        _mn_t = datetime.time(0)
        # Get date obj for now
        _today_d = datetime.datetime.today()
        # Get midnight 1st of the month as a datetime object and then get it as a
        # timestamp
        first_of_month_dt = get_first_day(_today_d)
        _mn_first_of_month_dt = datetime.datetime.combine(first_of_month_dt, _mn_t)
        _mn_first_of_month_ts = time.mktime(_mn_first_of_month_dt.timetuple())
        _month_ts = TimeSpan(_mn_first_of_month_ts, timespan.stop)
        # Get midnight 1st of the year as a datetime object and then get it as a
        # timestamp
        _first_of_year_dt = get_first_day(_today_d, 0, 1-_today_d.month)
        _mn_first_of_year_dt = datetime.datetime.combine(_first_of_year_dt, _mn_t)
        _mn_first_of_year_ts = time.mktime(_mn_first_of_year_dt.timetuple())
        _year_ts = TimeSpan(_mn_first_of_year_ts, timespan.stop)

        # Get vectors of our month stats
        _rain_vector = []
        _time_vector = []
        # Step through each day in our month timespan and get our daily rain
        # total and timestamp. This is a day_archive version of the archive
        # getSqlVectors method.
        for tspan in weeutil.weeutil.genDaySpans(_mn_first_of_month_ts, timespan.stop):
            _row = db_lookup().getSql("SELECT dateTime, sum FROM archive_day_rain WHERE dateTime >= ? AND dateTime < ? ORDER BY dateTime", (tspan.start, tspan.stop))
            if _row is not None:
                _time_vector.append(_row[0])
                _rain_vector.append(_row[1])
        # As an aside lets get our number of rainy days this month
        _month_rainy_days = sum(1 for i in _rain_vector if i > 0)
        # Get our run of month dry days
        _interim = []   # List to hold details of any runs we might find
        _index = 0      # Placeholder so we can track the start dateTime of any runs
        # Use itertools groupby method to make our search for a run easier
        # Step through each of the groups itertools has found
        for k,g in itertools.groupby(_rain_vector):
            _length = len(list(g))
            if k == 0:  # If we have a run of 0s (ie no rain) add it to our
                        # list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # If we found a run (we want the longest one) then get our results
            (_temp, _month_dry_run, _position) = max(_interim, key=lambda a:a[1])
            # Our 'time' is the day the run ends so we need to add on run-1 days
            _month_dry_time_ts = _time_vector[_position] + (_month_dry_run - 1) * 86400
        else:
            # If we did not find a run then set our results accordingly
            _month_dry_run = 0
            _month_dry_time_ts = None

        # Get our run of month rainy days
        _interim = []   # List to hold details of any runs we might find
        _index = 0      # Placeholder so we can track the start dateTime of any runs
        # Use itertools groupby method to make our search for a run easier
        # Step through each of the groups itertools has found
        for k,g in itertools.groupby(_rain_vector, key=lambda r:1 if r > 0 else 0):
            _length = len(list(g))
            if k > 0:   # If we have a run of something > 0 (ie some rain) add
                        # it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # If we found a run (we want the longest one) then get our results
            (_temp, _month_wet_run, _position) = max(_interim, key=lambda a:a[1])
            # Our 'time' is the day the run ends so we need to add on run-1 days
            _month_wet_time_ts = _time_vector[_position] + (_month_wet_run - 1) * 86400
        else:
            # If we did not find a run then set our results accordingly
            _month_wet_run = 0
            _month_wet_time_ts = None

        # Get our year stats vectors
        _rain_vector = []
        _time_vector = []
        for tspan in weeutil.weeutil.genDaySpans(_mn_first_of_year_ts, timespan.stop):
            _row = db_lookup().getSql("SELECT dateTime, sum FROM archive_day_rain WHERE dateTime >= ? AND dateTime < ? ORDER BY dateTime", (tspan.start, tspan.stop))
            if _row is not None:
                _time_vector.append(_row[0])
                _rain_vector.append(_row[1])
        # Get our run of year dry days
        _interim = []   # List to hold details of any runs we might find
        _index = 0      # Placeholder so we can track the start dateTime of any runs
        # Use itertools groupby method to make our search for a run easier
        # Step through each of the groups itertools has found
        for k,g in itertools.groupby(_rain_vector):
            _length = len(list(g))
            if k == 0:  # If we have a run of 0s (ie no rain) add it to our
                        # list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # If we found a run (we want the longest one) then get our results
            (_temp, _year_dry_run, _position) = max(_interim, key=lambda a:a[1])
            # Our 'time' is the day the run ends so we need to add on run-1 days
            _year_dry_time_ts = _time_vector[_position] + (_year_dry_run - 1) * 86400
        else:
            # If we did not find a run then set our results accordingly
            _year_dry_run = 0
            _year_dry_time_ts = None

        # Get our run of year rainy days
        _interim = []   # List to hold details of any runs we might find
        _index = 0      # Placeholder so we can track the start dateTime of any runs
        # Use itertools groupby method to make our search for a run easier
        # Step through each of the groups itertools has found
        for k,g in itertools.groupby(_rain_vector, key=lambda r:1 if r > 0 else 0):
            _length = len(list(g))
            if k > 0:   # If we have a run of something > 0 (ie some rain) add
                        # it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # If we found a run (we want the longest one) then get our results
            (_temp, _year_wet_run, _position) = max(_interim, key=lambda a:a[1])
            # Our 'time' is the day the run ends so we need to add on run-1 days
            _year_wet_time_ts = _time_vector[_position] + (_year_wet_run - 1) * 86400
        else:
            # If we did not find a run then set our results accordingly
            _year_wet_run = 0
            _year_wet_time_ts = None

        # Get our alltime stats vectors
        _rain_vector = []
        _time_vector = []
        for tspan in weeutil.weeutil.genDaySpans(timespan.start, timespan.stop):
            _row = db_lookup().getSql("SELECT dateTime, sum FROM archive_day_rain WHERE dateTime >= ? AND dateTime < ? ORDER BY dateTime", (tspan.start, tspan.stop))
            if _row is not None:
                _time_vector.append(_row[0])
                _rain_vector.append(_row[1])
        # Get our run of alltime dry days
        _interim = []   # List to hold details of any runs we might find
        _index = 0      # Placeholder so we can track the start dateTime of any runs
        # Use itertools groupby method to make our search for a run easier
        # Step through each of the groups itertools has found
        for k,g in itertools.groupby(_rain_vector):
            _length = len(list(g))
            if k == 0:  # If we have a run of 0s (ie no rain) add it to our
                        # list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # If we found a run (we want the longest one) then get our results
            (_temp, _alltime_dry_run, _position) = max(_interim, key=lambda a:a[1])
            # Our 'time' is the day the run ends so we need to add on run-1 days
            _alltime_dry_time_ts = _time_vector[_position] + (_alltime_dry_run - 1) * 86400
        else:
            # If we did not find a run then set our results accordingly
            _alltime_dry_run = 0
            _alltime_dry_time_ts = None

        # Get our run of alltime rainy days
        _interim = []   # List to hold details of any runs we might find
        _index = 0      # Placeholder so we can track the start dateTime of any runs
        # Use itertools groupby method to make our search for a run easier
        # Step through each of the groups itertools has found
        for k,g in itertools.groupby(_rain_vector, key=lambda r:1 if r > 0 else 0):
            _length = len(list(g))
            if k > 0:   # If we have a run of something > 0 (ie some rain) add
                        # it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # If we found a run (we want the longest one) then get our results
            (_temp, _alltime_wet_run, _position) = max(_interim, key=lambda a:a[1])
            # Our 'time' is the day the run ends so we need to add on run-1 days
            _alltime_wet_time_ts = _time_vector[_position] + (_alltime_wet_run - 1) * 86400
        else:
            # If we did not find a run then set our results accordingly
            _alltime_wet_run = 0
            _alltime_wet_time_ts = None

        # Make our timestamps ValueHelpers to give more flexibility in how we can format them in our reports
        _month_dry_time_vt = (_month_dry_time_ts, dateTime_type, dateTime_group)
        _month_dry_time_vh = ValueHelper(_month_dry_time_vt,
                                         formatter=self.generator.formatter,
                                         converter=self.generator.converter)
        _month_wet_time_vt = (_month_wet_time_ts, dateTime_type, dateTime_group)
        _month_wet_time_vh = ValueHelper(_month_wet_time_vt,
                                         formatter=self.generator.formatter,
                                         converter=self.generator.converter)
        _year_dry_time_vt = (_year_dry_time_ts, dateTime_type, dateTime_group)
        _year_dry_time_vh = ValueHelper(_year_dry_time_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)
        _year_wet_time_vt = (_year_wet_time_ts, dateTime_type, dateTime_group)
        _year_wet_time_vh = ValueHelper(_year_wet_time_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)
        _alltime_dry_time_vt = (_alltime_dry_time_ts, dateTime_type, dateTime_group)
        _alltime_dry_time_vh = ValueHelper(_alltime_dry_time_vt,
                                           formatter=self.generator.formatter,
                                           converter=self.generator.converter)
        _alltime_wet_time_vt = (_alltime_wet_time_ts, dateTime_type, dateTime_group)
        _alltime_wet_time_vh = ValueHelper(_alltime_wet_time_vt,
                                           formatter=self.generator.formatter,
                                           converter=self.generator.converter)

        # Create a small dictionary with the tag names (keys) we want to use
        search_list_extension = {'month_con_dry_days': _month_dry_run,
                                 'month_con_dry_days_time': _month_dry_time_vh,
                                 'year_con_dry_days': _year_dry_run,
                                 'year_con_dry_days_time': _year_dry_time_vh,
                                 'alltime_con_dry_days': _alltime_dry_run,
                                 'alltime_con_dry_days_time': _alltime_dry_time_vh,
                                 'month_con_wet_days': _month_wet_run,
                                 'month_con_wet_days_time': _month_wet_time_vh,
                                 'year_con_wet_days': _year_wet_run,
                                 'year_con_wet_days_time': _year_wet_time_vh,
                                 'alltime_con_wet_days': _alltime_wet_run,
                                 'alltime_con_wet_days_time': _alltime_wet_time_vh,
                                 'month_rainy_days': _month_rainy_days}
        t2= time.time()
        logdbg2("wdRainDays SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]

class wdManualAverages(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)

        # dict to convert our [[[Xxxxx]]] to Weewx observation groups
        # if you add more [[[Xxxx]]] under [[Averages]] you must add additional
        # entries in this dict
        self.average_groups = {'Rainfall': 'group_rain',
                               'Temperature': 'group_temperature'}
        # dict to convert [[[Xxxxx]]] to labels for our tags
        # if you add more [[[Xxxx]]] under [[Averages]] you must add additional
        # entries in this dict
        self.average_abb = {'Rainfall': 'rain',
                            'Temperature': 'temp'}
        # dict to convert units used for manual averages to Weewx unit type
        # if you add more [[[Xxxx]]] under [[Averages]] you need to add any new
        # units to this dict
        self.units_dict = {'mm': 'mm', 'cm': 'cm', 'in': 'inch', 'inch': 'inch',
                           'c': 'degree_C', 'f': 'degree_F'}
        # list of setting names we expect under each [[[Xxxxxx]]]
        self.months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    def get_vh(self, entry_str, obs_group):
        """Takes a manual average entry and Weewx observation group and returns
           a ValueHelper.

           Unit labelled datum string is a number followed by one or more spaces followed by a unit label as defined in the keys in self.units_dict. ValueHelper datum and units are set to None if:
           - unit label is not a key in self.units_dict
           - either datum or units label cannot be extracted from entry_str
           - entry_str is None

        Parameters:
          entry_str: unit labelled quanta string eg '24.6 mm' or '56 F'
          obs_group: Weewx observation group to be used

        Returns:
          ValueHelper derived from quanta, units and observation group
        """

        # do we have a string to work on?
        if entry_str is not None:
            # yes, then split on the space
            elements = entry_str.lower().split()
            # do we have 2 elements from the split
            if len(elements) == 2:
                # yes, then start processing
                value = float(elements[0])
                units = elements[1]
                # do we recognise the units used?
                if units in self.units_dict:
                    # yes, then create a ValueTuple
                    entry_vt = ValueTuple(value, self.units_dict[units], obs_group)
                else:
                    # no, create ValueTuple but with None for value and units
                    entry_vt = ValueTuple(None, None, obs_group)
            else:
                # no, all we can do is create ValueTuple but with None for
                # value and units
                entry_vt = ValueTuple(None, None, obs_group)
        else:
            # no string, all we can do create ValueTuple but with None for
            # value and units
            entry_vt = ValueTuple(None, None, obs_group)
        # return a ValueHelper from our ValueTuple
        return ValueHelper(entry_vt)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with manually set month averages
           from [Weewx-WD] section in weewx.conf.

           Looks for a [Weewx-WD][[Averages]] section in weewx.conf. If found
           looks for user settable month averages under [[[Xxxxx]]]
           eg [[[Rainfall]]] or [[[Temperature]]]. Under each [[[Xxxxx]]] there
           must be 12 settings (Jan =, Feb = ... Dec =). Each setting consists
           of a number followed by a unit label eg 12 mm or 34.3 C. Note unit
           labels are not a Weewx unit type. Provided the 12 month settings
           exists the value are returned as ValueHelpers to allow unit
           conversion/formatting. If one or more month setting is invalid or
           missing the 'exists' flag (eg temp_man_avg_exists) is set to False
           indicating that there is not a valid, complete suite of average
           settings for that group. Additinal [[[Xxxxx]]] average groups can be
           catered for by adding to the self.average_groups, self.average_abb
           and self.units_dict dicts as required.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          jan_xxxx_man_avg .. dec_xxxx_man_avg: ValueHelper manual average
                setting for each month (eg jan_rain_man_avg). xxxx is the
                looked up values in the self.average_abb dict.

          xxxx_man_avg_exists: Flag (eg rain_man_avg_exists) set to False
                if a complete manual average group (12 months) is not
                available for xxxx. Flag is set true if entire 12 months of
                averages are available.
        """

        t1 = time.time()

        # clear our search list
        searchList = {}
        # do we have any manual month averages?
        if 'Averages' in self.generator.config_dict['Weewx-WD']:
            # yes, get our dict
            man_avg_dict = self.generator.config_dict['Weewx-WD']['Averages']
            # step through each of the average groups we might encounter
            for average_group in self.average_groups:
                # if we find an average group
                if average_group in man_avg_dict:
                    # get our settings
                    group_dict = man_avg_dict[average_group]
                    # initialise our 'exists' flag assuming we have settings
                    # for all 12 months
                    all_months = True
                    # step through each month
                    for avg_month in self.months:
                        if avg_month in group_dict:
                            # we found a setting so get it as a ValueHelper
                            entry_vh = self.get_vh(group_dict[avg_month].strip(), self.average_groups[average_group])
                        else:
                            # no setting for the month concerned so get a ValueHelper with None
                            entry_vh = self.get_vh(None, self.average_groups[average_group])
                        # add the ValueHelper to our search list
                        searchList[(avg_month + '_' + self.average_abb[average_group] + '_man_avg').lower()] = entry_vh
                        # update our 'exists' flag
                        all_months &= entry_vh.has_data()
                    # add our 'exists' flag to the search list
                    searchList[(average_group + '_man_avg_exists').lower()] = all_months
                else:
                    # no average group for this one so set our 'exists' flag
                    # False and add it to the search list
                    searchList[(average_group + '_man_avg_exists').lower()] = False
        else:
            # no, so set our 'exists' to False for each of our expected average
            # groups
            for average_group in self.average_groups:
                searchList[(average_group + '_man_avg_exists').lower()] = False

        t2 = time.time()
        logdbg2("wdManualAverages SLE executed in %0.3f seconds" % (t2-t1))

        return [searchList]
