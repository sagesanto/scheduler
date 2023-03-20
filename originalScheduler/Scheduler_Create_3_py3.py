#In this part of the code, I will be defining a class variable for NEO targets and MPC targets separately for future convenience. Also I will be defining a function that decides whether an object is observable at a given time from a given location with given constraints.

#Below are all the packages imported that are required to query the ephemerides for both MPC and NEO targets.
import os 
import weakref
import math
import numpy as np
import argparse
from astropy import units as u
from astropy.time import Time
from astropy.coordinates import Angle
from astroquery.jplhorizons import Horizons

#And here are all the packages for the airmass calculation of the MPC targets.
from astropy.utils import iers
from astropy.utils.data import clear_download_cache
iers.IERS_A_URL = 'ftp://ftp.iers.org/products/eop/rapid/standard/finals2000A.all'
iers.IERS_A_URL_MIRROR = 'https://datacenter.iers.org/data/latestVersion/9_FINALS.ALL_IAU2000_V2013_019.txt'
iers.conf.iers_auto_url = 'ftp://ftp.iers.org/products/eop/rapid/standard/finals2000A.all'
iers.conf.iers_auto_url_mirror = 'https://datacenter.iers.org/data/latestVersion/9_FINALS.ALL_IAU2000_V2013_019.txt'
clear_download_cache(iers.IERS_A_URL)
clear_download_cache(iers.IERS_A_URL_MIRROR)
from astroplan import download_IERS_A
download_IERS_A()
from astroplan import Observer
from astroplan import FixedTarget
from astropy.coordinates import SkyCoord

#Here are the packages necessary for the observing schedule table.
import astropy.table as at
from datetime import datetime, timedelta

#I use ascii to save the table to be passed on to the observing module.
from astropy.io import ascii

#I use random behaviors to fuel the initial schedule generation.
import random
import copy

#Now I define a class for the MPC objects, NEOs and stationary targets.
class MPCObj:

    _instances = set()

    def __init__(self, name, datetime, ra, dec, mag, airmass, epochs, exptime, expnum, camfilt):
        self.name = name
        self.time = np.asarray(datetime)
        self.ra = np.asarray(ra)
        self.dec = np.asarray(dec)
        self.mag = np.asarray(mag)
        self.airmass = np.asarray(airmass)
        self.epochs = epochs
        self.exptime = exptime
        self.expnum = expnum
        self.camfilt = camfilt
        self._instances.add(weakref.ref(self))

    @classmethod
    def getinstances(cls): #loop over all MPC objects with 'for obj in MPCObj.getinstances()'
        dead = set()
        for ref in cls._instances:
            obj = ref()
            if obj is not None:
                yield obj
            else:
                dead.add(ref)
        cls._instances -= dead

class HorizonsObj:

    _instances = set()

    def __init__(self, name, datetime, ra, dec, mag, airmass, epochs, exptime, expnum, camfilt):
        self.name = name
        self.time = np.asarray(datetime)
        self.ra = np.asarray(ra)
        self.dec = np.asarray(dec)
        self.mag = np.asarray(mag)
        self.airmass = np.asarray(airmass)
        self.epochs = epochs
        self.exptime = exptime
        self.expnum = expnum
        self.camfilt = camfilt
        self._instances.add(weakref.ref(self))

    @classmethod
    def getinstances(cls): #loop over all Horizons objects with 'for obj in HorizonsObj.getinstances()'
        dead = set()
        for ref in cls._instances:
            obj = ref()
            if obj is not None:
                yield obj
            else:
                dead.add(ref)
        cls._instances -= dead

class StationaryObj:

    _instances = set()

    def __init__(self, name, datetime, ra, dec, mag, airmass, epochs, exptime, expnum, camfilt):
        self.name = name
        self.time = np.asarray(datetime)
        self.ra = np.asarray(ra)
        self.dec = np.asarray(dec)
        self.mag = np.asarray(mag)
        self.airmass = np.asarray(airmass)
        self.epochs = epochs
        self.exptime = exptime
        self.expnum = expnum
        self.camfilt = camfilt
        self._instances.add(weakref.ref(self))

    @classmethod
    def getinstances(cls): #loop over all Stationary objects with 'for obj in StationaryObj.getinstances()'
        dead = set()
        for ref in cls._instances:
            obj = ref()
            if obj is not None:
                yield obj
            else:
                dead.add(ref)
        cls._instances -= dead

#Below is a function that can quickly generate strings of time between two given dates at a desired interval.
###2022 Note: This section is completely self-contained.
def datetime_range(start, end, delta):
    current = start
    while current <= end:
        yield current
        current += delta
        
