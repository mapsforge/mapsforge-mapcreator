#! /usr/bin/env python
'''
Created on 08.10.2012

@author: bross
'''
try:
    from lxml import etree as ET
    from lxml.etree import XMLSchema
    from lxml.etree import XMLSyntaxError
    from lxml.etree import XMLSchemaValidateError
except ImportError:
    from xml.etree import ElementTree as ET    
from optparse import OptionParser
from subprocess import CalledProcessError

import logging.config
from logging.handlers import RotatingFileHandler
from logging.handlers import SMTPHandler
# hack to support logging config file in python 2.5 with these handlers
logging.RotatingFileHandler = RotatingFileHandler
logging.SMTPHandler = SMTPHandler
import os
import os.path as PATH
import subprocess
import sys
import landextraction

class MapCreator:
    '''
    classdocs
    '''
    def __init__(self, osmosis_path, pbf_staging_path, map_staging_path, polygons_path,
                  initial_source_pbf, target_path, logging_path, default_start_zoom, default_preferred_languages, dry_run=False):
        '''
        Constructor
        '''
        self.osmosis_path = osmosis_path
        self.pbf_staging_path = normalize_path(pbf_staging_path)
        self.map_staging_path = normalize_path(map_staging_path)
        self.polygons_path = normalize_path(polygons_path)
        self.initial_source_pbf = initial_source_pbf
        self.logging_path = normalize_path(logging_path)
        self.target_path = normalize_path(target_path)
        self.default_start_zoom = default_start_zoom
        self.default_preferred_languages = default_preferred_languages
        self.dry_run = dry_run

        self.logger = logging.getLogger("mapcreator")
        self.landExtractor = landextraction.LandExtractor(self.pbf_staging_path, self.polygons_path, self.dry_run)

        self.logger.info("start downloading new land polygons")
        self.landExtractor.download_land_polygons(self.pbf_staging_path)
        

    def evalPart(self, subtree, source_pbf, staging_path, target_dir, zoom_interval_conf, land_simplification):
        
        error_occurred = False
        
        for child in subtree:            
            current_part_name = child.get('name')
            self.logger.info("evaluating part '%s'", staging_path + current_part_name)
            
            # get attributes from xml element
            create_map = child.get('create-map', default='true') == 'true'
            create_pbf = child.get('create-pbf', default='false') == 'true'
            defines_hierarchy = child.get('defines-hierarchy', default='true') == 'true'
            storage_type = child.get('type',default='ram')
            map_start_zoom = child.get('map-start-zoom', default=self.default_start_zoom)
            # lat/lon maybe None
            map_start_lat = child.get('map-start-lat')
            map_start_lon = child.get('map-start-lon')
            preferred_languages = child.get('preferred-languages', self.default_preferred_languages)
            # if not None, convert lat/lon to float
            if map_start_lat:
                map_start_lat = float(map_start_lat)
            if map_start_lon:
                map_start_lon = float(map_start_lon)
                
            
            # we do not need to filter the area during map creation if either a pbf was created (with a filter)
            # or the source pbf equals the current part
            area_filter = not(create_pbf or PATH.basename(source_pbf).startswith(current_part_name))
                
            if create_pbf: 
                # create pbf
                try:        
                    # the new source pbf for the subtree and this child is the newly created one
                    new_source_pbf = self.call_create_pbf(source_pbf, staging_path, current_part_name)                                        
                except ProcessingException, e:
                    error_occurred = True
                    self.logger.warning("%s, skipping all sub parts", str(e))
                    #print "an error occurred while creating pbf for '%s', no further processing of sub-parts will take part, error message: %s" % (current_part_name, e)
                    # we need to skip processing of sub parts
                    continue                
            else:
                # we didn't create a new pbf, so the new source pbf is the old one
                new_source_pbf = source_pbf
                
            if create_map:
                self.landExtractor.make_sea_polygon_file(staging_path + current_part_name)
                self.landExtractor.extract_land_polygons(staging_path + current_part_name, self.pbf_staging_path, land_simplification)
                try:
                    self.call_create_map(new_source_pbf, staging_path, target_dir, current_part_name, area_filter, map_start_zoom, preferred_languages, zoom_interval_conf, storage_type, map_start_lat, map_start_lon)
                except ProcessingException, e:
                    error_occurred = True
                    self.logger.warning("%s", str(e))
                    #print "an error occurred while creating map for '%s', error message: %s" % (current_part_name, e)
                    # errors while creating the map file do not harm any sub parts
                    # continue with processing sub parts
            
            if defines_hierarchy:
                # this part defines a new level in the output hierarchy
                new_target_dir = target_dir + child.get('name') + '/'
            else:
                new_target_dir = target_dir;
        
            new_staging_path = staging_path + child.get('name') + '/'
            
            #### RECURSION         
            subpart_error = self.evalPart(child, new_source_pbf, new_staging_path, new_target_dir, zoom_interval_conf, land_simplification)
            error_occurred = subpart_error or error_occurred
            
            # clean up files
            pbf_file_path = self.pbf_staging_path+new_source_pbf
            if create_pbf and PATH.exists(pbf_file_path):
                if not error_occurred:
                    self.logger.debug("removing pbf file %s",pbf_file_path)
                    os.remove(pbf_file_path)
                else:
                    self.logger.debug("error occurred in sub part, keeping pbf file %s",pbf_file_path)
                
        return error_occurred
                
    
    def call_create_pbf(self, source_pbf, staging_dir, current_part_name):
        
        # set the path to the pbf file
        target_pbf = staging_dir + current_part_name + '.osm.pbf'
        target_pbf_path = check_create_path(self.pbf_staging_path+target_pbf)
        if PATH.exists(target_pbf_path):
            self.logger.info("the pbf file %s already exists, using the existing one", target_pbf)
            return target_pbf
        
       
        # check whether source pbf exists and has non-zero size (irrelevant for dry run)
        source_pbf_path = self.pbf_staging_path + source_pbf
        if not self.dry_run:
            if not PATH.exists(source_pbf_path):
                raise ProcessingException('cannot create %s, source pbf is missing: %s' % (target_pbf,source_pbf_path))
            if PATH.getsize(source_pbf_path) == 0:
                raise ProcessingException('cannot create %s, source pbf is empty: %s' % (target_pbf,source_pbf_path))
    
        polygons_path = self.polygons_path + staging_dir + current_part_name+'.poly'
        if not PATH.exists(polygons_path):
            raise ProcessingException('cannot create pbf %s , polygon is missing: %s' % (target_pbf, polygons_path))
        
        
        
          
        osmosis_call = [self.osmosis_path, '--rb',source_pbf_path]
        osmosis_call += ['--bp','completeWays=yes','completeRelations=yes','clipIncompleteEntities=false','file=%s'%polygons_path]
        osmosis_call += ['--wb','omitmetadata=false','compress=deflate','file=%s'%target_pbf_path]
        logfile_path = check_create_path(self.logging_path + staging_dir + current_part_name + '.pbf.log')
        logfile = open(logfile_path,'a')
        try:
            self.logger.debug("calling: %s"," ".join(osmosis_call))
            if not self.dry_run:
                subprocess.check_call(osmosis_call,stderr=logfile)
            else:
                subprocess.check_call(['touch',target_pbf_path])
            logfile.close()
            
            if not self.dry_run and PATH.getsize(target_pbf_path) == 0:
                raise ProcessingException('error creating %s, resulting pbf is empty' % (target_pbf_path))
            
            return target_pbf
        except CalledProcessError:
            logfile.close()
            raise ProcessingException("call to osmosis raised an error, see logs at %s for further details"%logfile_path)
        except OSError,e:
            raise ProcessingException("osmosis executable not found: %s"%e)
    
    def call_create_map(self, source_pbf, staging_dir, target_dir, current_part_name, area_filter, start_zoom, preferred_languages, zoom_interval_conf, storage_type='ram', lat=None,lon=None):
        
        # set the path to the map file
        map_file = staging_dir + current_part_name + ".map"
        
        # check whether source pbf exists and has non-zero size (irrelevant for dry run)
        source_pbf_path = self.pbf_staging_path + source_pbf
        if not self.dry_run:
            if not PATH.exists(source_pbf_path):
                raise ProcessingException('cannot create map %s, source pbf is missing: %s' % (map_file,source_pbf_path))
            if PATH.getsize(source_pbf_path) == 0:
                raise ProcessingException('cannot create map %s, source pbf is empty: %s' % (map_file,source_pbf_path))            
        
        osmosis_call = [self.osmosis_path,'--rb', source_pbf_path]
        
        if area_filter:
            polygon_file_path = self.polygons_path+ staging_dir+current_part_name + '.poly'
            if not PATH.exists(polygon_file_path):
                raise ProcessingException('cannot create map %s, polygon is missing: %s' % (map_file, polygon_file_path))
            osmosis_call += ['--bp','completeWays=yes','completeRelations=yes','clipIncompleteEntities=false','file=%s'%polygon_file_path]
        
        # read in the sea and land areas
        sea_path = self.landExtractor.sea_path(staging_dir + current_part_name)
        osmosis_call += ['--rx','file=%s'%sea_path]
        osmosis_call += ['--sort']
        osmosis_call += ['--merge']

        land_path = self.landExtractor.land_path(staging_dir + current_part_name)
        osmosis_call += ['--rx','file=%s'%land_path]
        osmosis_call += ['--sort']
        osmosis_call += ['--merge']

        
        # construct complete path from relative path
        map_file_path = check_create_path(self.map_staging_path + map_file)        
        osmosis_call += ['--mw','file=%s'%map_file_path]
        osmosis_call += ['%s'%zoom_interval_conf]
        osmosis_call += ['type=%s'%storage_type]
        osmosis_call += ['map-start-zoom=%s'%start_zoom]
        osmosis_call += ['preferred-languages=%s'%preferred_languages]
        bbox = self.landExtractor.region_bbox(staging_dir + current_part_name)
        osmosis_call += ['bbox=%s,%s,%s,%s'%(str(bbox[1]), str(bbox[0]),str(bbox[3]),str(bbox[2]))]

        if lat != None and lon != None:
            osmosis_call += ['map-start-position=%0.8f,%0.8f'%(lat,lon)]
                            
        #### CALL TO OSMOSIS #####
        logfile_path = check_create_path(self.logging_path + staging_dir + current_part_name + '.map.log')
        logfile = open(logfile_path,'a')
        try:
            self.logger.debug("calling: %s"," ".join(osmosis_call))
            if not self.dry_run:
                subprocess.check_call(osmosis_call,stderr=logfile)
            else:
                subprocess.check_call(['touch',map_file_path])
            logfile.close()
        except CalledProcessError:
            logfile.close()        
            raise ProcessingException("call to osmosis raised an error, see logs at %s for further details"%logfile_path)
        except OSError,e:
            raise ProcessingException("osmosis executable not found: %s"%e)             
        
        if not self.dry_run and PATH.getsize(map_file_path) == 0:
            raise ProcessingException("resulting map file size for %s is zero, keeping old map file" % map_file)
        
        map_file_target_path = check_create_path(self.target_path + target_dir+current_part_name + '.map')                
        move_call = ["mv",map_file_path, map_file_target_path]
        self.logger.debug("calling: %s"," ".join(move_call))
        if not self.dry_run:
            try:
                subprocess.check_call(move_call)
            except:        
                raise ProcessingException("could not move created map %s to target directory" % map_file)
        
