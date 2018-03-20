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
# Version: 1.2.0a1                                      Date: 17 March 2018
#
# Revision History
#   9 March 2018        v1.2.0a1
#       - weeWX-WD now requires weeWX v3.5.0 or later
#       - revised Databases and DataBindings config options to support wdSchema
#         and wd supp database
#       - added new WdSuppArchive service
#       - skins now include the enabled config option
#       - wdPWS skin disabled by default
#       - added sunshine_threshold config option and Supplementary stanza to
#         WeeWX-WD config stanza to support weeWX-WD supplementary data
#       - added new file wdSchema.py
#       - removed no longer used file wd_database
#
# Previous Bitbucket revision history
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

REQUIRED_VERSION = "3.5.0"
WEEWX_WD_VERSION = "1.2.0.a1"


def loader():
    return WeewxWdInstaller()


class WeewxWdInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_VERSION):
            msg = "%s requires weeWX %s or greater, found %s" % ('weeWX-WD ' + WEEWX_WD_VERSION,
                                                                 REQUIRED_VERSION,
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(WeewxWdInstaller, self).__init__(
            version=WEEWX_WD_VERSION,
            name='Weewx-WD',
            description='weeWX support for Weather Display Live, SteelSeries Gauges and Carter Lake/Saratoga weather web site templates.',
            author="Gary Roderick",
            author_email="gjroderick<@>gmail.com",
            process_services=['user.weewxwd3.WdWXCalculate'],
            archive_services=['user.weewxwd3.WdArchive',
                              'user.weewxwd3.WdSuppArchive'],
            config={
                'StdReport': {
                    'wdPWS': {
                        'enabled': 'False',
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
                        'enabled': 'True',
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
                        'enabled': 'True',
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
                        'enabled': 'True',
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
                        'enabled': 'True',
                        'HTML_ROOT': 'WD'
                    }
                },
                'DataBindings': {
                    'wd_binding': {
                        'database': 'weewxwd_sqlite',
                        'table_name': 'archive',
                        'manager': 'weewx.manager.DaySummaryManager',
                        'schema': 'user.wdSchema.weewxwd_schema'
                    },
                    'wdsupp_binding': {
                        'database': 'wd_supp_sqlite',
                        'table_name': 'supp',
                        'manager': 'weewx.manager.Manager',
                        'schema': 'user.wdSchema.wdsupp_schema'
                    }
                },
                'Databases': {
                    'weewxwd_sqlite': {
                        'database_type': 'SQLite',
                        'database_name': 'weewxwd.sdb'
                    },
                    'wd_supp_sqlite': {
                        'database_type': 'SQLite',
                        'database_name': 'wdsupp.sdb'
                    },
                    'weewxwd_mysql': {
                        'database_type': 'MySQL',
                        'database_name': 'weewxwd'
                    },
                    'wd_supp_mysql': {
                        'database_type': 'MySQL',
                        'database_name': 'wdsupp'
                    }
                },
                'Weewx-WD': {
                    'data_binding': 'wd_binding',
                    'sunshine_threshold': '120',
                    'Supplementary': {
                        'data_binding': 'wdsupp_binding',
                        'database_max_tries': '3',
                        'max_age': '691200',
                        'database_retry_wait': '10',
                        'vacuum': '86400',
                        'WU': {
                            'apiKey': '***REMOVED***',
                            'forecast_interval': '1800',
                            'api_lockout_period': '60',
                            'max_WU_tries': '3',
                            'location': '***REMOVED***',
                            'almanac_interval': '3600',
                            'conditions_interval': '1800'
                        }
                    }
                }
            },
            files=[('bin/user', ['bin/user/imageStackedWindRose3.py',
                                 'bin/user/wdAstroSearchX3.py',
                                 'bin/user/wdSchema.py',
                                 'bin/user/wdSearchX3.py',
                                 'bin/user/wdTaggedStats3.py',
                                 'bin/user/weewxwd3.py']),
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