#Here is a function to run into a given directory and look for text files that contain the ephemerides information. 
#For MPC targets, I look for the output of Navtej's script, and for NEOs a list of target names.
def get_ephemerides(directory, obs_times):
    for index, file in enumerate(os.listdir(directory)):
        if file.endswith('_eph.txt'):
            Input = np.genfromtxt(directory + file, delimiter=' ',
                             skip_header=2, skip_footer=0, dtype=str, encoding=None)
                             
            magnitude = [row[21] for row in Input]
            print(magnitude[0])
            
            if Input.size == 0:
                pass
            else:
            
                Objname = file.replace('_eph.txt','')
        
                date = [row[0] for row in Input]
                time = [row[1] for row in Input]
                date_time = [date[i] + ' ' + time[i] for i in range(np.shape(Input)[0])]
                DateTime = Time(date_time, scale='utc', location=('-117.6818d','34.3820d','2286m'))
                
                RA = [Angle(":".join(i) + ' hours').degree for i in Input[:,5:8]]
                Dec = [Angle(":".join(i) + ' degrees').degree for i in Input[:,11:14]]
                print(RA)
                print("RA IS ABOVE THIS")
                #RightAscension = [(":".join(i) + ' hours') for i in Input[:,5:8]]
                #print(RightAscension)
                
                if float(19.5) > float(magnitude[0]):
                    Objects[Objname] = MPCObj(Objname, DateTime, RA, Dec, Input[:,21], [0.0]*np.shape(Input)[0],
                                         3, 1, 300, 'CLEAR')
                elif float(20.5) > float(magnitude[0]) >= float(19.5):
                    Objects[Objname] = MPCObj(Objname, DateTime, RA, Dec, Input[:,21], [0.0]*np.shape(Input)[0],
                                         3, 1, 600, 'CLEAR')
                elif float(21.0) > float(magnitude[0]) >= float(20.5):
                    Objects[Objname] = MPCObj(Objname, DateTime, RA, Dec, Input[:,21], [0.0]*np.shape(Input)[0],
                                         3, 2, 600, 'CLEAR')
                elif float(21.5) >= float(magnitude[0]) >= float(21.0):
                    Objects[Objname] = MPCObj(Objname, DateTime, RA, Dec, Input[:,21], [0.0]*np.shape(Input)[0],
                                         3, 3, 600, 'CLEAR')
                else:
                    print('MPC target too dim, excluding.')
        
        elif file == ('Confirmed.txt'):
            IInput = np.genfromtxt(directory + file, delimiter='\t', dtype=str, encoding=None)
            IInput = np.array(IInput, ndmin=1)
            if IInput.size == 0:
                pass
            else:
                for Objname in IInput: 
                    start = obs_times[0].iso
                    end = obs_times[-1].iso
                    asteroid = Horizons(id=Objname, location='654', 
                                        epochs={'start':start, 'stop':end,'step':'1m'}, id_type='smallbody')
                    ephemerides = asteroid.ephemerides(quantities='1,3,8,9,20,23,24,25')
            
                    DateTime2 = Time(ephemerides['datetime_jd'], format='jd', scale='utc', 
                                     location=('-117.6818d','34.3820d','2286m'))
                
                    RA2 = [Angle(str(i) + ' degree').degree for i in ephemerides['RA']]
                
                    Dec2 = [Angle(str(i) + ' degree').degree for i in ephemerides['DEC']]
                
                    Objects[Objname] = HorizonsObj(Objname, DateTime2, RA2, Dec2, np.array(ephemerides['V']), 
                                                   np.array(ephemerides['airmass']), 3, 1, 600, 'CLEAR')
        elif file == ('Stationary.txt'):
            IIInput = np.genfromtxt(directory + file, delimiter = ' ', dtype=str, encoding=None)
            if IIInput.size == 0:
                pass
            else:
                if IIInput.size == 8:
                    IIInput = [IIInput]
                for row in IIInput:
                    RA3 = [Angle(row[1] + 'hour').degree]*len(obs_times)
                    
                    Dec3 = [Angle(row[2] + 'degree').degree]*len(obs_times)
                    #print('delimeter reached')
                    #print(row[0])
                    #print(row[1])
                    
                    Objects[row[0]] = StationaryObj(row[0], obs_times, RA3, Dec3, [row[3]]*len(obs_times), [0.0]*len(obs_times), int(row[4]), int(row[5]), int(row[6]), row[7])
                    
        else:
            pass

