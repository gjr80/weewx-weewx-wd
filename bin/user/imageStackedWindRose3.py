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
#       - no change, version number change only
#   14 December 2016    v1.0.2
#       - fixed Image/ImageDraw import issue, now tries to import from PIL
#         first
#       - fixed issue where wind speed was always displayed in the windSpeed/
#         windGust units used in the weewx database
#       - speed and direction ValueTuples now use .value property instead of
#         [0] to access the ValueTuple value
#   30 November 2016    v1.0.1
#       - fixed issue whereby weewx would exit if the requested font is not
#         installed, now defaults to a system font used by weewx if the
#         requested font is not installed
#       - minor reformatting of long lines and equations
#   10 January 2015     v1.0.0
#       - rewritten for weewx v3.0.0
#   1 May 2014          v0.9.3
#       - fixed issue that arose with weewx 2.6.3 now allowing use of UTF-8
#         characters in plots
#       - fixed logic error in code that calculates size of windrose 'petals'
#       - removed unnecessary import statements
#       - tweaked windrose size calculations to better cater for labels on plot
#   30 July 2013        v0.9.1
#       - revised version number to align with weewx-WD version numbering
#   20 July 2013        v0.1
#       - initial implementation
#

import datetime
import math
import os.path
import syslog
import time
try:
    from PIL import Image, ImageDraw
except ImportError:
    import Image, ImageDraw

import weeutil.weeutil
import weewx.reportengine
import weewx.units

from weeplot.utilities import get_font_handle
from weeutil.weeutil import TimeSpan

WEEWXWD_STACKED_WINDROSE_VERSION = '1.0.3'


#=============================================================================
#                    Class ImageStackedWindRoseGenerator
#=============================================================================


