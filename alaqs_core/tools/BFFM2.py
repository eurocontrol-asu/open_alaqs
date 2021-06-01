import logging
import copy
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from numpy import empty_like, dot

logger = logging.getLogger("alaqs.%s" % __name__)


@dataclass(init=False, frozen=True)
class _Constants:
    """
    An immutable dataclass for constants

    """
    epsilon: float = 1e-4


constants = _Constants()


def perp(a):
    b = empty_like(a)
    b[0] = -a[1]
    b[1] = a[0]
    return b
    
def seg_intersect(a1,a2, b1,b2):
    np.seterr(divide='ignore', invalid='ignore')

    # logger.debug("seg_intersect")
    # logger.debug("\t a1: %s" % (str(a1)))
    # logger.debug("\t a2: %s" % (str(a2)))
    # logger.debug("\t b1: %s" % (str(b1)))
    # logger.debug("\t b2: %s" % (str(b2)))

    da = a2-a1
    db = b2-b1
    dp = a1-b1
    dap = perp(da)
    denom = dot( dap, db)
    num = dot( dap, dp )

    return (num / denom)*db + b1

def plotEmissionIndex(pollutant, icao_eedb) :
    import matplotlib
    matplotlib.use('Qt5Agg')
    import matplotlib.pyplot as plt

    x1 = np.log10(list(icao_eedb[pollutant]['Idle'].keys()))
    x2 = np.log10(list(icao_eedb[pollutant]['Approach'].keys()))
    x3 = np.log10(list(icao_eedb[pollutant]['Climbout'].keys()))
    x4 = np.log10(list(icao_eedb[pollutant]['Takeoff'].keys()))

    y1 = np.log10(list(icao_eedb[pollutant]['Idle'].values())) if not list(icao_eedb[pollutant]['Idle'].values())==[0.] else np.log10(np.array([1e-3]))
    y2 = np.log10(list(icao_eedb[pollutant]['Approach'].values())) if not list(icao_eedb[pollutant]['Approach'].values())==[0.] else np.log10(np.array([1e-3]))
    y3 = np.log10(list(icao_eedb[pollutant]['Climbout'].values())) if not list(icao_eedb[pollutant]['Climbout'].values())==[0.] else np.log10(np.array([1e-4]))
    y4 = np.log10(list(icao_eedb[pollutant]['Takeoff'].values())) if not list(icao_eedb[pollutant]['Takeoff'].values())==[0.] else np.log10(np.array([1e-4]))

    if y1==y2==y3==y4==0.:
        logger.error("All input values are zero. Reference points from database for pollutant '%s':" % (pollutant))
        logger.error(icao_eedb[pollutant])
        return 0.

    # Calculate the intersection between the two lines
    A = np.concatenate([x1,y1])
    B = np.concatenate([x2,y2])

    if pollutant.lower() == "nox" :
        C = np.concatenate([x3,y3])
        D = np.concatenate([x4,y4])
        IP = seg_intersect(A,B,C,D)
        # if np.isnan(IP):
        #     print A,B
        # print(A, B, C, D, IP)
        
    elif pollutant.lower() == "co" or pollutant.lower() == "hc":
        
        lin_av=np.log10(1/2.*(np.asarray(list(icao_eedb[pollutant]['Climbout'].values())) + np.asarray(list(icao_eedb[pollutant]['Takeoff'].values())))) # linear avg of y3,y4 

        C = np.concatenate([x3,lin_av])
        D = np.concatenate([x4,lin_av])
        IP = seg_intersect( A, B, C, D)
        # if np.isnan(IP):
        #     print A,B
        
        # Define Standard or non-standard behaviour
        data_behavior = 1 # Standard
        if IP[0] > min([x3,x4]) or IP[0] < max([x1,x2]):
            data_behavior = 2 # Non-Standard
            plottitle = 'Log Of Ref. EI'+ pollutant +' vs Log of Ref Fuel Flow (Non-Standard Case)'
        
    plottitle = 'Log Of Ref. EI '+ pollutant +' vs Log of Ref Fuel Flow (Standard Case)'
    
    # PLOT  - CO Standard Data Behavior   
    plt.ion()
    plt.figure()

    p12, = plt.plot(np.linspace(x1,x2,1000),np.linspace(y1,y2,1000),'.k',ms=3,mew=2)
    if pollutant.lower() == "co" or pollutant.lower() == "hc":
        if  data_behavior == 1:
            p23, = plt.plot(np.linspace(x2,x3,1000),np.linspace(y2,y3,1000),'.k',ms=3,mew=2)
            p34, = plt.plot(np.linspace(x3,x4,1000),np.linspace(y3,y4,1000),'.k',ms=3,mew=2)
        
            #plt.annotate('EI to be calculated from this line',style='italic',color='green',
            #   xy=((x2+x3)/2, (y2+y3)/2), xytext=((x2+x3)/2, y2/2), arrowprops=dict(facecolor='green', shrink=0.1));
           
        elif data_behavior == 2:     
               p23, = plt.plot(np.linspace(x2,x3,1000),np.linspace(y2,lin_av,1000),'.k',ms=3,mew=2)
               p34, = plt.plot(np.linspace(x3,x4,1000),np.linspace(lin_av,lin_av,1000),'.k',ms=3,mew=2)
        
               #plt.annotate('EI to be calculated from this line',style='italic',color='green',
               #xy=((x2+x3)/2, (y2+lin_av)/2), xytext=((x2+x3)/2, lin_av/2), arrowprops=dict(facecolor='green', shrink=0.1));
    
    elif pollutant.lower() == "nox":
        p23, = plt.plot(np.linspace(x2,x3,1000),np.linspace(y2,y3,1000),'.k',ms=3,mew=2)
        p34, = plt.plot(np.linspace(x3,x4,1000),np.linspace(y3,y4,1000),'.k',ms=3,mew=2)           
                      
    ## plot continued ..     
    p1, = plt.plot(x1,y1, "ro", ms=8, mfc="r", mew=2, mec="r") # red filled circle
    plt.plot(x1,y1, "w+", ms=8, mec="w", mew=2) # white cross
    
    p2, = plt.plot(x2,y2, "ro", ms=8, mfc="r", mew=2, mec="r") # red filled circle
    plt.plot(x2,y2, "w+", ms=8, mec="w", mew=2) # white cross
    
    p3, = plt.plot(x3,y3, "ro", ms=8, mfc="r", mew=2, mec="r") # red filled circle
    plt.plot(x3,y3, "w+", ms=8, mec="w", mew=2) # white cross
    
    p4, = plt.plot(x4,y4, "ro", ms=8, mfc="r", mew=2, mec="r") # red filled circle
    plt.plot(x4,y4, "w+", ms=8, mec="w", mew=2) # white cross
       
    # text
    plt.text(x1,y1,'  7% ', color='b')
    plt.text(x2,y2,'  30% ', color='b')
    plt.text(x3,y3,'  85% ', color='b')
    plt.text(x4,y4,'  100% ', color='b')
 
    plt.plot(IP[0],IP[1], "go", ms=9, mfc="g", mew=2, mec="g") # red filled circle
    plt.plot(IP[0],IP[1], "wx", ms=8, mec="w", mew=2) # white cross
    plt.text(IP[0],IP[1],'  Intersection ', color='b')
    
    plt.axis([min(-1.5,min(x1,x2,x3,x4)), max(1.5,max(x1,x2,x3,x4)), min(-1.5,min(y1,y2,y3,y4)), max(2,max(y1,y2,y3,y4))])
        
    plt.xlabel('Log of Ref. FF')
    plt.ylabel('Log of Ref. '+ pollutant +' EI')
    plt.title(plottitle)
    ax = plt.gca()
    ax.grid(True)
    plt.savefig(pollutant+'_interp_curve.pdf', dpi=300, format='PDF', bbox_inches='tight')
    plt.show()    
    # plt.close("all")