#Here is the function that decides whether a given target is observable at a given time at a given position with HA and Dec constraints that are also defined. This is to be later used to determine the observability of the MPC objects and the observable periods for the NEOs.
def is_observable(target, ha_constraint, dec_constraint):
    #print(target.dec)
    #print(dec_constraint)
    dec_mask = (target.dec < dec_constraint[1]) & (target.dec > dec_constraint[0])
    sidereal_time = np.zeros(target.time.size)
    for i in range(target.time.size):
        sidereal_time[i] = target.time[i].sidereal_time('apparent').degree   
    ha = np.subtract(sidereal_time, target.ra)
    ha = (ha + 180) % 360 - 180
    print('Is Observable?')
    print(ha)
    #print(sidereal_time)
    #print(target.ra)
    print(ha_constraint)
    ha_mask = (ha < ha_constraint[1]) & (ha > ha_constraint[0])
    return dec_mask * ha_mask
        
#Here is a quick function to fill in the airmass column of an object. 
def get_airmass(obj):
    for i in range(np.shape(obj.time)[0]):
        coordinates = SkyCoord(obj.ra[i], obj.dec[i], unit='deg')
        target = FixedTarget(name=obj.name, coord=coordinates)
        obj.airmass[i] = tmo.altaz(obj.time[i], target).secz
        #print(coordinates)
        #print(len(obj.airmass[i]))
        #print(i)

#Here I define a function to grab a weighted index to fuel the semi-random behavior of the generation.
###2022: random.random() returns a random percentage in range [0,1), so then rnd is the percentage of the summed weights of all targets in a given schedule. We subtract a weight value (w) from rnd until rnd is negative, then we return the index (i) of the last subtracted weight value (associated with an object in the list). MAYBE this is how we pick a random object in the Objects list, since later we assign the returned index to the ID associated with the random object we're picking.
def weighted_randomizer(weights):
    rnd = random.random() * sum(weights)
    for i, w in enumerate(weights):
        rnd -= w
        if rnd < 0:
            return i
        
