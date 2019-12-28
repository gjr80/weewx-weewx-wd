"""
This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 2 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

                         Installer for Weewx-WD

Version: 2.0.0a1                                      Date: 27 December 2019

Revision History
    27 December 2019    v2.0.0
        - WeeWX-WD now requires WeeWX v4.0.0 or later
        - revised Databases and DataBindings config options to support wdSchema
          and wd supp database
        - added new WdSuppArchive service
        - skins now include the enabled config option
        - wdPWS skin disabled by default
        - added sunshine_threshold config option and Supplementary stanza to
          WeeWX-WD config stanza to support WeeWX-WD supplementary data
        - added new file wdschema.py
        - removed no longer used file wd_database
        - renamed various install files
        - reformatted these comments
        - removed SteelGauges skin
        - added new [[[WU]]], [[[DS]]] and [[[File]]] stanzas to [[Supplementary]]

Previous Bitbucket revision history
    31 March 2017       v1.0.3
        - no change, version number change only
    14 December 2016    v1.0.2
        - no change, version number change only
    30 November 2016    v1.0.1
        - minor formatting changes/fix typos
        - add weewx version check
        - add default units and date settings to weewx.conf as applicable
        - added wd_database utility
    10 December 2014    v1.0.0a2
        - set default HTML_ROOT to WD
        - initial cut of readme.txt, added steps to override units, date
          format and HTML_ROOT on a per skin basis in weewx.conf
    8 December 2014     v1.0.0a1
        - initial implementation
"""

# python imports
from distutils.version import StrictVersion

# WeeWX imports
import weewx

from setup import ExtensionInstaller

# TODO. Fix before release
REQUIRED_VERSION = "4.0.0b5"
WEEWX_WD_VERSION = "2.0.0a1"


def loader():
    return WeewxWdInstaller()


class WeewxWdInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_VERSION):
            msg = "%s requires WeeWX %s or greater, found %s" % ('WeeWX-WD ' + WEEWX_WD_VERSION,
                                                                 REQUIRED_VERSION,
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(WeewxWdInstaller, self).__init__(
            version=WEEWX_WD_VERSION,
            name='WeeWX-WD',
            description='WeeWX support for Weather Display Live and Carter Lake/Saratoga weather web site templates.',
            author="Gary Roderick",
            author_email="gjroderick<@>gmail.com",
            process_services=['user.wd.WdWXCalculate'],
            archive_services=['user.wd.WdArchive',
                              'user.wd.WdSuppArchive'],
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
                    'wdClientraw': {
                        'skin': 'Clientraw',
                        'enabled': 'True',
                        'HTML_ROOT': 'WD',
                        'Units': {
                            'StringFormats': {
                                'degree_C': '%.1f',
                                'degree_compass': '%.0f',
                                'foot': '%.0f',
                                'hPa': '%.1f',
                                'km': '%.1f',
                                'knot': '%.1f',
                                'mm': '%.1f',
                                'percent': '%.0f',
                                'uv_index': '%.1f',
                                'watt_per_meter_squared': '%.0f',
                                'NONE': '--'
                            },
                        },
                    }
                },
                'DataBindings': {
                    'wd_binding': {
                        'database': 'weewxwd_sqlite',
                        'table_name': 'archive',
                        'manager': 'weewx.manager.DaySummaryManager',
                        'schema': 'user.wdschema.weewxwd_schema'
                    },
                    'wdsupp_binding': {
                        'database': 'wd_supp_sqlite',
                        'table_name': 'supp',
                        'manager': 'weewx.manager.Manager',
                        'schema': 'user.wdschema.wdsupp_schema'
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
                        'WU': {
                            'api_key': 'replace_me',
                            'enable': 'False'
                        },
                        'DS': {
                            'api_key': 'replace_me',
                            'enable': 'False'
                        },
                        'File': {
                            'file': '/path/and/filename',
                            'enable': 'False'
                        }
                    }
                }
            },
            files=[('bin/user', ['bin/user/stackedwindrose.py',
                                 'bin/user/wdastro.py',
                                 'bin/user/wdschema.py',
                                 'bin/user/wdsearchlist.py',
                                 'bin/user/wdtaggedstats.py',
                                 'bin/user/wd.py']),
                   ('skins/Clientraw', ['skins/Clientraw/clientraw.txt.tmpl',
                                        'skins/Clientraw/clientrawdaily.txt.tmpl',
                                        'skins/Clientraw/clientrawextra.txt.tmpl',
                                        'skins/Clientraw/clientrawhour.txt.tmpl',
                                        'skins/Clientraw/skin.conf']),
                   ('skins/PWS', ['skins/PWS/weewx_pws.xml.tmpl',
                                  'skins/PWS/skin.conf']),
                   ('skins/StackedWindRose', ['skins/StackedWindRose/skin.conf']),
                   ('skins/Testtags', ['skins/Testtags/skin.conf',
                                       'skins/Testtags/testtags.php.tmpl']),
                   ]
            )