class ImageStackedWindRoseGenerator(weewx.reportengine.ReportGenerator):
    """Class for managing the stacked windrose image generator."""

    def run(self):
        self.setup()

        # Generate any images
        self.genImages(self.gen_ts)

    def setup(self):
        # Get our binding to use
        self.data_binding = self.config_dict['StdArchive'].get('data_binding',
                                                               'wx_binding')

        self.image_dict = self.skin_dict['ImageStackedWindRoseGenerator']
        self.title_dict = self.skin_dict['Labels']['Generic']
        self.converter  = weewx.units.Converter.fromSkinDict(self.skin_dict)
        self.formatter  = weewx.units.Formatter.fromSkinDict(self.skin_dict)
        self.unit_helper= weewx.units.UnitInfoHelper(self.formatter,
                                                     self.converter)

        # Set image attributes
        self.image_width = int(self.image_dict['image_width'])
        self.image_height = int(self.image_dict['image_height'])
        self.image_background_box_color = int(self.image_dict['image_background_box_color'], 0)
        self.image_background_circle_color = int(self.image_dict['image_background_circle_color'], 0)
        self.image_background_range_ring_color = int(self.image_dict['image_background_range_ring_color'],0)
        self.image_background_image = self.image_dict['image_background_image']

        # Set windrose attributes
        self.windrose_plot_border = int(self.image_dict['windrose_plot_border'])
        self.windrose_legend_bar_width = int(self.image_dict['windrose_legend_bar_width'])
        self.windrose_font_path = self.image_dict['windrose_font_path']
        self.windrose_plot_font_size  = int(self.image_dict['windrose_plot_font_size'])
        self.windrose_plot_font_color = int(self.image_dict['windrose_plot_font_color'], 0)
        self.windrose_legend_font_size  = int(self.image_dict['windrose_legend_font_size'])
        self.windrose_legend_font_color = int(self.image_dict['windrose_legend_font_color'], 0)
        self.windrose_label_font_size  = int(self.image_dict['windrose_label_font_size'])
        self.windrose_label_font_color = int(self.image_dict['windrose_label_font_color'], 0)
        # Look for petal colours, if not defined then set some defaults
        try:
            self.petal_colors = self.image_dict['windrose_plot_petal_colors']
        except KeyError:
            self.petal_colors = ['lightblue','blue','midnightblue',
                                 'forestgreen','limegreen','green',
                                 'greenyellow']
        # Loop through petal colours looking for 0xBGR values amongst colour
        # names, set any 0xBGR to their numeric value and leave colour names
        # alone
        i = 0
        while i<len(self.petal_colors):
            try:
                # Can it be converted to a number?
                self.petal_colors[i] = int(self.petal_colors[i],0)
            except ValueError:  # Cannot convert to a number, assume it is
                                # a colour word so leave it
                pass
            i += 1
        # Get petal width, if not defined then set default to 16 (degrees)
        try:
            self.windrose_plot_petal_width = int(self.image_dict['windrose_plot_petal_width'])
        except KeyError:
            self.windrose_plot_petal_width = 16
        # Boundaries for speed range bands, these mark the colour boundaries
        # on the stacked bar in the legend. 7 elements only (ie 0, 10% of max,
        # 20% of max...100% of max)
        self.speedFactor = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]

    def genImages(self, gen_ts):
        """Generate the images.

        The time period chosen is from gen_ts going back skin.conf
        'time_length' seconds.

        gen_ts: The time stamp of the end of the plot period. If not set
                defaults to the time of the last record in the archive database.
        """

        # Time period taken to generate plots, set plot count to 0
        t1 = time.time()
        ngen = 0
        # Loop over each time span class (day, week, month, etc.):
        for timespan in self.image_dict.sections :
            # Now, loop over all plot names in this time span class:
            for plotname in self.image_dict[timespan].sections :
                # Accumulate all options from parent nodes:
                plot_options = weeutil.weeutil.accumulateLeaves(self.image_dict[timespan][plotname])
                # Get the database archive
                default_archive = self.db_binder.get_manager(self.data_binding)
                # Get end time for plot. In order try gen_ts, last known good
                # archive time stamp and then current time
                self.plotgen_ts = gen_ts
                if not self.plotgen_ts:
                    self.plotgen_ts = default_archive.lastGoodStamp()
                    if not self.plotgen_ts:
                        self.plotgen_ts = time.time()
                # Get the path of the image file we will save
                image_root = os.path.join(self.config_dict['WEEWX_ROOT'],
                                          plot_options['HTML_ROOT'])
                # Get image file format. Can use any format PIL can write
                # Default to png
                if plot_options.has_key('format'):
                    format = plot_options['format']
                else:
                    format = "png"
                # Get full file name and path for plot
                img_file = os.path.join(image_root, '%s.%s' % (plotname,format))
                # Check whether this plot needs to be done at all:
                ai = plot_options.as_int('time_length') if plot_options.has_key('time_length') else None
                if skipThisPlot(self.plotgen_ts, ai, img_file, plotname) :
                    continue
                # Create the subdirectory that the image is to be put in.
                # Wrap in a try block in case it already exists.
                try:
                    os.makedirs(os.path.dirname(img_file))
                except:
                    pass
                # Loop over each line to be added to the plot.
                for line_name in self.image_dict[timespan][plotname].sections:

                    # Accumulate options from parent nodes.
                    line_options = weeutil.weeutil.accumulateLeaves(self.image_dict[timespan][plotname][line_name])

                    # See if a plot title has been explicitly requested.
                    # 'label' used for consistency in skin.conf with
                    # ImageGenerator sections
                    label = line_options.get('label')
                    if label:
                        self.label = unicode(label, 'utf8')
                    else:
                        # No explicit label so set label to nothing
                        self.label = label
                    # See if a time_stamp has been explicitly requested.
                    self.timeStamp = line_options.get('time_stamp')
                    # See if time_stamp location has been explicitly set
                    timeStampLocation = line_options.get('time_stamp_location')
                    if timeStampLocation:
                        self.timeStampLocation = [x.upper() for x in timeStampLocation]
                    else:
                        self.timeStampLocation = None
                    # Get units to be used
                    self.units = self.skin_dict['Units']['Groups']['group_speed']
                    # Get unit label for display on legend
                    self.unit_label = self.skin_dict['Units']['Labels'][self.units]
                    # See what SQL variable type to use for this plot and get
                    # corresponding 'direction' type. Can really only plot
                    # windSpeed and windGust, if anything else default to
                    # windSpeed.
                    self.obName = line_options.get('data_type', line_name)
                    if self.obName == 'windSpeed':
                        self.dirName = 'windDir'
                    elif self.obName == 'windGust':
                        self.dirName = 'windGustDir'
                    else:
                        self.obName == 'windSpeed'
                        self.dirName = 'windDir'
                    # Get our data tuples for speed and direction.
                    # Default to 24 hour timeframe if time_length not specified
                    getSqlVectors_TS = weeutil.weeutil.TimeSpan(self.plotgen_ts - int(plot_options.get('time_length', 86400)) + 1,
                                                                self.plotgen_ts)
                    (time_vec_t_ws_start, time_vec_t_ws_stop, data_windSpeed) = default_archive.getSqlVectors(getSqlVectors_TS,
                                                                                                              self.obName)
                    (time_vec_t_wd_start, time_vec_t_wd_stop, data_windDir) = default_archive.getSqlVectors(getSqlVectors_TS,
                                                                                                            self.dirName)
                    # convert the speeds to units to be used in the plot
                    data_windSpeed = weewx.units.convert(data_windSpeed,
                                                         self.units)
                    # Find maximum speed from our data
                    maxSpeed = max(data_windSpeed.value)
                    # Set upper speed range for our plot, set to a multiple of
                    # 10 for a neater display
                    maxSpeedRange = (int(maxSpeed/10.0) + 1) * 10
                    # Setup 2D list with speed range boundaries in speedList[0]
                    # petal colours in speedList[1]
                    speedList = [[0 for x in range(7)] for x in range(2)]
                    # Store petal colours
                    speedList[1] = self.petal_colors
                    # Loop though each speed range boundary and store in
                    # speedList[0]
                    i = 1
                    while i<7:
                        speedList[0][i] = self.speedFactor[i] * maxSpeedRange
                        i += 1
                    # Setup 2D list for wind direction
                    # windBin[0] represents each of 16 compass directions
                    # ([0] is N, [1] is ENE etc).
                    # windBin[1] holds count of obs in a partiuclr speed range
                    # for given direction
                    windBin = [[0 for x in range(7)] for x in range(17)]
                    # Setup list to hold obs counts for each speed range
                    speedBin = [0 for x in range(7)]
                    # How many obs do we have?
                    samples = len(time_vec_t_ws_stop[0])
                    # Loop through each sample and increment direction counts
                    # and speed ranges for each direction as necessary. 'None'
                    # direction is counted as 'calm' (or 0 speed) and
                    # (by definition) no direction and are plotted in the
                    # 'bullseye' on the plot
                    i = 0
                    while i < samples:
                        if (data_windSpeed.value[i] is None) or (data_windDir.value[i] is None):
                            windBin[16][6] += 1
                        else:
                            bin = int((data_windDir.value[i] + 11.25)/22.5) % 16
                            if data_windSpeed.value[i] > speedList[0][5]:
                                windBin[bin][6] += 1
                            elif data_windSpeed.value[i] > speedList[0][4]:
                                windBin[bin][5] += 1
                            elif data_windSpeed.value[i] > speedList[0][3]:
                                windBin[bin][4] += 1
                            elif data_windSpeed.value[i] > speedList[0][2]:
                                windBin[bin][3] += 1
                            elif data_windSpeed.value[i] > speedList[0][1]:
                                windBin[bin][2] += 1
                            elif data_windSpeed.value[i] > 0:
                                windBin[bin][1] += 1
                            else:
                                windBin[bin][0] += 1
                        i += 1
                    # Add 'None' obs to 0 speed count
                    speedBin[0] += windBin[16][6]
                    # Don't need the 'None' counts so we can delete them
                    del windBin[-1]
                    # Now set total (direction independent) speed counts. Loop
                    # through each petal speed range and increment direction
                    # independent speed ranges as necessary
                    j = 0
                    while j < 7:
                        i = 0
                        while i < 16:
                            speedBin[j] += windBin[i][j]
                            i += 1
                        j += 1
                    # Calc the value to represented by outer ring
                    # (range 0 to 1). Value to rounded up to next multiple of
                    # 0.05 (ie next 5%)
                    self.maxRingValue = (int(max(sum(b) for b in windBin)/(0.05 * samples)) + 1) * 0.05
                    # Find which wind rose arm to use to display ring range
                    # labels - look for one that is relatively clear. Only
                    # consider NE, SE, SW and NW preference in order is
                    # SE, SW, NE and NW
                    # Is SE clear?
                    if sum(windBin[6])/float(samples) <= 0.3 * self.maxRingValue:
                        labelDir = 6        # If so take it
                    else:                   # If not lets loop through the others
                        for i in [10, 2, 14]:
                            # Is SW, NE or NW clear
                            if sum(windBin[i])/float(samples) <= 0.3*self.maxRingValue:
                                labelDir = i    # If so let's take it
                                break           # And exit for loop
                        else:                   # If none are free then let's
                                                # take the smallest of the four
                            labelCount = samples+1  # Set max possible number of
                                                    # readings+1
                            i = 2                   # Start at NE
                            for i in [2,6,10,14]:   # Loop through directions
                                # If this direction has fewer obs than previous
                                # best (least)
                                if sum(windBin[i]) < labelCount:
                                    # Set min count so far to this bin
                                    labelCount = sum(windBin[i])
                                    # Set labelDir to this direction
                                    labelDir = i
                    self.labelDir = labelDir
                    # Get our image object to hold our windrose plot
                    image = WindRoseImageSetup(self)
                    draw = ImageDraw.Draw(image)
                    # Set fonts to be used
                    self.plotFont = get_font_handle(self.windrose_font_path,
                                                    self.windrose_plot_font_size)
                    self.legendFont = get_font_handle(self.windrose_font_path,
                                                      self.windrose_legend_font_size)
                    self.labelFont = get_font_handle(self.windrose_font_path,
                                                     self.windrose_label_font_size)
                    # Estimate space requried for the legend
                    textWidth, textHeight = draw.textsize("0 (100%)",
                                                          font=self.legendFont)
                    legendWidth = int(textWidth + 2 * self.windrose_legend_bar_width + 1.5 * self.windrose_plot_border)
                    # Estimate space required for label (if required)
                    textWidth, textHeight = draw.textsize("Wind Rose",
                                                          font=self.labelFont)
                    if self.label:
                        labelHeight = int(textWidth+self.windrose_plot_border)
                    else:
                        labelHeight = 0
                    # Calculate the diameter of the circular plot space in
                    # pixels. Two diameters are calculated, one based on image
                    # height and one based on image width. We will take the
                    # smallest one. To prevent optical distortion for small
                    # plots diameter will be divisible by 22
                    self.roseMaxDiameter = min(int((self.image_height - 2 * self.windrose_plot_border-labelHeight/2)/22.0) * 22,
                                               int((self.image_width - (2 * self.windrose_plot_border+legendWidth))/22.0) * 22)
                    if self.image_width > self.image_height:    # If wider than height
                        textWidth, textHeight = draw.textsize("W",
                                                              font=self.plotFont)
                        # x coord of windrose circle origin(0,0) top left corner
                        self.originX = self.windrose_plot_border + textWidth + 2 + self.roseMaxDiameter/2
                        # y coord of windrose circle origin(0,0) is top left corner
                        self.originY = int(self.image_height/2)
                    else:
                        # x coord of windrose circle origin(0,0) top left corner
                        self.originX = 2 * self.windrose_plot_border + self.roseMaxDiameter/2
                        # y coord of windrose circle origin(0,0) is top left corner
                        self.originY = 2 * self.windrose_plot_border + self.roseMaxDiameter/2
                    # Setup windrose plot. Plot circles, range rings, range
                    # labels, N-S and E-W centre lines and compass pont labels
                    WindRosePlotSetup(self, draw)
                    # Plot wind rose petals
                    # Each petal is constructed from overlapping pieslices
                    # starting from outside (biggest) and working in (smallest)
                    a = 0   # start at 'North' windrose petal
                    while a < len(windBin): # loop through each wind rose arm
                        s = len(speedList[0]) - 1
                        cumRadius = sum(windBin[a])
                        if cumRadius > 0:
                            armRadius = int((10 * self.roseMaxDiameter * sum(windBin[a]))/(11 * 2.0 * self.maxRingValue * samples))
                            while s > 0:
                                # Calc radius of current arm
                                pieRadius = int(round(armRadius * cumRadius/sum(windBin[a]) + self.roseMaxDiameter/22, 0))
                                # Set bound box for pie slice
                                bbox = (self.originX-pieRadius,
                                        self.originY-pieRadius,
                                        self.originX+pieRadius,
                                        self.originY+pieRadius)
                                # Draw pie slice
                                draw.pieslice(bbox,
                                              int(-90 + a * 22.5 - self.windrose_plot_petal_width/2),
                                              int(-90 + a * 22.5 + self.windrose_plot_petal_width/2),
                                              fill=speedList[1][s], outline='black')
                                cumRadius -= windBin[a][s]
                                s -= 1  # Move 'in' for next pieslice
                        a += 1  # Next arm
                    # Draw 'bullseye' to represent windSpeed=0 or calm
                    # Produce the label
                    label0 = str(int(round(100.0 * speedBin[0]/sum(speedBin), 0))) + '%'
                    # Work out its size, particularly its width
                    textWidth, textHeight = draw.textsize(label0,
                                                          font=self.plotFont)
                    # Size the bound box
                    bbox = (int(self.originX-self.roseMaxDiameter/22),
                            int(self.originY-self.roseMaxDiameter/22),
                            int(self.originX+self.roseMaxDiameter/22),
                            int(self.originY+self.roseMaxDiameter/22))
                    draw.ellipse(bbox, outline='black',
                                 fill=speedList[1][0])   # Draw the circle
                    draw.text((int(self.originX-textWidth/2),int(self.originY-textHeight/2)),
                              label0,
                              fill=self.windrose_plot_font_color,
                              font=self.plotFont)   # Display the value
                    # Setup the legend. Draw label/title (if set), stacked bar,
                    # bar labels and units
                    LegendSetup(self, draw, speedList, speedBin)
                # Save the file.
                image.save(img_file)
                ngen += 1
        t2 = time.time()
        syslog.syslog(syslog.LOG_INFO, "imageStackedWindRose: Generated %d images for %s in %.2f seconds" % (ngen,
                                                                                                             self.skin_dict['REPORT_NAME'],
                                                                                                             t2 - t1))