#Define the function that generates the initial state. Please note that this has a lot of implicit dependency on the presence of other variables that are already present.
def initial_state(Objects, Scheduler, selected, l1, l2, l3, fill):
    
    #First I generate the weights or the priorities of all the objects. For now, it is solely airmass based.
    weights = []
    for obj in list(Objects):
        #print((Objects[obj].airmass))
        
        ###2022: Find the location/index of the lowest airmass value available in the ephemeris of a given object. Define weights to be the inverse of that airmass value, i.e. higher weights are given to objects with lower airmass values.
        loc_id = np.argmin(Objects[obj].airmass, axis=0)
        weights.append(1/(Objects[obj].airmass[loc_id]))
    
    #Start a loop that generates a random object. Grab its airmass data and identify the minimum.
    n1 = 0
    limit1 = l1
    while True:
        rnd_id = weighted_randomizer(weights)
        rnd_obj = list(Objects)[rnd_id]
        obs_len = int(math.ceil((Objects[rnd_obj].exptime*Objects[rnd_obj].expnum)/60.0)+2) 
        
        #Now check if the selected object was previously placed before. If placed, skip it and if not, proceed.
        if rnd_obj in list(selected):
            continue
        else:
            rnd_airmass = Objects[rnd_obj].airmass
            airmass_id = np.argmin(rnd_airmass, axis=0)
            tmp = Objects[rnd_obj].name
            #print(tmp)
            #print(Objects[rnd_obj].airmass[4])
            #print(rnd_obj)
            #print(len(rnd_airmass))
        
            #Now we find the best n-hour airmass window of our object around the best airmass.
            epochs = Objects[rnd_obj].epochs
            best_t = epochs*60
            if len(rnd_airmass) < best_t:
                print('1')
                #print(rnd_airmass)
                #print(best_t)
                mask = [True]*len(rnd_airmass)
                #print(mask)
                #print(mask[-obs_len:])
                #print([-obs_len])
                mask[-obs_len:] = [False]*obs_len
                #print([False]*obs_len)
                #print(mask)
                #print(obs_len)
            else:
                mask = [False]*len(rnd_airmass)
                print(len(mask))
                if len(rnd_airmass[:airmass_id]) < best_t/2:
                    print('2')
                    #print(best_t)
                    mask[:best_t] = [True]*best_t
                    mask[-obs_len:] = [False]*obs_len
                elif len(rnd_airmass[airmass_id:]) < best_t/2:
                    print('3')
                    #print(best_t)
                    mask[-best_t:] = [True]*best_t
                    mask[-obs_len:] = [False]*obs_len
                else:
                    print('4')
                    #print(best_t)
                    #print(obs_len)
                    #print(len(mask))
                    mask[airmass_id-int((best_t/2)):airmass_id+int((best_t/2))] = [True]*best_t
                    #print(len(mask))
                    mask[-obs_len:] = [False]*obs_len
                    #print(len(mask))
                    #print(len([False]*obs_len))
        
            #And generate n random observations of this object in the best airmass window.
            #print(Objects[rnd_obj].time)
            #print(len(mask))
            #print(len(Objects[rnd_obj].time))
            time_sub = Objects[rnd_obj].time[mask]
            time_sub = [round(row.jd,5) for row in time_sub]
            n2 = 0
            limit2 = l2
            while True:
                n3 = 0
                limit3 = l3
                while True:
                    obs = random.sample(time_sub, k=epochs)
                    n3 += 1
                    if np.all(np.array([abs(x-y) for i,x in enumerate(obs) for j,y in enumerate(obs) if i > j]) 
                              > 0.02083) == True:
                        break
                    elif n3 > limit3:
                        break
                             
                #Proceed to attempt to place these observations in the Scheduler, with limiting number of tries.
                timelist = [round(row.jd,5) for row in Scheduler["DateTime"]]
                sch_id = [timelist.index(obs[i]) for i in range(epochs)]
                occupation = sum([sum(Scheduler["Occupied"][sch_id[i]:sch_id[i]+obs_len]) for i in range(epochs)])
                
                if  occupation == 0:
                    selected[rnd_obj] = rnd_obj
                    for i in range(epochs):
                        obj_loc_id = [round(row.jd, 5) for row in Objects[rnd_obj].time].index(obs[i])
                        Scheduler["Occupied"][sch_id[i]:sch_id[i]+obs_len] = 1 
                        Scheduler["Target"][sch_id[i]:sch_id[i]+obs_len] = [Objects[rnd_obj].name]*obs_len
                        Scheduler["Move"][sch_id[i]] = 1
                        Scheduler["RA"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].ra[obj_loc_id:(obj_loc_id+obs_len)]
                        Scheduler["Dec"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].dec[obj_loc_id:(obj_loc_id+obs_len)]
                        Scheduler["ExposureTime"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].exptime
                        Scheduler["#Exposure"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].expnum
                        Scheduler["Filter"][sch_id[i]:sch_id[i]+obs_len] = [Objects[rnd_obj].camfilt]*obs_len
                    break
                elif n2 > limit2:
                    break
                else:
                    n2 += 1
        print(float(sum(Scheduler["Occupied"]))/len(Scheduler))
        if float(sum(Scheduler["Occupied"]))/len(Scheduler) > fill:
            print(str(fill)+' fill reached. Stopping.')
            break
        elif len(selected) == len(Objects):
            print('Selected:', selected)
            print('Out of objects. Stopping.')
            break
        elif n1 > limit1:
            print('Selected:', selected)
            print('Exceeded number of tries. Stopping.')
            break
        else:
            n1 += 1

###2022: Define the following function for checking the number of observations of a given target in a schedule.
def check_number_obs(target_name):
    number_obs = 0
    for i in range(len(Scheduler)):
        if Scheduler["Target"][i] == target_name and Scheduler["Move"][i] == 1:
            Scheduler["Move"][i] = number_obs
            number_obs += 1
    return number_obs

#Define the following five functions that are the linearly independent operations on a schedule to generate a new one, used in the ascent algorithm.

