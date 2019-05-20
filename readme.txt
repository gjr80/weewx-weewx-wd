WeeWX-WD - A WeeWX extension that provides support for Weather Display Live,
Carter Lake/Saratoga weather website templates and the Pocket PWS Android
weather app.

WeeWX-WD consists of a number of WeeWX services, Search List Extensions (SLE)
and skins that produce the following data files:

Weather Display live
    clientraw.txt
    clientrawextra.txt
    clientrawdaily.txt
    clientrawhour.txt

Carter Lake/Saratoga templates
    testtags.php
    daywindrose.png

Pocket PWS
    weewx_pws.xml

WeeWX-WD utilises a separate database to record a number of observations in
addition to those normally recorded by WeeWX. WeeWX-WD then uses this and
standard WeeWX data to produce a number of files used as source data for
Weather Display Live, the Carter Lake/Saratoga weather website templates and
the Pocket PWS Android weather app.

Pre-Requisites

WeeWX-WD v1.2.0 requires Weewx v3.5.0 or greater.

File Locations

As WeeWX file locations vary by system and installation method, the following
symbolic names, as per the WeeWX User's Guide - Installing WeeWX, are used in
these instructions:

- $BIN_ROOT (Executables)
- $SKIN_ROOT (Skins and templates)
- $SQLITE_ROOT (SQLite databases)
- $HTML_ROOT (Web pages and images)

Where applicable the nominal location for your system and installation type
should be used in place of the symbolic name.

Installation Instructions

Installation using the wee_extension utility

Note:   In the following code snippets the symbolic name *$DOWNLOAD_ROOT* is
        the path to the directory containing the downloaded WeeWX-WD extension.

1.  Download the WeeWX-WD extension from the WeeWX-WD Bitbucket downloads site
(https://bitbucket.org/ozgreg/weewx-wd/downloads) into a directory accessible
from the weewx machine.

    $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-weewx-wd/releases/download/v1.2.0/weewxwd-1.2.0.tar.gz

	where $DOWNLOAD_ROOT is the path to the directory where the WeeWX-WD
    extension is to be downloaded.

2.  Stop WeeWX:

    $ sudo /etc/init.d/weewx stop

	or

    $ sudo service weewx stop

    or

    $ sudo systemctl stop weewx

3.  Install the WeeWX-WD extension downloaded at step 1 using the WeeWX
wee_extension utility:

    wee_extension --install=$DOWNLOAD_ROOT/weewxwd-1.2.0.tar.gz

    This will result in output similar to the following:

		Request to install '/var/tmp/weewxwd-1.2.0.tar.gz'
		Extracting from tar archive /var/tmp/weewxwd-1.2.0.tar.gz
		Saving installer file to /home/weewx/bin/user/installer/Weewx-WD
		Saved configuration dictionary. Backup copy at /home/weewx/weewx.conf.20190427130000
		Finished installing extension '/var/tmp/weewxwd-1.2.0.tar.gz'

4. Start WeeWX:

    $ sudo /etc/init.d/weewx start

	or

    $ sudo service weewx start

    or

    $ sudo systemctl start weewx

This will result in the WeeWX-WD data files being generated during each report
generation cycle. The WeeWX-WD installation can be further customized (eg units
of measure, file locations etc) by referring to the WeeWX-WD wiki.

Manual installation

1.  Download the WeeWX-WD extension from the WeeWX-WD Bitbucket downloads site
(https://bitbucket.org/ozgreg/weewx-wd/downloads) into a directory accessible
from the WeeWX machine:

    $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-weewx-wd/releases/download/v1.2.0/weewxwd-1.2.0.tar.gz

	where $DOWNLOAD_ROOT is the path to the directory where the WeeWX-WD
    extension is to be downloaded.

2.  Unpack the extension as follows:

    $ tar xvfz weewxwd-1.2.0.tar.gz

3.  Copy files from within the resulting folder as follows:

    $ cp weewxwd/bin/user/*.py $BIN_ROOT/user
    $ cp -R weewxwd/skins/Clientraw $SKIN_ROOT
    $ cp -R weewxwd/skins/Testtags $SKIN_ROOT
    $ cp -R weewxwd/skins/SteelGauges $SKIN_ROOT
    $ cp -R weewxwd/skins/PWS $SKIN_ROOT
    $ cp -R weewxwd/skins/StackedWindRose $SKIN_ROOT

	replacing the symbolic names $BIN_ROOT and $SKIN_ROOT with the nominal
    locations for your installation.

4.  Edit weewx.conf:

    $ vi weewx.conf

5.  In weewx.conf, modify the [StdReport] section by adding the following
sub-sections:

    [[wdTesttags]]
        HTML_ROOT = public_html/WD
        skin = Testtags

    [[wdPWS]]
        HTML_ROOT = public_html/WD
        skin = PWS

    [[wdClientraw]]
        HTML_ROOT = public_html/WD
        skin = Clientraw

    [[wdStackedWindRose]]
        HTML_ROOT = public_html/WD
        skin = StackedWindRose

6.  In weewx.conf, add the following section:

    [Weewx-WD]
        data_binding = wd_binding

7.  In weewx.conf, add the following sub-section to [Databases]:

    [[weewxwd_sqlite]]
        driver = weedb.sqlite
        database_name = archive/weewxwd.sdb
        root = /home/weewx/

    if using MySQL instead add something like (with settings for your MySQL
    setup):

    [[weewxwd_mysql]]
        host = localhost
        user = weewx
        password = weewx
        database_name = weewxwd
        driver = weedb.mysql

8.  In weewx.conf, add the following sub-section to the [DataBindings] section:

    [[wd_binding]]
        manager = weewx.manager.DaySummaryManager
        schema = user.weewxwd3.schema
        table_name = archive
        database = weewxwd_sqlite

    if using MySQL instead, add something like (with settings for your MySQL
    setup):

    [[wd_binding]]
        manager = weewx.manager.DaySummaryManager
        schema = user.weewxwd3.schema
        table_name = archive
        database = weewxwd_mysql

9.  In weewx.conf, modify the services lists in [Engine] as indicated:

	*   process_services. Add user.wd.WdWXCalculate eg:

        process_services = weewx.engine.StdConvert, weewx.engine.StdCalibrate, weewx.engine.StdQC, weewx.wxservices.StdWXCalculate, user.wd.WdWXCalculate

	*   archive_services. Add user.weewxwd3.WdArchive eg:

        archive_services = weewx.engine.StdArchive, user.wd.WdArchive

10. Start WeeWX:

    $ sudo /etc/init.d/weewx start

	or

    $ sudo service weewx start

    or

    $ sudo systemctl start weewx

This will result in the WeeWX-WD data files being generated during each report
generation cycle. The WeeWX-WD installation can be further customized (eg units
of measure, file locations etc) by referring to the WeeWX-WD wiki.