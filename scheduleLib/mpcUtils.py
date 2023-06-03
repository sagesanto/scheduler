from datetime import datetime

# this isn't terribly elegant
def _findExposure(magnitude):
    # Internal: match magnitude to exposure description for TMO
    if magnitude < 19.5:
        return "1.0|300.0"
    if magnitude < 20.5:
        return "1.0|600.0"
    if magnitude < 21.0:
        return "2.0|600.0"
    if magnitude < 21.5:
        return "3.0|600.0"


def _formatEphem(ephems, desig):
    # Internal: take an object in the form returned from self.mpc.get_ephemeris() and convert each line to the scheduler format, before returning it in a dictionary of {startDt : line}
    ephemDict = {None: "DateTime|Occupied|Target|Move|RA|Dec|ExposureTime|#Exposure|Filter|Description"}
    for i in ephems:
        # the dateTime in the ephems list is a Time object, need to convert it to string
        i[0].format = "fits"
        i[0].out_subfmt = "date_hms"
        date = i[0].value
        i[0].format = "iso"
        i[0].out_subfmt = "date_hm"
        inBetween = i[0].value
        dateTime = datetime.strptime(inBetween, "%Y-%m-%d %H:%M")
        # name
        target = desig
        # convert the skycoords object to decimal
        coords = i[1].to_string("decimal").replace(" ", "|")

        vMag = i[2]
        # get the correct exposure string based on the vMag
        exposure = str(_findExposure(float(vMag)))

        # dRA and dDec come in arcsec/sec, we need /minute
        dRa = str(round(float(i[3]) * 60, 2))
        dDec = str(round(float(i[4]) * 60, 2))

        # for the description, we need RA and Dec in sexagesimal
        sexagesimal = i[1].to_string("hmsdms").split(" ")
        # the end of the scheduler line must have a description that looks like this
        description = "\'MPC Asteroid " + target + ", UT: " + datetime.strftime(dateTime, "%H%M") + " RA: " + \
                      sexagesimal[0] + " DEC: " + sexagesimal[1] + " dRA: " + dRa + " dDEC: " + dDec + "\'"

        lineList = [date, "1", target, "1", coords, exposure, "CLEAR", description]
        expLine = "|".join(lineList)
        ephemDict[datetime] = expLine

    return ephemDict


def pullEphem(mpcInst, desig, whenDt, altitudeLimit):
    """
    Fetch the ephemeris of a target from the MPC NEO confirmation database, given a valid designation. Requires internet connection.
    :param mpcInst: An instance of the MPCNeoConfirm class from the (privileged) photometrics.mpc_neo_confirm module
    :param desig: the temporary designation of the NEO candidate, as it appears on the MPC
    :param whenDt: A datetime object representing the time for which the ephemeris should be generated
    :param altitudeLimit: The lower altitude limit, below which ephemeris lines will not be generated
    :return: A Dictionary {startTimeDt: ephemLine}
    """
    return _formatEphem(mpcInst.get_ephemeris(desig, when=whenDt.strftime('%Y-%m-%dT%H:%M'),
                                              altitude_limit=altitudeLimit, get_uncertainty=None), desig)


def pullEphems(mpcInst, designations: list, whenDt: datetime, altitudeLimit):
    """
    Use pullEphem to pull ephemerides for multiple targets, given a list of their designations. Requires internet connection.
    :param mpcInst: An instance of the MPCNeoConfirm class from the (privileged) photometrics.mpc_neo_confirm module
    :param designations: A list of designations (strings) of the targets to retrieve
    :param whenDt: A datetime object representing the time for which the ephemeris should be generated
    :param altitudeLimit: The lower altitude limit, below which ephemeris lines will not be generated
    :return: a Dictionary of {designation: {startTimeDt: ephemLine}}
    """
    ephemsDict = {}
    for desig in designations:
        ephemsDict[desig] = pullEphem(mpcInst,desig, whenDt, altitudeLimit)
    return ephemsDict