def add_object():
    
    #Select an object at random and check whether it is in the already selected objects.
    rnd_id = random.choice(range(len(list(Objects))))
    rnd_obj = list(Objects)[rnd_id]
    
    #If it is not, then define its observing parameters and generate the random observations.
    if rnd_obj not in list(selected):
        obs_len = int(math.ceil((Objects[rnd_obj].exptime*Objects[rnd_obj].expnum)/60.0)+2) #S 3/2/23: duration of observation, in epochs (?), renamed from obs_len
        epochs = Objects[rnd_obj].epochs #these are the windows (epochs) that the observation takes place in
        #S 3/2/23 grab a random sample of times from the last obs_len times on the schedule
        obs = random.sample(list(Objects[rnd_obj].time[:-obsDur]), k=epochs)
        
        #Ensure that the observations do not overlap. 
        if np.all(np.array([abs(x-y) for i,x in enumerate(obs) for j,y in enumerate(obs) if i > j]) > 0.000694444*obsDur) == True: #S 3/2/23: 0.000694444 is one minute in days, this line should probably be made a function
            
            #If they do not, proceed to attempt to place them. 
            timelist = [round(row.jd,5) for row in Scheduler["DateTime"]]
            sch_id = [timelist.index(round(obs[i].jd,5)) for i in range(epochs)]

            #S 3/2/23: Adding these variables for code readability, refactoring indices below
            epochStart = sch_id[i]
            epochEnd = epochStart + obsDur
            randObject = Objects[rnd_obj]
            
            occupation = sum([sum(Scheduler["Occupied"][epochStart:epochEnd]) for i in range(epochs)])
            if  occupation == 0:
                selected[rnd_obj] = rnd_obj
                for i in range(epochs):
                    obj_loc_id = [round(row.jd, 5) for row in randObject.time].index(round(obs[i].jd,5))
                    oIDstart, oIDEnd = obj_loc_id, obj_loc_id + obsDur #S 3/2/23: added for readability
                    Scheduler["Occupied"][epochStart:epochEnd] = 1 
                    Scheduler["Target"][epochStart:epochEnd] = [randObject.name]*obsDur
                    Scheduler["Move"][epochStart] = 1
                    Scheduler["RA"][epochStart:epochEnd] = randObject.ra[oIDstart:oIDEnd]
                    Scheduler["Dec"][epochStart:epochEnd] = randObject.dec[oIDstart:oIDEnd]
                    Scheduler["ExposureTime"][epochStart:epochEnd] = randObject.exptime
                    Scheduler["#Exposure"][epochStart:epochEnd] = randObject.expnum
                    Scheduler["Filter"][epochStart:epochEnd] = [randObject.camfilt]*obsDur
                    
def remove_object():
    
    #Select an object at random from the selected list.
    if len(list(selected)) != 0:
        rnd_id = random.choice(range(len(list(selected))))
        rnd_obj = list(selected)[rnd_id]
    
        #Find the observations in the scheduler amd set to default values.
        for row in Scheduler:
            if row["Target"] == selected[rnd_obj]:
                row["Occupied"] = 0
                row["Target"] = 'No target'
                row["Move"] = 0
                row["RA"] = 0.0
                row["Dec"] = 0.0
                row["ExposureTime"] = 0.0
                row["#Exposure"] = 0.0
                row["Filter"] = 'No filter'
        del selected[rnd_obj]
    
def add_observation(): ## ADD NO TIME OVERLAP ##
    
    #Select an object at random from the selected objects.
    if len(list(selected)) != 0:
        rnd_id = random.choice(range(len(list(selected))))
        rnd_obj = list(selected)[rnd_id]
        
        #Check the number of scheduled observations for it.
        number_of_obs = check_number_obs(rnd_obj)
        
        #Sample a random observation for it.
        ###2022: obs_len stores the rounded integer representation of the time it takes to complete one observation of a random object in minutes. obs rounds all the times associated with the random object selected from the Objects list during its observation length to 5 decimal places.
        obs_len = int(math.ceil((Objects[rnd_obj].exptime*Objects[rnd_obj].expnum)/60.0)+2) 
        obs = round(random.choice(Objects[rnd_obj].time[:-obs_len]).jd,5)
        epochs = 1
        
        #Attempt to place it.
        ###2022: Round all datetimes in Scheduler to 5 decimal places. sch_id stores the index of obs (the datetime row corresponding to the sampled random observation).
        timelist = [round(row.jd,5) for row in Scheduler["DateTime"]]
        sch_id = [timelist.index(obs) for i in range(epochs)]
        #print('Value and type of sch_id:', sch_id, type(sch_id))
        
        ###2022: The double sum's function seems to be to make the inner sum an integer.
        occupation = sum([sum(Scheduler["Occupied"][sch_id[i]:sch_id[i]+obs_len]) for i in range(epochs)])

        ###2022: If the sampled object does not occupy any rows in the Scheduler, proceed to add an observation.
        ###2022: The following while loop USED to be done with an if statement and ONLY the occupation == 0 condition (never satisfied).
        while occupation == 0 or number_of_obs < 3:
            #epochs = Objects[rnd_obj].epochs
            selected[rnd_obj] = rnd_obj
            for i in range(epochs):
                obj_loc_id = [round(row.jd, 5) for row in Objects[rnd_obj].time].index(obs)
                Scheduler["Occupied"][sch_id[i]:sch_id[i]+obs_len] = 1 
                Scheduler["Target"][sch_id[i]:sch_id[i]+obs_len] = [Objects[rnd_obj].name]*obs_len
                Scheduler["Move"][sch_id[i]] = 1
                Scheduler["RA"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].ra[obj_loc_id:(obj_loc_id+obs_len)]
                Scheduler["Dec"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].dec[obj_loc_id:(obj_loc_id+obs_len)]
                Scheduler["ExposureTime"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].exptime
                Scheduler["#Exposure"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].expnum
                Scheduler["Filter"][sch_id[i]:sch_id[i]+obs_len] = [Objects[rnd_obj].camfilt]*obs_len
                number_of_obs += 1
                print(i)
                print('Incremented observations:', number_of_obs)
        else:
            return

                    