# def calculateEmissionIndex(pollutant, fuel_flow, icao_eedb, ambient_conditions=None, installation_corrections = None):
def calculateEmissionIndex(pollutant, fuel_flow, icao_eedb, ambient_conditions={}, installation_corrections = {}):
    """
    Calculates the emission index associated to a particular fuel flow with the BFFM2 method
    :param pollutant: str either "NOx", "CO", or "HC"
    :param fuel_flow: float in units kg/s
    :param icao_eedb: dict with fuel_flow:emission index values from ICAO Emissions
    :param ambient conditions: dict with parameters to correct for ambient conditions, default is ISA
    :param installation_corrections: dict (mode: factor) with adjustment factors for installation effects
    :return float: calculated fuel flow in kg/s

    An issue concerns the modeling of zero values from the certification data, especially concerning EITHC values.
    Since zero values cannot be converted to Logs, a substitution to a small value is recommended.
    For the 85% and 100% power points or if all power point EIs are zero, any value < 10-4 should suffice.
    If the 7% power point is non-zero and the 30% power point is zero, then values < 10-3 may result in excessive
    extrapolation below the 7% power setting.
    These solutions are reasonable since the zero values in the ICAO data likely represents small values that were
    rounded to zero as opposed to actually implying zero emissions.
    """
    
    # Adjustment factors for installation effects (in not explicitly specified) :
    # Mode       Power Setting (%)    Adjustment Factor
    # Takeoff        100                 1.010
    # Climbout       85                  1.013
    # Approach       30                  1.020
    # Idle           7                   1.100
    icao_eedb = copy.deepcopy(icao_eedb)

    # installation_corrections_ = {
    #     "Takeoff":1.0,    # 100%
    #     "Climbout":1.0,   # 85%
    #     "Approach":1.0,   # 30%
    #     "Idle":1.0        # 7%
    # }

    installation_corrections_ = {
        "Takeoff":1.010,    # 100%
        "Climbout":1.012,   # 85%
        "Approach":1.020,   # 30%
        "Idle":1.100        # 7%
    }
    installation_corrections_.update(installation_corrections)
    installation_corrections = installation_corrections_

    ambient_conditions_ = {
        "temperature_in_Kelvin":288.15, #ISA conditions
        "pressure_in_Pa":1013.25*100., #ISA conditions
        "relative_humidity":0.6, #normal day at ISA conditions
        "mach_number":0.0 #ground or laboratory
        # "humidity_ratio_in_kg_water_per_kg_dry_air":0.00634 #ISA default
    }

    ambient_conditions_.update(ambient_conditions)
    ambient_conditions = ambient_conditions_


    #some sanity checks
    fuel_flow=max(0., fuel_flow)

    for key_ in list(installation_corrections.keys()):
        for p_ in icao_eedb:
            if not key_ in icao_eedb[p_]:
                logger.error("Did not find mandatory key '%s' in ICAO EEDB." % (key_))

    for p_ in icao_eedb:
        if not len(list(icao_eedb[p_].keys())) == 4:
            logger.error("Found not exactly four points in values provided for ICAO EEDB. Keys should be '%s', but are '%s'." %( ", ".join(list(installation_corrections.keys())), ", ".join(list(icao_eedb[pollutant].keys()))))

    # 1. Multiply FF ref values with the above (default) adjustment factors if not any other factors are passed into the function
    for ikey in icao_eedb[pollutant].keys():
        for ik, ival in list(icao_eedb[pollutant][ikey].items()):
            icao_eedb[pollutant][ikey][ik*installation_corrections[ikey]] = icao_eedb[pollutant][ikey].pop(ik)

    # logger.debug("After installation corrections")
    # for mode in icao_eedb[pollutant]:
        # logger.debug("\t Mode '%s':"% (mode))
        # for item in icao_eedb[pollutant][mode].items():
            # logger.debug("\t\t Fuel flow=%f, EI=%f" % (item[0], item[1]))

    # logger.debug('Ambient conditions:')
    T_a = ambient_conditions['temperature_in_Kelvin'] # T_a = Ambient temperature (K)
    T_ac = T_a - 273.15 # T_ac = Ambient temperature (oC)
    # logger.debug('\t T_ac: ' + "%.3f C" % T_ac)

    P_a = ambient_conditions['pressure_in_Pa']    # P_a = Ambient pressure (kPa)
    P_psia = P_a * 0.14504 * 1e-3  # 1 kPa = 0.14504 psia    # P_psia = Ambient pressure (psia)
    # logger.debug('\t P_psia: ' + "%.3f" % P_psia)

    # RH = Relative humidity
    RH = ambient_conditions['relative_humidity']
    # M = Mach number
    M = ambient_conditions['mach_number']

    omega = None
    if "humidity_ratio_in_kg_water_per_kg_dry_air" in ambient_conditions:
        omega = ambient_conditions['humidity_ratio_in_kg_water_per_kg_dry_air']

    # P_sat = Saturation vapor pressure (mbar)
    P_sat = 6.107 * 10 ** ( (7.5 * T_ac) / (237.3 + T_ac) ) # T_ac in Celsius (C = K-273.15) !!
    # logger.debug('\t P_sat: ' + "%.3f" % P_sat)

    #theta = Temperature ratio (ambient to sea level)
    theta = T_a / 288.15
    # logger.debug('\t theta: ' + "%.3f" % theta)

    # delta = Pressure ratio (ambient to sea level)
    delta = P_a/float(101325)
    if delta < 0.001:
        logger.debug('\t delta (Pressure ratio) is unnatural: %.3f. Pressure should be in Pa' %delta)

    # omega = Humidity ratio (kg H2O/kg of dry air)
    if omega is None:
        # omega = (0.62197058 * RH * P_sat) / ( (P_psia * 100) - 0.37802*(RH*P_sat) )
        omega = (0.62197058 * RH * P_sat) / ( P_psia * 68.9473 - RH * P_sat )
    # logger.debug('\t omega: ' + "%.5f" % omega)

    # H = Humidity coefficient
    H = -19.0*(omega - 0.00634)
    # logger.debug('\t H: ' + "%.3f" % H)

    x = 1.0 # P3T3 exponent (default value is 1.0)
    y = 0.5 # P3T3 exponent (default value is 0.5)

    # FF_ref = Fuel flow at reference conditions (kg/s)
    # fuel_flow = Fuel flow at non-reference conditions (kg/s)
    FF_ref = (fuel_flow/delta) * (theta**3.8) * np.exp(0.2 * M**2)
    # logger.debug('Reference Fuel Flow: ' + "%.3f" % FF_ref)

    ####################################################################################################
    # 2. Develop Log-Log relationship between EI_ref and adjusted FF_ref values
    ####################################################################################################

    # Modeling of zero values from the certification data (especially concerning EITHC values) :
    # Since zero values cannot be converted to Logs, a substitution to a small value is recommended.

    # for ikey in icao_eedb[pollutant].keys():

    # if ikey == 'Idle':
    idle_check = 1
    for ik, ival in list(icao_eedb[pollutant]['Idle'].items()):
        if icao_eedb[pollutant]['Idle'][ik] == 0:
            idle_check = 0
            # logger.debug("7%% EI is zero, setting to %f" % (constants.epsilon))
            icao_eedb[pollutant]['Idle'][ik] = constants.epsilon * 10

    # elif ikey == 'Approach':
    for ik, ival in list(icao_eedb[pollutant]['Approach'].items()):
        if icao_eedb[pollutant]['Approach'][ik] == 0 and idle_check > 0:
            # logger.debug("30%% EI is zero, but 7%% EI is not zero, setting 30%% EI to %f" % (constants.epsilon))
            icao_eedb[pollutant]['Approach'][ik] = constants.epsilon*10
        elif icao_eedb[pollutant]['Approach'][ik] == 0 and idle_check == 0:
            # logger.debug("30%% EI is zero, but 7%% EI was zero, setting 30%% EI to %f" % (constants.epsilon))
            icao_eedb[pollutant]['Approach'][ik] = constants.epsilon

    # For the 85 and 100 power points or if all power point EIs are zero, any value <= 10-4 should suffice.
    # elif ikey == 'Climbout':
        for ik, ival in list(icao_eedb[pollutant]['Climbout'].items()):
            if icao_eedb[pollutant]['Climbout'][ik] == 0:
                icao_eedb[pollutant]['Climbout'][ik] = constants.epsilon
    # elif ikey == 'Takeoff':
        for ik, ival in list(icao_eedb[pollutant]['Takeoff'].items()):
            if icao_eedb[pollutant]['Takeoff'][ik] == 0:
                icao_eedb[pollutant]['Takeoff'][ik] = constants.epsilon

    # These solutions are reasonable since the zero values in the ICAO data likely represents small
    # values that were rounded to zero as opposed to actually implying zero emissions.
    x1 = np.log10(list(icao_eedb[pollutant]['Idle'].keys()))
    x2 = np.log10(list(icao_eedb[pollutant]['Approach'].keys()))
    x3 = np.log10(list(icao_eedb[pollutant]['Climbout'].keys()))
    x4 = np.log10(list(icao_eedb[pollutant]['Takeoff'].keys()))

    y1 = np.log10(list(icao_eedb[pollutant]['Idle'].values())) if not list(icao_eedb[pollutant]['Idle'].values())==[0.] else 0.
    y2 = np.log10(list(icao_eedb[pollutant]['Approach'].values())) if not list(icao_eedb[pollutant]['Approach'].values())==[0.] else 0.
    y3 = np.log10(list(icao_eedb[pollutant]['Climbout'].values())) if not list(icao_eedb[pollutant]['Climbout'].values())==[0.] else 0.
    y4 = np.log10(list(icao_eedb[pollutant]['Takeoff'].values())) if not list(icao_eedb[pollutant]['Takeoff'].values())==[0.] else 0.

    if y1==y2==y3==y4==0.:
        logger.error("All input values are zero. Reference points from database for pollutant '%s':" % (pollutant))
        logger.error(icao_eedb[pollutant])
        return 0.

    x_ff_log = np.log10(FF_ref if FF_ref else constants.epsilon)

    # logger.debug('Log Fuel Flow: ' + "%.2f" % x_ff_log)

    # First (7-30%) line equation (y=ax+b)
    coef_a1 = ( y2 - y1 )/( x2 - x1 )
    coef_b1 = y2 - coef_a1*x2

    # STANDARD DATA BEHAVIOR

    y_ff_log = None
    # NOx case: Points in-between each pair of adjacent certification points are determined through linear interpolations on the Log-Log scales
    if pollutant.lower() == "nox":
        # logger.debug(" NOx case: STANDARD DATA BEHAVIOR ")
        #if np.log10(1e-4) <= x_ff_log <= x1:
           # logger.debug("Attention: FF below 7% - Erroneously high emissions could be generated for some engines ")
        #    y_ff_log = np.interp(x_ff_log,np.asarray([np.log10(1e-4),x1]), np.asarray([np.log10(1e-4),y1]))
        if x_ff_log < x1:
            # logger.debug( "Attention: FF below 7%% - Erroneously high emissions could be generated for some engines ")
            y_ff_log = coef_a1*x_ff_log+coef_b1

        elif x1 <= x_ff_log <= x2:
            # logger.debug("FF between 7% and 30% ")
            y_ff_log = np.interp(x_ff_log,np.concatenate([x1,x2]),np.concatenate([y1,y2]))

        elif x2 < x_ff_log <= x3:
            # logger.debug("FF between 30% and 85% ")
            y_ff_log = np.interp(x_ff_log,np.concatenate([x2,x3]),np.concatenate([y2,y3]))

        elif x3 < x_ff_log <= x4:
            # logger.debug("FF between 85% and 100% ")
            y_ff_log = np.interp(x_ff_log,np.concatenate([x3,x4]),np.concatenate([y3,y4]))

        elif x_ff_log > x4:
           # logger.debug("Attention: FF over 100% ")
           # First (>100%) line equation (y=ax+b)
           coef_a100 = ( y4 - y3 )/( x4 - x3 )
           coef_b100 = y4 - coef_a100*x4
           y_ff_log = coef_a100*x_ff_log+coef_b100

    elif pollutant.lower() == "co" or pollutant.lower() == "hc":

        lin_av=np.log10(1/2.*(np.asarray(list(icao_eedb[pollutant]['Climbout'].values())) + np.asarray(list(icao_eedb[pollutant]['Takeoff'].values())))) # linear avg of y3,y4
        lin_av=np.log10(1/2.*(np.asarray(list(icao_eedb[pollutant]['Climbout'].values())) + np.asarray(list(icao_eedb[pollutant]['Takeoff'].values())))) # linear avg of y3,y4

        # Calculate the intersection between the two lines
        A = np.concatenate([x1,y1])
        B = np.concatenate([x2,y2])
        C = np.concatenate([x3,lin_av])
        D = np.concatenate([x4,lin_av])

        IP = seg_intersect( A,B, C,D)

        # Define Standard or non-standard behaviour
        data_behavior = 1 # Standard
        if IP[0] > min([x3, x4]) or IP[0] < max([x1, x2]) :
            data_behavior = 2 # Non-Standard

        if x_ff_log < x1:
            # logger.debug("FF_ref below 7% !")
            coef_a = ( y2-y1 )/( x2-x1 )
            coef_b = y2 - coef_a*x2
            y_ff_log = coef_a*x_ff_log+coef_b

        elif x1 <= x_ff_log <= x2:
            # logger.debug('FF_ref between 7 and 30%')
            y_ff_log = np.interp(x_ff_log,np.concatenate([x1,x2]),np.concatenate([y1,y2]))

        elif x2 <= x_ff_log <= x3:
            if data_behavior == 1:
                # logger.debug("STANDARD DATA BEHAVIOR")
                if x2 < x_ff_log <= IP[0]:
                    # logger.debug('FF_ref between 30% and Intersection Point FF')
                    coef_a = ( IP[1]-y2 )/( IP[0]-x2 )
                    coef_b = y2 - coef_a*x2
                    y_ff_log = coef_a*x_ff_log+coef_b
                elif IP[0] < x_ff_log <= x3:
                    # logger.debug('FF_ref between Intersection Point and 85%')
                    coef_a = ( IP[1]-y3 )/( IP[0]-x3 )
                    coef_b = y3 - coef_a*x3
                    y_ff_log = coef_a*x_ff_log+coef_b

            elif data_behavior == 2:
                # logger.debug("NON-STANDARD DATA BEHAVIOR")
                # logger.debug('FF_ref between 30% and 85 FF')
                y_ff_log = np.interp(x_ff_log,np.concatenate([x2,x3]),np.concatenate([y2,lin_av]))

        elif x3 < x_ff_log <= x4:
            # logger.debug('FF_ref between 85% and 100% FF')
            y_ff_log = np.interp(x_ff_log,np.concatenate([x3,x4]),np.concatenate([y3,y4]))

        elif x_ff_log > x4:
            # logger.debug("FF_ref over 100% !")
            coef_a = ( IP[1]-lin_av )/( IP[0]-x4 )
            coef_b = IP[1] - coef_a*IP[0]
            y_ff_log = coef_a*x_ff_log+coef_b
    else:
        logger.error("Pollutant '%s' unknown." % (str(pollutant)))

    # if not y_ff_log is None:
        # logger.debug('Pollutant %s:' % (str(pollutant)))
        # logger.debug('\t Corresponding Log EI: ' + "%.2f" % y_ff_log)
        # logger.debug('\t EI corresponding to this reference Fuel Flow: ' + "%.4f" % 10**(y_ff_log))

    if y_ff_log is None or np.isnan(y_ff_log):
        y_ff_log = np.log10(constants.epsilon)
        # print "\t log(EI<>_ref): %s"%y_ff_log

    #####################################################################################################################
    #   3. Calculate EI
    #####################################################################################################################

    if pollutant.lower() == "nox":
    # EI = NOx EI at non-reference conditions (g/kg)
    # EINOx_ref = NOx EI at reference conditions (g/kg)
        EINOx_ref = 10**(y_ff_log) if 10**(y_ff_log)>constants.epsilon else 0.
        EI = EINOx_ref * np.exp(H) * ( delta**1.02 / theta**3.3 )**y
        # print "EINOx_ref %s"%EINOx_ref
    elif pollutant.lower() == "co":
        # EI = CO EI at non-reference conditions (g/kg)
        EICO_ref = 10**(y_ff_log) if 10**(y_ff_log)>constants.epsilon else 0. # CO EI at reference conditions (g/kg)
        EI = EICO_ref * (theta**3.3/delta**1.02)**x
        # print "EICO_ref %s"%EICO_ref

    elif pollutant.lower()=="hc":
        # EI = THC EI at non-reference conditions (g/kg)
        EITHC_ref = 10**(y_ff_log) if 10**(y_ff_log)>constants.epsilon else 0. # HC EI at reference conditions (g/kg)
        EI = float(EITHC_ref) * (theta**3.3/delta**1.02)**x

    emission_index = EI[0] if (type(EI) is np.ndarray and EI.size == 1) else EI # in kg/s

    # if type(emission_index) == np.ndarray and emission_index.size == 1:
    #     emission_index = emission_index[0]

    return emission_index