#=============================================================================
#                            Utility Functions
#=============================================================================


def WindRoseImageSetup(self):
    """Create image object for us to draw on.

    image: Image object to be returned for us to draw on.
    """

    try:
        image = Image.open(self.image_background_image)
    except IOError as e:
        image = Image.new("RGB",
                          (self.image_width, self.image_height),
                          self.image_background_box_color)
    return image

def WindRosePlotSetup(self, draw):
    """Draw circular plot background, rings, axes and labels.

    draw: The Draw object on which we are drawing.
    """

    # Draw speed circles
    bbMinRadius = self.roseMaxDiameter/11   # Calc distance between windrose
                                            # range rings. Note that 'calm'
                                            # bulleye is at centre of plot with
                                            # diameter equal to bbMinRadius
    # Loop through each circle and draw it
    i=5
    while i > 0:
        bbox = (self.originX-bbMinRadius * (i + 0.5),
                self.originY-bbMinRadius * (i + 0.5),
                self.originX+bbMinRadius * (i + 0.5),
                self.originY + bbMinRadius * (i + 0.5))
        draw.ellipse(bbox,
                     outline=self.image_background_range_ring_color,
                     fill=self.image_background_circle_color)
        i -= 1
    # Draw vertical centre line
    draw.line([(self.originX,self.originY-self.roseMaxDiameter/2 - 2),(self.originX,self.originY+self.roseMaxDiameter/2 + 2)],
              fill=self.image_background_range_ring_color)
    # Draw horizontal centre line
    draw.line([(self.originX-self.roseMaxDiameter/2 - 2,self.originY),(self.originX+self.roseMaxDiameter/2 + 2,self.originY)],
              fill=self.image_background_range_ring_color)
    # Draw N,S,E,W markers
    textWidth, textHeight = draw.textsize('N', font=self.plotFont)
    draw.text((self.originX-textWidth/2,self.originY-self.roseMaxDiameter/2 - 1 - textHeight),
              'N', fill=self.windrose_plot_font_color, font=self.plotFont)
    textWidth, textHeight = draw.textsize('S', font=self.plotFont)
    draw.text((self.originX-textWidth/2,self.originY+self.roseMaxDiameter/2 + 3),
              'S', fill=self.windrose_plot_font_color, font=self.plotFont)
    textWidth, textHeight = draw.textsize('W', font=self.plotFont)
    draw.text((self.originX-self.roseMaxDiameter/2 - 1 - textWidth,self.originY-textHeight/2),
              'W', fill=self.windrose_plot_font_color, font=self.plotFont)
    textWidth, textHeight = draw.textsize('E', font=self.plotFont)
    draw.text((self.originX+self.roseMaxDiameter/2 + 1,self.originY-textHeight/2),
              'E', fill=self.windrose_plot_font_color, font=self.plotFont)
    # Draw % labels on rings
    labelInc = self.maxRingValue/5  # Value increment between rings
    speedLabels=list((0, 0, 0, 0, 0))   # List to hold ring labels
    i = 1
    while i<6:
        speedLabels[i-1] = str(int(round(labelInc * i * 100,0)))+'%'
        i += 1
    # Calculate location of ring labels
    labelAngle = 7 * math.pi/4 + int(self.labelDir/4.0) * math.pi/2
    labelOffsetX = int(round(self.roseMaxDiameter/22 * math.cos(labelAngle),0))
    labelOffsetY = int(round(self.roseMaxDiameter/22 * math.sin(labelAngle),0))
    # Draw ring labels. Note leave inner ring blank due to lack of space.
    # For clarity each label (except for outside ring) is drawn on a rectangle
    # with background colour set to that of the circular plot.
    i = 2
    while i < 5:
        textWidth, textHeight = draw.textsize(speedLabels[i - 1], font=self.plotFont)
        draw.rectangle(((self.originX + (2 * i + 1) * labelOffsetX - textWidth/2,self.originY + (2 * i + 1) * labelOffsetY - textHeight/2),(self.originX + (2 * i + 1) * labelOffsetX + textWidth/2,self.originY + (2 * i + 1) * labelOffsetY + textHeight/2)),
                       fill=self.image_background_circle_color)
        draw.text((self.originX + (2 * i + 1) * labelOffsetX - textWidth/2,self.originY + (2 * i + 1) * labelOffsetY -textHeight/2),
                  speedLabels[i-1],
                  fill=self.windrose_plot_font_color, font=self.plotFont)
        i += 1
    # Draw outside ring label
    textWidth, textHeight = draw.textsize(speedLabels[i-1], font=self.plotFont)
    draw.text((self.originX + (2 * i + 1) * labelOffsetX - textWidth/2, self.originY + (2 * i + 1) * labelOffsetY-textHeight/2),
              speedLabels[i-1],
              fill=self.windrose_plot_font_color, font=self.plotFont)