def remove_observation():
    
    #Select an object at random from the selected objects.
    if len(list(selected)) != 0:
        rnd_id = random.choice(range(len(list(selected))))
        rnd_obj = list(selected)[rnd_id]
        obs_len = int(math.ceil((Objects[rnd_obj].exptime*Objects[rnd_obj].expnum)/60.0)+2) 
        epochs = Objects[rnd_obj].epochs
    
        #Find all of its observations in the scheduler.
        count = 2
        for row in Scheduler:
            if row["Target"] == Objects[rnd_obj].name and row["Move"] == 1:
                row["Move"] = count
                count += 1
    
        #If the object has more than the intended amount of observations, then proceed.
        if count > epochs+2:
        
            #Pick an observation at random:
            rnd_obs = random.choice(range(2,count))
        
            #Find the row again.
            for i in range(len(Scheduler)):
                if Scheduler["Target"][i] == Objects[rnd_obj].name and Scheduler["Move"][i] == rnd_obs:
                
                    #Set to the original values.
                    length = len(Scheduler["Occupied"][i:i+obs_len])
                    Scheduler["Occupied"][i:i+obs_len] = [0]*length
                    Scheduler["Target"][i:i+obs_len] = ['No target']*length
                    Scheduler["Move"][i:i+obs_len] = [0]*length
                    Scheduler["RA"][i:i+obs_len] = [0.0]*length
                    Scheduler["Dec"][i:i+obs_len] = [0.0]*length
                    Scheduler["ExposureTime"][i:i+obs_len] = [0.0]*length
                    Scheduler["#Exposure"][i:i+obs_len] = [0.0]*length
                    Scheduler["Filter"][i:i+obs_len] = ['No filter']*length
                
        #Now fix the move column values that were changed before. 
        for i in range(len(Scheduler)):
            if Scheduler["Target"][i] == Objects[rnd_obj].name and Scheduler["Move"][i] != 0:
                Scheduler["Move"][i] = 1
                
