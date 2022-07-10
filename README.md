[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](http://www.gnu.org/licenses/lgpl-3.0)

Create your own Mapsforge maps with MapCreator
==============================================

**For the new process using Geofabrik see [here](https://github.com/mapsforge/mapsforge-creator).**

With the coastline and water issues, creating a mapsforge map is not as simple as it should be, but here we offer a scripted solution that includes these additional steps.

Mapsforge uses the process described here to build maps for the download.mapsforge.org site. The process is run on a Linux machine with 8 cores, 24GB memory and 2TB of storage. The process has not been tested on any other operating system, running this on Windows or OSX will most likely require some changes. 

Cook Book
---------

1. Clone mapsforge-mapcreator `git clone https://github.com/mapsforge/mapsforge-mapcreator.git`
2. In the directory xml you will find an example configuration file, named example-config. You will need to edit this file to suit your installation and your map requirements.
3. You will also need polygons for any area you want to build a map for. The polygons are found in the polygons directory. 
4. Run `python mapcreator.py -c xml/myconfigfile.xml`

The configuration file
-----------------------

The configuration file has a number of settings and path specifications in the top, adjust them to your environment:

```xml
<mapcreator-config xmlns="http://mapsforge.org/mapcreator" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
	xsi:schemaLocation="http://mapsforge.org/mapcreator https://raw.githubusercontent.com/mapsforge/mapsforge-mapcreator/master/resources/mapcreator.xsd"
	default-map-start-zoom="14" map-staging-path="maps" pbf-staging-path="data" polygons-path="polygons" map-target-path="/web/ftp.mapsforge.org/public/maps"
	logging-path="logs" initial-source-pbf="planet.osm.pbf" osmosis-path="/export/local-1/public/mapsforge/preprocessing/bin/osmosis-0.40.1/bin/osmosis"
	default-preferred-languages="en">
```

The second part are the maps to be created. Map definitions look like this:

```xml
<part name="great_britain" create-pbf="true" map-start-lat="51.499266" map-start-lon="-0.124787">
	<part name="england" map-start-lat="51.50728" map-start-lon="-0.12766" defines-hierarchy="false">
	    <part name="greater_london" map-start-lat="51.50728" map-start-lon="-0.12766"/>
	</part>
	<part name="scotland" map-start-lat="55.94834" map-start-lon="-3.19327"/>
	<part name="wales" map-start-lat="51.48353" map-start-lon="-3.18369"></part>
</part>
```
	
A part directive specifies an extract from the original pbf file, from which either only pbf extracts are made or/and maps. For every part for which a map will be created you will need to define a start point that needs to lie within the polygon. Every part requires a correspondingly named polygon in the polygons folder (at the same depth).

These are some of the more important options for each part:
 - **name** required and needs to have a matching polygon in the polygons directory.
 - **create-map** if a map should be created or simply a pbf extract that can be used for parts of this part (this is a speed issue, extracting everything from a top-level planet can be very slow).
 - **create-pbf** if true will create a pbf file that can subsequently be used for parts of this part.
 - **type** if set to hd uses less memory, but much slower
 - **map-start-zoom** start zoom level
 - **map-start-lat**
 - **map-start-lon** starting position, must be within polygon
 - **preferred-languages** If not specified, only the default language with no tag will be written to the file. If only one language is specified, it will be written if its tag is found, otherwise the default language will be written. If multiple comma separated languages are specified, the default language will be written, followed by the specified languages (if present and if different than the default).

For all options see https://github.com/mapsforge/mapsforge-mapcreator/blob/master/resources/mapcreator.xsd

Notes
-----
 - This script will not download the initial file, e.g. [planet pbf](https://wiki.openstreetmap.org/wiki/Planet.osm). 
 - You will need a working [Osmosis](http://wiki.openstreetmap.org/wiki/Osmosis) installation
 - You will need the mapsforge writer installed
 - Requirements: [GDAL](http://www.gdal.org/) , [Shapely](http://toblerity.org/shapely/)
 - If you are making something like a world map, you might consider the zoom-interval-config setting as well as the land-simplification setting, which reduces the number of nodes in the land borders (higher=more simplification).
 - It might be worthwhile to first try this process without any changes applied and full planet.pbf file, to rule out any configuration problems.
