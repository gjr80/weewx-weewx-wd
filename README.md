# WeeWX-WD #

A WeeWX extension to support Weather Display Live, Carter Lake/Saratoga weather website templates and the Pocket PWS Android weather app.

Forked from https://bitbucket.org/ozgreg/weewx-wd

The *WeeWX-WD* extension consists of a number of WeeWX services, Search List Extensions (SLE) and skins that produce the following data files:

Weather Display live:

-   clientraw.txt
-   clientrawextra.txt
-   clientrawdaily.txt
-   clientrawhour.txt

Carter Lake/Saratoga templates:
-   testtags.php
-   daywindrose.png

Pocket PWS:
-   weewx_pws.xml

The *WeeWX-WD* extension utilises a separate database to record a number of observations in addition to those normally recorded by WeeWX. The *WeeWX-WD* extension then uses this and standard WeeWX data to produce a number of files used as source data for Weather Display Live, the Carter Lake/Saratoga weather website templates and the Pocket PWS Android weather app.

## Pre-Requisites ##

The *WeeWX-WD* extension requires WeeWX v3.2 or later. Both Python 2 and Python 3 are 
supported when using WeeWX v4.0.0 or later.

Pyephem is required to support advanced ephemeris tags. 

## File Locations ##

As WeeWX file locations vary by system and installation method, the following symbolic names, as per the WeeWX User's Guide - Installing WeeWX, are used in these instructions:

- $BIN_ROOT (Executables)
- $SKIN_ROOT (Skins and templates)
- $SQLITE_ROOT (SQLite databases)
- $HTML_ROOT (Web pages and images)

Where applicable the nominal location for your system and installation type should be used in place of the symbolic name.

## Installation Instructions ##

