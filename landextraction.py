#!/usr/bin/python
# -*- coding: utf-8 -*-

from shapely.geometry import MultiPolygon, Polygon
import os
import logging.config
from logging.handlers import RotatingFileHandler
from logging.handlers import SMTPHandler
import shape2osm



class LandExtractor:

    def __init__(self, output_dir, polygon_dir, dry_run = False):
        self.logger = logging.getLogger("mapcreator")
        self.polygon_dir = polygon_dir
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self.polygon_ext = ".poly"
        self.dry_run = dry_run
        # self.landfiles = "land-polygons-complete-4326"  # there seems to be a bug in that data
        self.landfiles = "land-polygons-split-4326"

    def parse_poly(self, lines):
        """ Parse an Osmosis polygon filter file.
        
        Accept a sequence of lines from a polygon file, return a shapely.geometry.MultiPolygon object.
        
        http://wiki.openstreetmap.org/wiki/Osmosis/Polygon_Filter_File_Format
        Source taken from 
        http://wiki.openstreetmap.org/wiki/Osmosis/Polygon_Filter_File_Python_Parsing
        """
        in_ring = False
        coords = []
        
        for (index, line) in enumerate(lines):
            if index == 0:
                # first line is junk.
                continue
        
            elif index == 1:
                # second line is the first polygon ring.
                coords.append([[], []])
                ring = coords[-1][0]
                in_ring = True
        
            elif in_ring and line.strip() == 'END':
                # we are at the end of a ring, perhaps with more to come.
                in_ring = False
    
            elif in_ring:
                # we are in a ring and picking up new coordinates.
                ring.append(map(float, line.split()))
    
            elif not in_ring and line.strip() == 'END':
                # we are at the end of the whole polygon.
                break
    
            elif not in_ring and line.startswith('!'):
                # we are at the start of a polygon part hole.
                coords[-1][1].append([])
                ring = coords[-1][1][-1]
                in_ring = True
    
            elif not in_ring:
                # we are at the start of a polygon part.
                coords.append([[], []])
                ring = coords[-1][0]
                in_ring = True
    
        return MultiPolygon(coords)


    def polygon_bbox(self, polygon_file, buffer=0.1):
        with open(polygon_file) as f:
            polygon = self.parse_poly(f.readlines())
            return polygon.buffer(buffer).intersection(self.world_polygon()).bounds

    def sea_polygon_file(self, bbox, output):
        template = """<osm version='0.6'>
        <node timestamp='1969-12-31T23:59:59Z' changeset='-1' id='32951459320' version='1' lon='{lonmin}' 
        lat='{latmin}' />
        <node timestamp='1969-12-31T23:59:59Z' changeset='-1' id='32951459321' version='1' lon='{lonmin}' 
        lat='{latmax}' />
        <node timestamp='1969-12-31T23:59:59Z' changeset='-1' id='32951459322' version='1' lon='{lonmax}' 
        lat='{latmax}' />
        <node timestamp='1969-12-31T23:59:59Z' changeset='-1' id='32951459323' version='1' lon='{lonmax}' 
        lat='{latmin}' />
        <way timestamp='1969-12-31T23:59:59Z' changeset='-1' id='32951623372' version='1'>
        <nd ref='32951459320' />
        <nd ref='32951459321' />
        <nd ref='32951459322' />
        <nd ref='32951459323' />
        <nd ref='32951459320' />
        <tag k='area' v='yes' />
        <tag k='layer' v='-5' />
        <tag k='natural' v='sea' />
        </way>
        </osm>
        """
        with open(self.sea_path(output), "w+") as f:
            f.write(template.format(lonmin=bbox[0], latmin=bbox[1], lonmax=bbox[2], latmax=bbox[3]))

    def world_polygon(self):
        return Polygon([(-180, 90), (180, 90), (180, -90), (-180, -90), (-180, 90)])

    def region_bbox(self, region):
        return self.polygon_bbox(self.polygon_dir + region + self.polygon_ext)

    def make_sea_polygon_file(self, region):
        self.logger.info("Making sea polygon for " + region)
        bbox = self.region_bbox(region)
        self.sea_polygon_file(bbox, region)

    def download_land_polygons(self, data_dir):
        import urllib
        import zipfile
        self.logger.info("Retrieving new land files")
        if not self.dry_run:
            path = os.path.join(data_dir, self.landfiles + ".zip")
            #urllib.urlretrieve ("http://data.openstreetmapdata.com/" + self.landfiles + ".zip", path)
            zfile = zipfile.ZipFile(path)
            print data_dir
            zfile.extractall(data_dir)
        self.logger.info("Retrieved new land files")

    def extract_land_polygons(self, region, data_dir, simplify=0):
        import subprocess
        simplifiy = 0.2
        bbox = self.region_bbox(region)
        if simplify == 0:
            ogr_call = ["ogr2ogr", "-overwrite", "-skipfailures", "-clipsrc", str(bbox[0]), str(bbox[1]), str(bbox[2]), str(bbox[3]), os.path.join(self.output_dir, region.replace("/", "-")), os.path.join(data_dir, os.path.join(self.landfiles, "land_polygons.shp"))]
        else:
            ogr_call = ["ogr2ogr", "-overwrite", "-skipfailures", "-simplify", str(simplify), "-clipsrc", str(bbox[0]), str(bbox[1]), str(bbox[2]), str(bbox[3]), os.path.join(self.output_dir, region.replace("/", "-")), os.path.join(data_dir, "land-polygons-split-4326/land_polygons.shp")]
        self.logger.debug("calling: %s"," ".join(ogr_call))
        success = subprocess.call(ogr_call)
        shape2osm.run(self.land_polygon_path(region), output_location=self.land_path_base(region))

    def land_polygon_path(self, region):
        """
        path to the shapefile containing the land polygons
        """
        return os.path.join(os.path.join(self.output_dir, region.replace("/", "-")), "land_polygons.shp")
        
    def sea_path(self, region):
        return os.path.join(self.output_dir, region.replace("/", "-") + "-sea.osm")
    def land_path_base(self, region):
        """
        returns path to land file but without the numbers and extension
        """
        return os.path.join(self.output_dir, region.replace("/", "-"))
        
    def land_path(self, region):
        """
        returns path to land file with first extension, which should be sufficient
        """        
        return self.land_path_base(region) + ".osm"


if __name__ == '__main__':
    polygon_dir = "polygons/"
    output_dir = "test"

    landExtractor = LandExtractor(output_dir, polygon_dir)

    landExtractor.download_land_polygons("data")

    for region in ["europe", "asia", "europe/greece", "europe/ukraine"]:
        landExtractor.make_sea_polygon_file(region)
        landExtractor.extract_land_polygons(region, "data")







    