def LegendSetup(self, draw, speedList, speedBin):
    """Draw plot title (if requested), legend and time stamp (if requested).

    draw: The Draw object on which we are drawing.

    speedList: 2D list with speed range boundaries in speedList[0] and petal
    colours in speedList[1]

    speedBin: 1D list to hold overal obs count for each speed range
    """

    # set static values
    textWidth, textHeight = draw.textsize('E', font=self.plotFont)
    # labelX and labelY = x,y coords of bottom left of stacked bar.
    # Everything else is relative to this point
    labelX = self.originX+self.roseMaxDiameter/2 + textWidth + 10
    labelY = self.originY+self.roseMaxDiameter/2 - self.roseMaxDiameter/22
    bulbDiameter = int(round(1.2 * self.windrose_legend_bar_width, 0))
    # draw stacked bar and label with values/percentages
    i = 6
    while i > 0:
        draw.rectangle(((labelX, labelY - (0.85 * self.roseMaxDiameter * self.speedFactor[i])), (labelX + self.windrose_legend_bar_width, labelY)),
                       fill=speedList[1][i], outline='black')
        textWidth, textHeight = draw.textsize(str(speedList[0][i]),
                                              font=self.legendFont)
        draw.text((labelX + 1.5 * self.windrose_legend_bar_width, labelY - textHeight/2 - (0.85 * self.roseMaxDiameter * self.speedFactor[i])),
                  str(int(round(speedList[0][i], 0))) + ' (' + str(int(round(100 * speedBin[i]/sum(speedBin), 0))) + '%)',
                  fill=self.windrose_legend_font_color, font=self.legendFont)
        i -= 1
    textWidth, textHeight = draw.textsize(str(speedList[0][0]),
                                          font=self.legendFont)
    # Draw 'calm' or 0 speed label and %
    draw.text((labelX + 1.5 * self.windrose_legend_bar_width, labelY - textHeight/2 - (0.85 * self.roseMaxDiameter * self.speedFactor[0])),
              str(speedList[0][0]) + ' (' + str(int(round(100.0 * speedBin[0]/sum(speedBin), 0))) + '%)',
              fill=self.windrose_legend_font_color, font=self.legendFont)
    textWidth, textHeight = draw.textsize('Calm', font=self.legendFont)
    draw.text((labelX - textWidth - 2, labelY - textHeight/2 - (0.85 * self.roseMaxDiameter * self.speedFactor[0])),
              'Calm',
              fill=self.windrose_legend_font_color, font=self.legendFont)
    # draw 'calm' bulb on bottom of stacked bar
    bbox = (labelX-bulbDiameter/2 + self.windrose_legend_bar_width/2,
            labelY - self.windrose_legend_bar_width/6,
            labelX + bulbDiameter/2 + self.windrose_legend_bar_width/2,
            labelY - self.windrose_legend_bar_width/6 + bulbDiameter)
    draw.ellipse(bbox, outline='black', fill=speedList[1][0])
    # draw legend title
    if self.obName == 'windGust':
        titleText = 'Gust Speed'
    else:
        titleText = 'Wind Speed'
    textWidth, textHeight = draw.textsize(titleText, font=self.legendFont)
    draw.text((labelX + self.windrose_legend_bar_width/2 - textWidth/2, labelY - 5 * textHeight/2 - (0.85 * self.roseMaxDiameter)),
              titleText,
              fill=self.windrose_legend_font_color, font=self.legendFont)
    # draw legend units label
    textWidth, textHeight = draw.textsize('(' + self.unit_label.strip() + ')',
                                          font=self.legendFont)
    draw.text((labelX + self.windrose_legend_bar_width/2 - textWidth/2, labelY - 3 * textHeight/2 - (0.85 * self.roseMaxDiameter)),
              '(' + self.unit_label.strip() + ')',
              fill=self.windrose_legend_font_color, font=self.legendFont)
    # draw plot title (label) if any
    if self.label:
        textWidth, textHeight = draw.textsize(self.label, font=self.labelFont)
        try:
            draw.text((self.originX - textWidth/2, textHeight/2),
                      self.label,
                      fill=self.windrose_label_font_color,
                      font=self.labelFont)
        except UnicodeEncodeError:
            draw.text((self.originX - textWidth/2, textHeight/2),
                      self.label.encode("utf-8"),
                      fill=self.windrose_label_font_color,
                      font=self.labelFont)
    # draw plot timestamp if any
    if self.timeStamp:
        timeStampText = datetime.datetime.fromtimestamp(self.plotgen_ts).strftime(self.timeStamp).strip()
        textWidth, textHeight = draw.textsize(timeStampText,
                                              font=self.labelFont)
        if self.timeStampLocation is not None:
            if 'TOP' in self.timeStampLocation:
                timeStampY = self.windrose_plot_border + textHeight
            else:
                timeStampY = self.image_height - self.windrose_plot_border - textHeight
            if 'LEFT' in self.timeStampLocation:
                timeStampX = self.windrose_plot_border
            elif ('CENTER' in self.timeStampLocation) or ('CENTRE' in self.timeStampLocation):
                timeStampX = self.originX-textWidth/2
            else:
                timeStampX = self.image_width - self.windrose_plot_border - textWidth
        else:
            timeStampY = self.image_height - self.windrose_plot_border - textHeight
            timeStampX = self.image_width - self.windrose_plot_border - textWidth
        draw.text((timeStampX,timeStampY),
                  timeStampText,
                  fill=self.windrose_legend_font_color, font=self.legendFont)