def replace_observation():
    
    #Select an object at random from the selected objects.
    if len(list(selected)) != 0:
        rnd_id = random.choice(range(len(list(selected))))
        rnd_obj = list(selected)[rnd_id]
        obs_len = int(math.ceil((Objects[rnd_obj].exptime*Objects[rnd_obj].expnum)/60.0)+2)
        epochs = 1
    
        #Find all of its observations in the scheduler.
        #number_of_obs = check_number_obs(rnd_obj)
        count = 2
        for row in Scheduler:
            if row["Target"] == Objects[rnd_obj].name and row["Move"] == 1:
                row["Move"] = count
                count += 1
                #print('Inc. count:', count)
            return count
        
        #Pick an observation at random:
        obs = round(random.choice(Objects[rnd_obj].time[:-obs_len]).jd,5)
        rnd_obs = random.choice(range(2,count))
        
        org_obs = 0
        
        #Find the row again.
        def temp_original():
            for i in range(len(Scheduler)):
                if Scheduler["Target"][i] == Objects[rnd_obj].name and Scheduler["Move"][i] == rnd_obs:
                
                    #Set to the original values. Remember where the observation was removed from.
                    global org_obs
                    org_obs = copy.deepcopy(i)
                    print('Deep copy of row:', org_obs)
                    length = len(Scheduler["Occupied"][i:i+obs_len])
                    Scheduler["Occupied"][i:i+obs_len] = [0]*length
                    Scheduler["Target"][i:i+obs_len] = ['No target']*length
                    Scheduler["Move"][i:i+obs_len] = [0]*length
                    Scheduler["RA"][i:i+obs_len] = [0.0]*length
                    Scheduler["Dec"][i:i+obs_len] = [0.0]*length
                    Scheduler["ExposureTime"][i:i+obs_len] = [0.0]*length
                    Scheduler["#Exposure"][i:i+obs_len] = [0.0]*length
                    Scheduler["Filter"][i:i+obs_len] = ['No filter']*length
        
        print('Org_obs before:',org_obs)
        temp_original()
        print('org_obs after:', org_obs) 
                
        #Now fix the move column values that were changed before.
        #for i in range(len(Scheduler)):
            #if Scheduler["Target"][i] == Objects[rnd_obj].name and Scheduler["Move"][i] != 0:
                #Scheduler["Move"][i] = 1
                
        #Sample a random observation for it. 
        obs = round(random.choice(Objects[rnd_obj].time[:-obs_len]).jd,5)
    
        #Attempt to place it.
        timelist = [round(row.jd,5) for row in Scheduler["DateTime"]]
        sch_id = [timelist.index(obs) for i in range(epochs)]
        occupation = sum([sum(Scheduler["Occupied"][sch_id[i]:sch_id[i]+obs_len]) for i in range(epochs)])
        
        if occupation == 0:
            
            print('Replace atempted')
            for i in range(epochs):
                obj_loc_id = [round(row.jd, 5) for row in Objects[rnd_obj].time].index(obs)
                Scheduler["Occupied"][sch_id[i]:sch_id[i]+obs_len] = 1 
                Scheduler["Target"][sch_id[i]:sch_id[i]+obs_len] = [Objects[rnd_obj].name]*obs_len
                Scheduler["Move"][sch_id[i]] = 1
                Scheduler["RA"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].ra[obj_loc_id:(obj_loc_id+obs_len)]
                Scheduler["Dec"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].dec[obj_loc_id:(obj_loc_id+obs_len)]
                Scheduler["ExposureTime"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].exptime
                Scheduler["#Exposure"][sch_id[i]:sch_id[i]+obs_len] = Objects[rnd_obj].expnum
                Scheduler["Filter"][sch_id[i]:sch_id[i]+obs_len] = [Objects[rnd_obj].camfilt]*obs_len
                
        #If it fails, place the removed observation back.
        else:
            print('HERE:', timelist[org_obs])
            print('HERE:', timelist[1])
            print(len(Objects[rnd_obj].time))
            print('HERE:', [round(row.jd, 5) for row in Objects[rnd_obj].time])
            obj_loc_id = [round(row.jd, 5) for row in Objects[rnd_obj].time].index(timelist[org_obs])
            Scheduler["Occupied"][org_obs:org_obs+obs_len] = 1
            Scheduler["Target"][org_obs:org_obs+obs_len] = [Objects[rnd_obj].name]*obs_len
            Scheduler["Move"][org_obs] = 1
            #print('Dimension 1:', len(Scheduler["RA"][org_obs:org_obs+obs_len]))
            #print('Dimension 2:', len(Objects[rnd_obj].ra[obj_loc_id:(obj_loc_id+obs_len)]))
            Scheduler["RA"][org_obs:org_obs+obs_len] = Objects[rnd_obj].ra[obj_loc_id:(obj_loc_id+obs_len)]
            Scheduler["Dec"][org_obs:org_obs+obs_len] = Objects[rnd_obj].dec[obj_loc_id:(obj_loc_id+obs_len)]
            Scheduler["ExposureTime"][org_obs:org_obs+obs_len] = Objects[rnd_obj].exptime
            Scheduler["#Exposure"][org_obs:org_obs+obs_len] = Objects[rnd_obj].expnum
            Scheduler["Filter"][org_obs:org_obs+obs_len] = [Objects[rnd_obj].camfilt]*obs_len

parser = argparse.ArgumentParser(description="TMO Automation Code")
parser.add_argument('directory', type=str, help="Input/Output directory")
parser.add_argument('obs_start', type=str, help="Observation starting time, format YYYYMMDDhhmm")
parser.add_argument('obs_end', type=str, help="Observation ending time, format YYYYMMDDhhmm")
args = vars(parser.parse_args())

#Begin by defining the time interval and some necessary quantities.
tmo = Observer(latitude=34.3820*u.deg, longitude=-117.6818*u.deg, elevation=2286*u.meter, 
               name='tmo', timezone='US/Pacific')
ha_constraint = [-30,60]
dec_constraint = [-10,50]
begin = args['obs_start']
end = args['obs_end']
obs_start = datetime(int(begin[0:4]),int(begin[4:6]),int(begin[6:8]),int(begin[8:10]),int(begin[10:]))
obs_end = datetime(int(end[0:4]),int(end[4:6]),int(end[6:8]),int(end[8:10]),int(end[10:]))
interval = timedelta(minutes=1)
obs_times = [Time(dt.strftime('%Y-%m-%dT%H:%M:00'), scale='utc', location=('-117.6818d','34.3820d','2286m')) 
             for dt in datetime_range(obs_start, obs_end, interval)]

