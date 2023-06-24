#Here are all the packages to observe the schedule table.
import argparse
###2022: Import logging to log timestamps of lines. Set the logger output file with timestamps for logger lines.
import logging
import os
import time
from datetime import datetime

import photometrics
from astropy import units as u
from astropy.io import ascii
from astropy.time import Time
from photometrics.camera_control import recenter_and_capture
from photometrics.pomona import Controller
from photometrics.syntrack_client import SynTrackClient

# sys.path.insert(0,'~/Software/repos/worktree/scheduler/tmocass')
logger = logging.getLogger(__name__)
logging.basicConfig(filename=os.fspath('obs.log'), filemode='a', format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')

#Assuming that the above structure for the Scheduler stays intact, I present the below method to observe 
#these series of objects. Begin by connecting to the telescope and setting some directories.
parser = argparse.ArgumentParser(description="TMO Automation Code")
parser.add_argument('directory', type=str, help="Input/Output directory")
args = vars(parser.parse_args())

scope = Controller()
scope.connect(photometrics.TELESCOPE_CONTROLLER)
port = '/dev/ttyS0'
linux_dirname = args['directory']

#Begin by importing the exported Scheduler table back in.
with open(linux_dirname+'/Scheduler.txt', 'rb') as infile:
    Scheduler = ascii.read(infile)

#Convert time column back into time objects.
Scheduler["DateTimeObj"] = [Time(row["DateTime"]) for row in Scheduler]

# Get windows directory path.
print('Set SynTrack archive path')
tmp = os.path.abspath(linux_dirname).split('/')
dirname = tmp[3] + ':'
for val in tmp[4:]:
    dirname += '/' + val
    
syntrack_client = SynTrackClient()
syntrack_client.connect(photometrics.SYNTRACK_IP, photometrics.SYNTRACK_PORT)
syntrack_client.set_archive_path(dirname)

# Metadata file name.
print('Set SynTrack metadata filename')
syntrack_client.set_metadata_filename('%s/%s' % (dirname, 'Metadata.db'))

for row in Scheduler:
    while True:
        if Time.now() < row["DateTimeObj"]-30*u.second:
            print('Waiting.')
            time.sleep(1)
        elif row["DateTimeObj"]-30*u.second < Time.now() and Time.now() < row["DateTimeObj"]:
            if row["Occupied"] == 1 and row["Move"] == 1:
                ra = row["RA"]
                if ra < 0: 
                    ra += 360
                if ra > 360:
                    ra -= 360
                dec = row["Dec"]
                
                #####Changes below#####
                exptime1 = str(row["ExposureTime"])
                exptime2 = float(str(row["ExposureTime"]))                
                nframes1 = str(row["#Exposure"])
                nframes2 = str(row["#Exposure"])
                print(nframes2)
                #####Scheduler output needs to be formatted such that #ofFrames is an INTEGER not a FLOAT and the 2 lines below can be removed#####
                #####This needs to run from an appropriate data spot to save data to archive correctly#####
                print(nframes2[:-2])
                nframes3 = int(nframes2[:-2])
                #####Changes above and in 82 and 83 below#####
                
                ###2022: Log the timestamp of telescope slewing as the start of a given observation.
                print('Moving to coordinates: ('+str(ra)+','+str(dec)+')')
                logger.info('Moving to coordinates: ('+str(ra)+','+str(dec)+')')
                scope.ra_dec(ra, dec)
                time.sleep(5.0)
                
                print('Calculating offset and recentering')
                recenter_exptime = 10.0
                print(linux_dirname)
                print(row["Target"])
                logger.info('Target name: '+row["Target"])
                
                #####The following two versions of recenter and capture are for Scheduler made and manually made schedules respectively (manual schedules have
                #####a 'Description' column and Scheduler made schedules do NOT have the description column)
                #####(2022)- Scheduler.txt file needs first row to be the columns desired so add or remove "|Description" as necessary
                #recenter_and_capture(linux_dirname, exptime2, nframes3, row["Target"],
                               #row["Target"]+' '+exptime1+' observation', recenter_exptime, syntrack_client, scope, do_bin2fits=True)
                               
                #recenter_and_capture(linux_dirname, exptime2, nframes3, row["Target"],
                               #row["Description"], recenter_exptime, syntrack_client, scope, do_bin2fits=True)
                # added filter info 20221121
                recenter_and_capture(linux_dirname, exptime2, nframes3, row["Target"],
                               row["Description"], recenter_exptime, syntrack_client, scope, do_bin2fits=True, filter_name=row["Filter"])
                
                ###2022: Log the timestamp of official dataset start.
                print('Exposing for '+str(float(exptime2)*float(nframes1))+' seconds.')
                logger.info('Exposing for '+str(float(exptime2)*float(nframes1))+' seconds.')
                
                #capture_single(linux_dirname, exptime2, nframes3, row["Target"],
                               #row["Target"]+' '+exptime1+' observation', syntrack_client, scope = scope, do_bin2fits = False)
            elif row["Occupied"] == 1 and row["Target"] == "Focus":
                logger.info('Refocusing...')
                now = datetime.now()
                suffix = now.strftime('%Y-%m-%dT%H:%M:%S')
                
                shell_cmd = 'python3 ../Autofocus_v1.1.py focusloop_'+suffix
                os.system(shell_cmd)
                
                # The following lines are crucial: we need to reinit syntrack, or else the first science cube after focusloop will be killed
                syntrack_client = SynTrackClient()
                syntrack_client.connect(photometrics.SYNTRACK_IP, photometrics.SYNTRACK_PORT)
                syntrack_client.set_archive_path(dirname)
                syntrack_client.set_metadata_filename('%s/%s' % (dirname, 'Metadata.db'))
            	
            # added the following elif 20221106 to allow moving scope without take_images
            elif row["Occupied"] == 0 and row["Move"] == 1 and row["Target"] == "MoveScope":
                ra = float(row["RA"])
                dec = float(row["Dec"])

                print('Moving to coordinates: ('+str(ra)+','+str(dec)+')')
                logger.info('Moving to coordinates: ('+str(ra)+','+str(dec)+')')
                scope.ra_dec(ra, dec)
                time.sleep(5.0)
                
            elif row["Occupied"] == 1 and row["Move"] == 0:
			
                exptime = float(str(row["ExposureTime"]))                
                nframes0 = str(row["#Exposure"])
                nframes = int(nframes0[:-2])

                print(linux_dirname)
                print(row["Target"])
                logger.info('Target name: '+row["Target"])
                
                #_,_ = capture_single(linux_dirname, exptime, nframes, row["Target"],
                #               row["Description"], syntrack_client, scope=scope, do_bin2fits=True, filter_name=row["Filter"])
                shell_cmd = 'take_images ./ '+str(exptime)+' '+str(nframes)+' '+str(row["Target"])+' '+str(row["Description"])+' '+str(row["Filter"])
                os.system(shell_cmd)

            else:
                pass
        elif Time.now() > row["DateTimeObj"]:
            print('No longer observable.')
            break
            







#---------------------Sanity Checks---------------------------

#from photometrics.utils import get_sidereal_time
#from tcs.telemetry import RoofStatus, Weather, Seeing, SkyBrightness