def skipThisPlot(time_ts, time_length, img_file, plotname):
    """    Plots must be generated if:
    (1) it does not exist
    (2) it is 24 hours old (or older)

    Every plot, irrespective of time_length, will likely be different to the
    last one but to reduce load for long time_length plots a plot can be
    skipped if:
    (1) no time_length was specified (need to put entry in syslog)
    (2) plot length is greater than 30 days and the plot file is less than
        24 hours old
    (3) plot length is greater than 7 but less than 30 day and the plot file
        is less than 1 hour old
    (4) can't think of another reason! Let's see how (1) and (2) go

    time_ts: Timestamp holding time of plot

    time_length: Length of time over which plot is produced

    img_file: Full path and filename of plot file

    plotname: Name of plot
    """

    # Images without a time_length must be skipped every time and a syslog
    # entry added.
    if time_length is None:
        syslog.syslog(syslog.LOG_INFO, "imageStackedWindRose: Plot " + plotname + " ignored, no time_length specified")
        return True

    # The image definitely has to be generated if it doesn't exist.
    if not os.path.exists(img_file):
        return False

    # If the image is older than 24 hours then regenerate
    if time_ts - os.stat(img_file).st_mtime >= 86400:
        return False

    # If time_length > 30 days and the image is less than 24 hours old then skip
    if time_length > 18144000 and time_ts - os.stat(img_file).st_mtime < 86400:
        return True

    # If time_length > 7 days and the image is less than 1 hour old then skip
    if time_length >= 604800 and time_ts - os.stat(img_file).st_mtime < 3600:
        return True

    # Otherwise we must regenerate
    return False
