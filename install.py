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
#                          Installer for Weewx-WD
#
# Version: 1.0.3                                  Date: 31 March 2017
#
# Revision History
#   31 March 2017       v1.0.3
#       - no change, version number change only
#   14 December 2016    v1.0.2
#       - no change, version number change only
#   30 November 2016    v1.0.1
#       - minor formatting changes/fix typos
#       - add weewx version check
#       - add default units and date settings to weewx.conf as applicable
#       - added wd_database utility
#   10 December 2014    v1.0.0a2
#       - set default HTML_ROOT to WD
#       - initial cut of readme.txt, added steps to override units, date
#         format and HTML_ROOT on a per skin basis in weewx.conf
#   8 December 2014     v1.0.0a1
#       - initial implementation
#

import weewx

from distutils.version import StrictVersion
from setup import ExtensionInstaller

REQUIRED_VERSION = "3.4.0"
WEEWX_WD_VERSION = "1.0.3"

def loader():
    return WeewxWdInstaller()

class WeewxWdInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_VERSION):
            msg = "%s requires weewx %s or greater, found %s" % ('Weewx-WD ' + WEEWX_WD_VERSION,
                                                                 REQUIRED_VERSION,
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(WeewxWdInstaller, self).__init__(
            version=WEEWX_WD_VERSION,
            name='Weewx-WD',
            description='weewx support for Weather Display Live, SteelSeries Gauges and Carter Lake/Saratoga weather web site templates.',
            author="Gary Roderick/Oz Greg",
            author_email="gjroderick@gmail.com ozgreg@gmail.com",
            process_services=['user.weewxwd3.WdWXCalculate'],
            archive_services=['user.weewxwd3.WdArchive'],
            config={
                'StdReport': {
                    'wdPWS': {
                        'skin': 'PWS',
                        'HTML_ROOT': 'WD',
                        'Units': {
                            'Groups': {
                                'group_pressure': 'hPa',
                                'group_rain': 'mm',
                                'group_rainrate': 'mm_per_hour',
                                'group_speed': 'km_per_hour',
                                'group_speed2': 'km_per_hour2',
                                'group_temperature': 'degree_C'
                            },
                        },
                    },
                    'wdStackedWindRose': {
                        'skin': 'StackedWindRose',
                        'HTML_ROOT': 'WD',
                        'Units': {
                            'Groups': {
                                'group_speed': 'km_per_hour',
                                'group_speed2': 'km_per_hour2'
                            },
                            'TimeFormats': {
                                'date_f': '%d/%m/%Y',
                                'date_time_f': '%d/%m/%Y %H:%M'
                            },
                        },
                    },
                    'wdTesttags': {
                        'skin': 'Testtags',
                        'HTML_ROOT': 'WD',
                        'Units': {
                            'Groups': {
                                'group_altitude': 'foot',
                                'group_degree_day': 'degree_C_day',
                                'group_pressure': 'hPa',
                                'group_rain': 'mm',
                                'group_rainrate': 'mm_per_hour',
                                'group_speed': 'km_per_hour',
                                'group_speed2': 'km_per_hour2',
                                'group_temperature': 'degree_C'
                            },
                            'TimeFormats': {
                                'date_f': '%d/%m/%Y',
                                'date_time_f': '%d/%m/%Y %H:%M'
                            },
                        },
                    },
                    'wdSteelGauges': {
                        'skin': 'SteelGauges',
                        'HTML_ROOT': 'WD',
                        'Units': {
                            'Groups': {
                                'group_pressure': 'hPa',
                                'group_rain': 'mm',
                                'group_rainrate': 'mm_per_hour',
                                'group_speed': 'km_per_hour',
                                'group_speed2': 'km_per_hour2',
                                'group_temperature': 'degree_C'
                            },
                        },
                    },
                    'wdClientraw': {
                        'skin': 'Clientraw',
                        'HTML_ROOT': 'WD'
                    }
                },
                'DataBindings': {
                    'wd_binding': {
                        'database': 'weewxwd_sqlite',
                        'table_name': 'archive',
                        'manager': 'weewx.manager.DaySummaryManager',
                        'schema': 'user.weewxwd3.schema'
                    }
                },
                'Databases': {
                    'weewxwd_sqlite': {
                        'root': '%(WEEWX_ROOT)s',
                        # SQLite database so just use the file name, relative
                        # path will be added at install
                        'database_name': 'weewxwd.sdb',
                        'driver': 'weedb.sqlite'
                    },
                    'weewxwd_mysql': {
                        'host': 'localhost',
                        'user': 'weewx',
                        'password': 'weewx',
                        'database_name': 'weewxwd',
                        'driver': 'weedb.mysql'
                    }
                },
                'Weewx-WD': {
                    'data_binding': 'wd_binding'}},
            files=[('bin/user', ['bin/user/imageStackedWindRose3.py',
                                 'bin/user/wdAstroSearchX3.py',
                                 'bin/user/wdSearchX3.py',
                                 'bin/user/wdTaggedStats3.py',
                                 'bin/user/weewxwd3.py',
                                 'bin/user/wd_database']),
                   ('skins/Clientraw', ['skins/Clientraw/clientraw.txt.tmpl',
                                        'skins/Clientraw/clientrawdaily.txt.tmpl',
                                        'skins/Clientraw/clientrawextra.txt.tmpl',
                                        'skins/Clientraw/clientrawhour.txt.tmpl',
                                        'skins/Clientraw/skin.conf']),
                   ('skins/PWS', ['skins/PWS/weewx_pws.xml.tmpl',
                                  'skins/PWS/skin.conf']),
                   ('skins/StackedWindRose', ['skins/StackedWindRose/skin.conf']),
                   ('skins/SteelGauges', ['skins/SteelGauges/customclientraw.txt.tmpl',
                                          'skins/SteelGauges/skin.conf']),
                   ('skins/Testtags', ['skins/Testtags/skin.conf',
                                       'skins/Testtags/testtags.php.tmpl']),
                  ]
            )