#And read in all the MPC and NEO targets.
Objects = {}
selected = {}
directory = args['directory']
get_ephemerides(directory, obs_times)

# Now I fill in the airmasses for the MPC objects and stationary objects that were missing from our catalogue.
for obj in MPCObj.getinstances():
    print('START')
    get_airmass(obj)
    #print(obj.name)
    #print('test')
for obj in StationaryObj.getinstances():
    print('START')
    get_airmass(obj)
    #print(obj.name)
    #print('test')
         
#And I will reduce to the targets that are observable at least for a minute in the observing period
#and I will trim their ephemerides to the observable periods.
for obj in list(Objects):
    observability = is_observable(Objects[obj], ha_constraint, dec_constraint)
    if any(observability) is False:
        print(str(Objects[obj].name) + ' is not observable.')
        del Objects[obj]
    else:
        Objects[obj].time = Objects[obj].time[observability]
        Objects[obj].ra = Objects[obj].ra[observability]
        Objects[obj].dec = Objects[obj].dec[observability]
        Objects[obj].airmass = Objects[obj].airmass[observability]
        Objects[obj].mag = Objects[obj].mag[observability]

#Now that we have all our objects prepared, we can create the table and start defining its columns.
Scheduler = at.Table()
Scheduler["DateTime"] = obs_times
Scheduler["Occupied"] = [0]*len(obs_times)
Scheduler["Target"] = np.array(['No target']*len(obs_times), dtype='object')
Scheduler["Move"] = [0]*len(obs_times)
Scheduler["RA"] = [0.0]*len(obs_times)
Scheduler["Dec"] = [0.0]*len(obs_times)
Scheduler["ExposureTime"] = [0.0]*len(obs_times)
Scheduler["#Exposure"] = [0.0]*len(obs_times)
Scheduler["Filter"] = ['No filter']*len(obs_times)

###
#check_number_obs()
###

#And finally since we have all of our objects and our observing schedule table, we build a schedule.
initial_state(Objects, Scheduler, selected, 25, 10, 100, 0.75)

# Define a function that evaluates the quality of a schedule and returns a value to be maximized.
def sched_eval(Scheduler):
    return float(sum(Scheduler["Occupied"]))/len(Scheduler)

#Create a library of the functions and assign them weights.
functions = [add_object, remove_object, add_observation, remove_observation, replace_observation]
###2022: Redefine weights so that weights (and hence the weighted_randomizer(weights) function) are now applied to operations instead of objects.
weights = [1, 0.2, 1, 0.2, 1]

#Make an evaluation log to keep track of the schedule state.
eval_log = [float(sum(Scheduler["Occupied"]))/len(Scheduler)]
n = 0

#Run the ascent until the quality is met or the run limit is reached.
###2022: While the last evaluation log in the list is less than 0.85 (suboptimal), we initialize another schedule for the objects in the selected list. The current best schedule is stored in the evaluation log until a better schedule is generated, then the latter replaces the stored value. Continue to generate random schedules regardless of whether the subsequent schedule is better than the one before it or not, until the quality is met (0.85) or the run limit is reached. The chosen schedule is whatever "best" value is stored in the evaluation log at the time of stopping.
while eval_log[-1] < 0.85:
    Scheduler_init = copy.deepcopy(Scheduler)
    selected_init = copy.deepcopy(selected)
    eval_log = np.append(eval_log, sched_eval(Scheduler))
    
    ###2022: Apply 10 random functions in one trial to generate a new schedule.
    for i in range(10):
        random_func = weighted_randomizer(weights)
        functions[random_func]()
    eval_log = np.append(eval_log, sched_eval(Scheduler))
    if eval_log[-1] < eval_log[-2]:
        Scheduler = copy.deepcopy(Scheduler_init)
        selected = copy.deepcopy(selected_init)
    print(eval_log[-1])
    n += 1
    if n > 1500:
        break

#Here I save the Scheduler table as an ascii format text file.
#This allows the scheduling and observing scripts to be run separately if needed. 
for i in range(len(Scheduler)):
	Scheduler["DateTime"][i] = Scheduler["DateTime"][i].value
with open('Scheduler.txt', 'w', newline='') as outfile:
    ascii.write(Scheduler, outfile, overwrite=True, delimiter='|')