def check_create_path(path):
    directory = PATH.dirname(path)
    if not PATH.exists(directory):
        os.makedirs(directory)
    return path
def normalize_path(path):
    path = path.strip()
    if path and not path.endswith('/'):
        path = path + '/'
    return path               
        
class ProcessingException(Exception):
    '''
    classdocs
    ''' 
    
def main():
    
    ######## SETUP OPTION PARSER AND READ COMMAND LINE ARGS ##########
    
    usage = "usage: %prog -c CONFIGURATION_FILE [-d]"
    option_parser = OptionParser(usage,version='1.0')
    option_parser.add_option("-c", "--configuration-file", dest="configuration_file",
                             action='store',help="the path to the XML configuration file")
    option_parser.add_option("-d", "--dry-run", dest="dry_run",
                             action='store_true', default=False,
                             help="only execute a dry run without calls to osmosis [default=false]")
    option_parser.add_option("-l", "--logging-conf", dest="logging_config_file",
                             action='store', default='logging.conf',
                             help="path to the logging configuration [default=logging.conf]")
    (options, args) = option_parser.parse_args()
           
    if len(args) != 0:
        option_parser.print_help()
        sys.exit("incorrect number of arguments")
    
    if not options.configuration_file:
        option_parser.print_help()
        sys.exit("configuration file is missing")    
    
    # check whether xml configuration exists    
    if not PATH.exists(options.configuration_file) or not PATH.isfile(options.configuration_file):
        sys.exit("the xml configuration file at '%s' could not be found" % options.configuration_file)
        
    
    
    ######## READING SCHEMA AND XML CONFIG ###########
    
    try:
        # load XML schema file
        xmlschema_doc = ET.parse('resources/mapcreator.xsd')
        xmlschema = XMLSchema(xmlschema_doc)
        parser = ET.XMLParser(schema=xmlschema,remove_comments=True)
        # try to load xml configuration, validate with schema    
        tree = ET.parse(options.configuration_file, parser=parser)
    except NameError:
        tree = ET.parse(options.configuration_file)
    except (XMLSyntaxError,XMLSchemaValidateError), e:
        sys.exit("the xml configuration is not valid: '%s'" %e)
        
    root = tree.getroot()
    default_start_zoom = root.get('default-start-zoom',default=14)
    default_preferred_languages = root.get('default-preferred-languages','en')
    initial_source_pbf = root.get('initial-source-pbf')
    pbf_staging_path = root.get('pbf-staging-path')
    map_staging_path = root.get('map-staging-path')
    polygons_path = root.get('polygons-path')
    map_target_path = root.get('map-target-path')
    logging_path = root.get('logging-path')
    osmosis_path = root.get('osmosis-path',default='osmosis')
    land_simplification = root.get('land-simplification', 0)
    zoom_interval_conf = root.get('zoom-interval-conf',default='')
    if zoom_interval_conf != "":
        zoom_interval_conf = "zoom-interval-conf=" + zoom_interval_conf

    full_osmosis_path = which(osmosis_path)        
    if not full_osmosis_path:
        sys.exit("the osmosis path is not valid, must be an executable file: '%s'" %osmosis_path)
      
    ########### LOGGING ###############  
    # if logging configuration is provided use this
    if options.logging_config_file and PATH.isfile(options.logging_config_file):
        try:
            logging.config.fileConfig(options.logging_config_file)
            logger = logging.getLogger("mapcreator")
            if options.dry_run:
                # only perform console logging during dry run
                # remove all other handlers than StreamHandler
                
                # to remove handler in for-loop, copy sequence by slicing
                for handler in logger.handlers[:]:
                    # need explicit check by name as 'isinstance()' also is true for subclasses                    
                    if handler.__class__.__name__ != 'StreamHandler' :
                        logger.removeHandler(handler)
                    else:
                        handler.setLevel(logging.DEBUG)                
        except Exception, e:            
            # use default logging if reading from file failed
            logger = setup_logging(logging_path, options.dry_run)
            logger.warning("log configuration file not valid, using default configuration: %s",e)
    else:
        # no logging conf provided, use default
        logger = setup_logging(logging_path, options.dry_run)
               
    
    ########### START PROCESSING ############

    logger.info("start creating maps from configuration at: '%s'", options.configuration_file)
    creator = MapCreator(full_osmosis_path,pbf_staging_path, map_staging_path, polygons_path,
                         initial_source_pbf, map_target_path, logging_path,
                         default_start_zoom, default_preferred_languages, options.dry_run)
    creator.evalPart(root, initial_source_pbf, '', '', zoom_interval_conf, land_simplification)                

def setup_logging(logging_path, dry_run):
    
    # check and create path to logging
    logging_path = check_create_path(normalize_path(logging_path))
    
    # obtain and configure logger
    # we use a console handler to log warnings and more critical problems
    # the rotating file handler logs at debug level 
    logger = logging.getLogger("mapcreator")
    logger.setLevel(logging.DEBUG)    
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # during a dry run we only want to log to the console
    if not dry_run:
        # ROTATING LOG HANDLER        
        rh = logging.handlers.RotatingFileHandler(logging_path+'mapcreator.log',
                                                  maxBytes=1048576, backupCount=5)
        rh.setLevel(logging.DEBUG)
        rh.setFormatter(formatter)
        logger.addHandler(rh)
    
    # CONSOLE LOG HANDLER
    sh = logging.StreamHandler()
    # during a dry run the console should receive all logs 
    if not dry_run:
        sh.setLevel(logging.WARN)
    sh.setFormatter(formatter)
    logger.addHandler(sh)   
    
    return logger

# used to check the path to the osmosis script
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

if __name__ == '__main__':
    main()