**Note:** If upgrading a previous *WeeWX-WD* installation please refer to the [Upgrade Guide](https://github.com/gjr80/weewx-weewx-wd/wiki/Upgrade%20Guide) in the *WeeWX-WD* [wiki](https://github.com/gjr80/weewx-weewx-wd/wiki).

**Note:** In the following code snippets the symbolic name *$DOWNLOAD_ROOT* is the path to the directory containing the downloaded *WeeWX-WD* extension.

### Installation using the wee_extension utility ###

1.  Download the *WeeWX-WD* extension from the *WeeWX-WD* extension the *WeeWX-WD* extension [releases page](https://github.com/gjr80/weewx-weewx-wd/releases) into a directory accessible from the WeeWX machine.

        $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-weewx-wd/releases/download/v2.1.1/weewxwd-2.1.1.tar.gz

	replacing the symbolic name *$DOWNLOAD_ROOT* with the path to the directory where the *WeeWX-WD* extension is to be downloaded (eg, */var/tmp*).

1.  Stop WeeWX:

        $ sudo /etc/init.d/weewx stop

	or

        $ sudo service weewx stop

    or

        $ sudo systemctl stop weewx

1.  Install the *WeeWX-WD* extension downloaded at step 1 using the WeeWX *wee_extension* utility:

        $ wee_extension --install=$DOWNLOAD_ROOT/weewxwd-2.1.1.tar.gz

    **Note:** Depending on your system/installation the above command may need to be prefixed with *sudo*.

    **Note:** Depending on your WeeWX installation the path to *wee_extension* may need to be provided, eg: `$ /home/weewx/bin/wee_extension --install...`.
    
    This will result in output similar to the following:

		Request to install '/var/tmp/weewxwd-2.1.1.tar.gz'
		Extracting from tar archive /var/tmp/weewxwd-2.1.1.tar.gz
		Saving installer file to /home/weewx/bin/user/installer/WeeWX-WD
		Saved configuration dictionary. Backup copy at /home/weewx/weewx.conf.20190427130000
		Finished installing extension '/var/tmp/weewxwd-2.1.1.tar.gz'

1. Start WeeWX:

        $ sudo /etc/init.d/weewx start

	or

        $ sudo service weewx start

    or

        $ sudo systemctl start weewx

1.  This will result in the WeeWX-WD data files being generated during each report generation cycle. The *WeeWX-WD* extension installation can be further customized (eg units of measure, file locations etc) by referring to the WeeWX-WD wiki.

### Manual installation ###

1.  Download the *WeeWX-WD* extension from the *WeeWX-WD* extension [releases page](https://github.com/gjr80/weewx-weewx-wd/releases) into a directory accessible from the WeeWX machine.

        $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-weewx-wd/releases/download/v2.1.1/weewxwd-2.1.1.tar.gz

	where *$DOWNLOAD_ROOT* is the path to the directory where the *WeeWX-WD* extension is to be downloaded.

1.  Unpack the extension as follows:

        $ tar xvfz weewxwd-2.1.1.tar.gz

1.  Copy files from within the resulting folder as follows:

        $ cp weewxwd/bin/user/*.py $BIN_ROOT/user
        $ cp -R weewxwd/skins/Clientraw $SKIN_ROOT
        $ cp -R weewxwd/skins/Testtags $SKIN_ROOT
        $ cp -R weewxwd/skins/SteelGauges $SKIN_ROOT
        $ cp -R weewxwd/skins/PWS $SKIN_ROOT
        $ cp -R weewxwd/skins/StackedWindRose $SKIN_ROOT

	replacing the symbolic names *$BIN_ROOT* and *$SKIN_ROOT* with the nominal locations for your installation.

1.  Edit weewx.conf:

        $ vi weewx.conf

1.  In weewx.conf, modify the *[StdReport]* section by adding the following sub-sections:

        [[wdTesttags]]
            HTML_ROOT = public_html/WD
            skin = Testtags
            enabled = True
            [[[Units]]]
                [[[[TimeFormats]]]]
                    date_f = %d/%m/%Y
                    date_time_f = %d/%m/%Y %H:%M
                [[[[Groups]]]]
                    group_altitude = foot
                    group_degree_day = degree_C_day
                    group_rainrate = mm_per_hour
                    group_rain = mm
                    group_speed = km_per_hour
                    group_speed2 = km_per_hour2
                    group_pressure = hPa
                    group_temperature = degree_C            
    
        [[wdPWS]]
            HTML_ROOT = public_html/WD
            skin = PWS
            enabled = False
            [[[Units]]]
                [[[[Groups]]]]
                    group_rainrate = mm_per_hour
                    group_rain = mm
                    group_speed = km_per_hour
                    group_speed2 = km_per_hour2
                    group_pressure = hPa
                    group_temperature = degree_C
                    
        [[wdClientraw]]
            HTML_ROOT = public_html/WD
            skin = Clientraw
            enabled = True
            [[[Units]]]
                [[[[StringFormats]]]]
                    percent = %.0f
                    degree_compass = %.0f
                    watt_per_meter_squared = %.0f
                    mm = %.1f
                    NONE = --
                    knot = %.1f
                    degree_C = %.1f
                    km = %.1f
                    foot = %.0f
                    uv_index = %.1f
                    hPa = %.1f
                    
        [[wdStackedWindRose]]
            HTML_ROOT = public_html/WD
            skin = StackedWindRose
            enabled = True
            [[[Units]]]
                [[[[TimeFormats]]]]
                    date_f = %d/%m/%Y
                    date_time_f = %d/%m/%Y %H:%M
                [[[[Groups]]]]
                    group_speed2 = km_per_hour2
                    group_speed = km_per_hour            

1.  In weewx.conf, add the following section:

        [Weewx-WD]
            data_binding = wd_binding
            sunshine_threshold = 120
            [[Supplementary]]
                data_binding = wdsupp_binding
                [[[WU]]]
                    api_key = replace_me
                    enable = False
                [[[DS]]]
                    api_key = replace_me
                    enable = False
                [[[File]]]
                    file = /path/and/filename
                    enable = False

1.  In weewx.conf, add the following sub-section to *[Databases]*:

        [[weewxwd_sqlite]]
            driver = weedb.sqlite
            database_name = archive/weewxwd.sdb
            root = /home/weewx/

        [[wd_supp_sqlite]]
            database_name = wdsupp.sdb
            database_type = SQLite

    if using MySQL instead add something like (with settings for your MySQL setup):

        [[weewxwd_mysql]]
            database_name = weewxwd
            database_type = MySQL
    
        [[wd_supp_mysql]]
            database_name = wdsupp
            database_type = MySQL

1.  In weewx.conf, add the following sub-section to the *[DataBindings]* section:

        [[wd_binding]]
            database = weewxwd_sqlite
            table_name = archive
            manager = weewx.manager.DaySummaryManager
            schema = user.wdschema.weewxwd_schema
    
        [[wdsupp_binding]]
            database = wd_supp_sqlite
            table_name = supp
            manager = weewx.manager.Manager
            schema = user.wdschema.wdsupp_schema

    if using MySQL instead, add something like (with settings for your MySQL
    setup):

        [[wd_binding]]
            database = weewxwd_mysql
            table_name = archive
            manager = weewx.manager.DaySummaryManager
            schema = user.wdschema.weewxwd_schema
    
        [[wdsupp_binding]]
            database = wd_supp_mysql
            table_name = supp
            manager = weewx.manager.Manager
            schema = user.wdschema.wdsupp_schema

1.  In weewx.conf, modify the services lists in *[Engine]* as indicated:

	*   process_services. Add user.wd.WdWXCalculate eg:

            process_services = weewx.engine.StdConvert, weewx.engine.StdCalibrate, weewx.engine.StdQC, weewx.wxservices.StdWXCalculate, user.wd.WdWXCalculate

	*   archive_services. Add user.weewxwd3.WdArchive AND user.wd.WdSuppArchive eg:

            archive_services = weewx.engine.StdArchive, user.wd.WdArchive, user.wd.WdSuppArchive

1. Start WeeWX:

        $ sudo /etc/init.d/weewx start

	or

        $ sudo service weewx start

    or

        $ sudo systemctl start weewx

1.  This will result in the WeeWX-WD data files being generated during each report generation cycle. The *WeeWX-WD* extension installation can be further customized (eg units of measure, file locations etc) by referring to the WeeWX-WD wiki.


## Support ##

General support issues may be raised in the Google Groups [weewx-user forum](https://groups.google.com/group/weewx-user "Google Groups weewx-user forum"). Specific bugs in the *WeeWX-WD* extension code should be the subject of a new issue raised via the [Issues Page](https://github.com/gjr80/weewx-weewx-wd/issues "WeeWX-WD extension Issues").

## Licensing ##

The *WeeWX-WD* extension is licensed under the [GNU Public License v3](https://github.com/gjr80/weewx-weewx-wd/blob/master/LICENSE "*WeeWX-WD* extension License").