def plotEmissionIndexNominal(pollutant, icao_eedb, ambient_conditions={}, installation_corrections={}, range_relative_fuelflow=(0.50, 1.5), steps=101, suffix="", multipage={}, title=""):
    import matplotlib
    matplotlib.use('Qt5Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    import numpy as np
    """
    Plots the emission index associated to a particular pollutant with the BFFM2 method
    :param pollutant: str either "NOx", "CO", or "HC"
    :param icao_eedb: dict with fuel_flow:emission index values from ICAO Emissions
    :param ambient conditions: dict with ambient conditions
    :param installation_corrections: dict (mode: factor) with adjustment factors for installation effects
    :param range_relative_fuelflow: tuple with plot range for x-axis.
    First entry is factor multiplied with minimal fuel flow (obtained from icao_eedb), second index refers to maximal fuel flow.
    Example:range_relative_fuelflow=(0.50, 1.5) means that plot range is [0.5*min(fuel flow) + 1.5*max(fuel flow)
    """

    reference_points = []
    for id in list(icao_eedb[pollutant].keys()):
        for (ff_,ei_) in list(icao_eedb[pollutant][id].items()):
            reference_points.append((ff_,ei_))
    min_ff = min([ff for ff,ei in reference_points])* float(range_relative_fuelflow[0])
    max_ff = max([ff for ff,ei in reference_points])* float(range_relative_fuelflow[1])

    #fuel flow
    val_ff = np.linspace(min_ff, max_ff, steps)
    val_ei = []
    #calculate emission index
    for ff in val_ff:
        val_ei.append(calculateEmissionIndex(pollutant, ff, icao_eedb, ambient_conditions, installation_corrections))

    #Plotting
    plt.ion()
    plt.figure()

    plot, = plt.plot(val_ff, val_ei,'.k',ms=3,mew=2, label="BFFM2 corrected for ambient conditions and installation effects")
    plot_ref, = plt.plot([item[0] for item in reference_points],[item[1] for item in reference_points], 'bo', label="Reference values at ISA conditions")
    plt.xlabel("Fuel flow [kg/s]")
    plt.ylabel("Emission index of '%s' [g/kg]" % (pollutant))
    if title:
        plt.title(title)
    ax = plt.gca()
    ax.grid(True)
    # ax.legend(bbox_to_anchor=(0., 1.02, 1., .102),
    #           loc=3,
    #           mode="expand",
    #           fontsize=10,
    #           borderaxespad=0.,
    #           numpoints=1
    # )
    ax.legend(bbox_to_anchor=(0.5, -0.12),
              loc='upper center',
     #         mode="expand",
              fontsize=10,
              borderaxespad=0.,
              numpoints=1
    )

    plt.show()

    if multipage and pollutant in multipage and isinstance(multipage[pollutant], PdfPages):
        multipage[pollutant].savefig(dpi=300, bbox_inches='tight')
    else:
        plt.savefig("%s_%s_%s.pdf" % (pollutant, 'emission_index', str(suffix)), dpi=300, format='PDF', bbox_inches='tight')

    # plt.close("all")

if __name__ == "__main__":
    # create a logger for this module
    # logger.setLevel(logging.DEBUG)
    # # create console handler and set level to debug
    # ch = logging.StreamHandler()
    # ch.setLevel(logging.DEBUG)
    # # create formatter
    # formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
    # # add formatter to ch
    # ch.setFormatter(formatter)
    # # add ch to logger
    # logger.addHandler(ch)

    # Input conditions for this example are:
    pollutant = "NOx"

    # # Example: These values correspond to a cruise point or segment of a flight trajectory using the Trent 892 engine with an ICAO UID of 2RR027
    # # For each pollutant, the reference FF (non-adjusted) and EI are given

    # Engine	1CM008 (CFM56-5-A1)
    # Engine fuel flow rate (in kg/s at reference conditions)
    # fuel_flow = 0.882 # Engine fuel flow rate = 0.882 # in kg/s (or 7000 lb/hr/engine)
    fuel_flow = 0.319894549
    ff_to = 1.051
    ff_co = 0.862
    ff_app = 0.291
    ff_idle = 0.1011

    icao_values = {
        'CO': OrderedDict({'Idle': {ff_idle: 17.6}, 'Approach': {ff_app: 2.5}, 'Climbout': {ff_co: 0.9}, 'Takeoff': {ff_to: 0.9}}),
        'NOx': OrderedDict({'Idle': {ff_idle: 4.0}, 'Approach': {ff_app: 8.0}, 'Climbout': {ff_co: 19.6}, 'Takeoff': {ff_to: 24.6}}),
        'HC': OrderedDict({'Idle': {ff_idle: 1.4}, 'Approach': {ff_app: 0.4}, 'Climbout': {ff_co: 0.23}, 'Takeoff': {ff_to: 0.23}})
    }

    # Altitude = 39000 # in ft
    # Standard day (ISA conditions)
    ambient_conditions = {
    "temperature_in_Kelvin":288.15, #ISA conditions
    "pressure_in_Pa":1013.25*100., #ISA conditions
    "relative_humidity":0.6, #normal day at ISA conditions
    "mach_number":0.779999728 #ground or laboratory
    # "humidity_ratio_in_kg_water_per_kg_dry_air":0.00634 #ISA default
    }

    # ambient_conditions = {
    #         "temperature_in_Kelvin":216.65,
    #         "pressure_in_Pa":19677,
    #         "mach_number":0.84,
    #         "relative_humidity":0.60,
    #         #either relative humidity or absolute humidity ratio has to be defined
    #         # "humidity_ratio_in_kg_water_per_kg_dry_air":0.000053
    #     }

    # ambient_conditions = {}

    installation_corrections = {
            "Takeoff":1.010,    # 100%
            "Climbout":1.013,   # 85%
            "Approach":1.020,   # 30%
            "Idle":1.100        # 7%
        }

    #Don't correct for installation
    # installation_corrections = {}

    #logger.info("Calculated emission index '%s' for fuel flow '%.2f' is '%.2f'" % (pollutant, fuel_flow, calculateEmissionIndex(pollutant, fuel_flow, icao_values, ambient_conditions=ambient_conditions, installation_corrections=installation_corrections)))

    # fix_print_with_import
    print(calculateEmissionIndex(pollutant, fuel_flow, icao_values, ambient_conditions=ambient_conditions, installation_corrections=installation_corrections))

    plotEmissionIndex(pollutant, icao_values)
    plotEmissionIndexNominal(pollutant, icao_values, ambient_conditions=ambient_conditions, installation_corrections=installation_corrections, range_relative_fuelflow=[1.00, 1.0], steps=51, suffix="")