import math
import sys

# FIXME remove call to alaqs (implement class for study setup), fix also direct sql calls
from open_alaqs.alaqs_core import alaqs
from open_alaqs.alaqs_core import alaqsdblite
from open_alaqs.alaqs_core import alaqsutils
from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


def roadway_emission_factors_alaqs_method(input_data):
    """
    This function creates a set of averaged emission factors for a roadway (or parking) based on:
    - The roadway fleet year (set using the study setup UI)
    - The roadway country (set using the study setup UI)
    - The roadway geometry
    At present, only the ALAQS roadway method is supported.

    The function works by creating a dict that is fed repeatedly through different roadway vehicle types (passenger
    vehicles, light goods vehicles, heavy goods vehicles) and for different vehicle scenarios (pre-euro, EURO I,
    EURO II, ...). Each time the dict is passed through one of these functions, the emissions totals and vehicle totals
    are incremented based on the defined formulae for that vehicle class/scenario. At the end o the function, all
    emissions are averaged to provide an overall representative EF for the specific road.

    :param input_data: This is a dict of parameters that outline a description of the roadway. This should contain
        airport_temperature         In degrees C, comes from study setup UI
        roadway_method              Currently must be ALAQS
        roadway_fleet_year          A valid year for COPERT Fleet data
        roadway_country             A valid country for COPERT Fleet data
        parking_method              Currently must be ALAQS
    :return emission_factors:
    :rtype: dict
    """

    try:
        # Unpack input
        #road_number_per_year = roadway_data['number_per_year']
        road_speed = input_data['speed']

        # Get the study data for additional information needed
        study_data = alaqs.load_study_setup_dict()
        airport_temperature = study_data['airport_temperature']
        airport_roadway_method = study_data['roadway_method']
        airport_roadway_year = study_data['roadway_fleet_year']
        airport_roadway_country = study_data['roadway_country']
        airport_parking_method = study_data['parking_method']

        # Create a dict that is the input for the various ef aggregation functions
        aggregation_input = dict()
        aggregation_input['roadway_country'] = airport_roadway_country
        aggregation_input['roadway_method'] = airport_roadway_method
        aggregation_input['roadway_year'] = airport_roadway_year
        aggregation_input['parking_method'] = airport_parking_method
        aggregation_input['temperature_average'] = airport_temperature
        aggregation_input['velocity'] = road_speed

        # Add some fields that are used to keep running totals during calculation
        aggregation_input['total_em_voc_pc'] = 0
        aggregation_input['total_em_voc_ldv'] = 0
        aggregation_input['total_em_voc_hdv'] = 0
        aggregation_input['total_em_co_pc'] = 0
        aggregation_input['total_em_co_ldv'] = 0
        aggregation_input['total_em_co_hdv'] = 0
        aggregation_input['total_em_nox_pc'] = 0
        aggregation_input['total_em_nox_ldv'] = 0
        aggregation_input['total_em_nox_hdv'] = 0
        aggregation_input['total_em_pm_pc'] = 0
        aggregation_input['total_em_pm_ldv'] = 0
        aggregation_input['total_em_pm_hdv'] = 0
        aggregation_input['weighted_sum_pc'] = 0
        aggregation_input['weighted_sum_ldv'] = 0
        aggregation_input['weighted_sum_hdv'] = 0

        # Get the average trip length
        aggregation_input['average_trip_length'] = get_average_trip_length(airport_roadway_country)

        # Equivalent of modAggrPcEuroIEf.PCAggregatedPreEURO_EF
        aggregation_input['vehicle_type'] = "PC"

        ## Emission_Class = 'Pre-ECE'
        aggregation_input['vehicle_fuel'] = "Gasoline"

        aggregation_input['vehicle_class'] = "Pre-ECE"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)

        # Emission_Class = 'ECE 15/00-01'
        aggregation_input['vehicle_class'] = "ECE 15/00-01"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)

        # Emission_Class = 'ECE 15-02'
        aggregation_input['vehicle_class'] = "ECE 15/02"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)

        # Emission_Class = 'ECE 15-03'
        aggregation_input['vehicle_class'] = "ECE 15/03"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)

        # Emission_Class = 'ECE 15-04'
        aggregation_input['vehicle_class'] = "ECE 15/04"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)

        # Emission_Class = 'Improved Conv'
        aggregation_input['vehicle_class'] = "Improved Conv"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)

        # Emission_Class = 'Open Loop'
        aggregation_input['vehicle_class'] = "Open Loop"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)

        # Emission_Class = 'Uncontrolled'
        aggregation_input['vehicle_fuel'] = "Diesel"

        aggregation_input['vehicle_class'] = "Uncontrolled"
        aggregation_input['vehicle_size'] = "<2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_pre_euro_ef(aggregation_input)

        # Equivalent of modAggrPcEf.PCAggregatedEURO_EF
        aggregation_input['vehicle_fuel'] = "Gasoline"
        aggregation_input['vehicle_class'] = "EURO I"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)

        aggregation_input['vehicle_class'] = "EURO II"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)

        aggregation_input['vehicle_class'] = "EURO III"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)

        aggregation_input['vehicle_class'] = "EURO IV"
        aggregation_input['vehicle_size'] = "<1.4 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = "1.4 - 2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)

        aggregation_input['vehicle_fuel'] = "Diesel"

        aggregation_input['vehicle_class'] = "EURO I"
        aggregation_input['vehicle_size'] = "<2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)

        aggregation_input['vehicle_class'] = "EURO II"
        aggregation_input['vehicle_size'] = "<2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)

        aggregation_input['vehicle_class'] = "EURO III"
        aggregation_input['vehicle_size'] = "<2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)

        aggregation_input['vehicle_class'] = "EURO IV"
        aggregation_input['vehicle_size'] = "<2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)
        aggregation_input['vehicle_size'] = ">2.0 l"
        aggregation_input = aggregated_euro_ef(aggregation_input)

        # TODO The code for LPG in original ALAQS is wrong and will need redoing
        #aggregation_input['vehicle_fuel'] = "LPG"
        #aggregation_input['vehicle_size'] = "All"
        #aggregation_input['vehicle_class'] = "Uncontrolled"
        #aggregation_input = aggregated_euro_ef(aggregation_input)
        #aggregation_input['vehicle_class'] = "EURO I"
        #aggregation_input = aggregated_euro_ef(aggregation_input)
        #aggregation_input['vehicle_class'] = "EURO II"
        #aggregation_input = aggregated_euro_ef(aggregation_input)

        # Equivalent of modAggrPcMotEf.PCAggregatedMOT_EF
        if input_data['parking'] is False:
            aggregation_input['vehicle_type'] = "MOT"
            aggregation_input['vehicle_fuel'] = "Gasoline"
            aggregation_input['vehicle_class'] = "Uncontrolled"
            aggregation_input['vehicle_size'] = "<50 cc"
            aggregation_input['vehicle_mot'] = "Mopeds"
            aggregation_input = aggregated_mot_ef(aggregation_input)
            aggregation_input['vehicle_class'] = "Stage I"
            aggregation_input = aggregated_mot_ef(aggregation_input)
            aggregation_input['vehicle_class'] = "Stage II"
            aggregation_input = aggregated_mot_ef(aggregation_input)
            aggregation_input['vehicle_class'] = "Uncontrolled"
            aggregation_input['vehicle_size'] = ">50 cc 2-s"
            aggregation_input = aggregated_mot_ef(aggregation_input)
            aggregation_input['vehicle_class'] = "Controlled"
            aggregation_input = aggregated_mot_ef(aggregation_input)
            # TODO include rest of the bikes...

        # Equivalent of modAggrPcLdvEf.PCAggregatedLDV_EF
        aggregation_input['vehicle_type'] = "LDV"

        aggregation_input['vehicle_fuel'] = "Gasoline"

        aggregation_input['vehicle_size'] = "All"

        aggregation_input['vehicle_class'] = "Uncontrolled"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_class'] = "EURO I"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_class'] = "EURO II"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_class'] = "EURO III"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_class'] = "EURO IV"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_fuel'] = "Diesel"
        aggregation_input['vehicle_class'] = "Uncontrolled"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_class'] = "EURO I"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_class'] = "EURO II"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_class'] = "EURO III"
        aggregation_input = aggregated_ldv_ef(aggregation_input)
        aggregation_input['vehicle_class'] = "EURO IV"
        aggregation_input = aggregated_ldv_ef(aggregation_input)

        # Calculate the emission factors for each vehicle category
        avg_ef_nox_pc = calculate_avg_ef(aggregation_input['total_em_nox_pc'], aggregation_input['weighted_sum_pc'])
        avg_ef_nox_ldv = calculate_avg_ef(aggregation_input['total_em_nox_ldv'], aggregation_input['weighted_sum_ldv'])
        avg_ef_nox_hdv = calculate_avg_ef(aggregation_input['total_em_nox_hdv'], aggregation_input['weighted_sum_hdv'])

        avg_ef_hc_pc = calculate_avg_ef(aggregation_input['total_em_voc_pc'], aggregation_input['weighted_sum_pc'])
        avg_ef_hc_ldv = calculate_avg_ef(aggregation_input['total_em_voc_ldv'], aggregation_input['weighted_sum_ldv'])
        avg_ef_hc_hdv = calculate_avg_ef(aggregation_input['total_em_co_hdv'], aggregation_input['weighted_sum_hdv'])

        avg_ef_co_pc = calculate_avg_ef(aggregation_input['total_em_co_pc'], aggregation_input['weighted_sum_pc'])
        avg_ef_co_ldv = calculate_avg_ef(aggregation_input['total_em_co_ldv'], aggregation_input['weighted_sum_ldv'])
        avg_ef_co_hdv = calculate_avg_ef(aggregation_input['total_em_co_hdv'], aggregation_input['weighted_sum_hdv'])

        avg_ef_pm_pc = calculate_avg_ef(aggregation_input['total_em_pm_pc'], aggregation_input['weighted_sum_pc'])
        avg_ef_pm_ldv = calculate_avg_ef(aggregation_input['total_em_pm_ldv'], aggregation_input['weighted_sum_ldv'])
        avg_ef_pm_hdv = calculate_avg_ef(aggregation_input['total_em_pm_hdv'], aggregation_input['weighted_sum_hdv'])

        # Calculate the overall averaged emission factors based on % in each category
        avg_ef_nox = avg_ef_nox_pc * input_data['vehicle_light'] / 100 + \
                     avg_ef_nox_ldv * input_data['vehicle_medium'] / 100 + \
                     avg_ef_nox_hdv * input_data['vehicle_heavy'] / 100

        avg_ef_hc = avg_ef_hc_pc * input_data['vehicle_light'] / 100 + \
                     avg_ef_hc_ldv * input_data['vehicle_medium'] / 100 + \
                     avg_ef_hc_hdv * input_data['vehicle_heavy'] / 100

        avg_ef_co = avg_ef_co_pc * input_data['vehicle_light'] / 100 + \
                     avg_ef_co_ldv * input_data['vehicle_medium'] / 100 + \
                     avg_ef_co_hdv * input_data['vehicle_heavy'] / 100

        avg_ef_pm = avg_ef_pm_pc * input_data['vehicle_light'] / 100 + \
                     avg_ef_pm_ldv * input_data['vehicle_medium'] / 100 + \
                     avg_ef_pm_hdv * input_data['vehicle_heavy'] / 100

        # Return the result
        emission_factors = dict()
        if input_data['parking'] is True:
            l_idle = aggregation_input['velocity'] * input_data['idle_time'] / 60
            emission_factors['co_ef'] = (input_data['travel_distance'] / 1000 + l_idle) * avg_ef_co
            emission_factors['hc_ef'] = (input_data['travel_distance'] / 1000 + l_idle) * avg_ef_hc
            emission_factors['nox_ef'] = (input_data['travel_distance'] / 1000 + l_idle) * avg_ef_nox
            emission_factors['sox_ef'] = 0
            emission_factors['pm10_ef'] = (input_data['travel_distance'] / 1000 + l_idle) * avg_ef_pm
            emission_factors['p1_ef'] = 0
            emission_factors['p2_ef'] = 0
        else:
            emission_factors['co_ef'] = avg_ef_co
            emission_factors['hc_ef'] = avg_ef_hc
            emission_factors['nox_ef'] = avg_ef_nox
            emission_factors['sox_ef'] = 0
            emission_factors['pm10_ef'] = avg_ef_pm
            emission_factors['p1_ef'] = 0
            emission_factors['p2_ef'] = 0

        #pprint.pprint(emission_factors)
        return emission_factors

    except Exception as e:
        error = alaqsutils.print_error(roadway_emission_factors_alaqs_method.__name__, Exception, e)
        return error


def calculate_avg_ef(total_emission, total_km):
    """
    This function calculates an average emission factor based on the total emissions for all vehicles in all classes
    and the total km travelled by all vehicles in for all scenarios. The resulting EF is per vehicle per km.
    :param total_emission: total emission by all vehicles in all COPERT scenarios in grams
    :param total_km: the total km travelled by all vehicles in all COPERT classes
    :return emission_factor: the emission factor per vehicle per km travelled
    """
    try:
        if total_emission == 0:
            return 0
        if total_km == 0:
            return 0
        emission_factor = total_emission / total_km
        return emission_factor
    except Exception as e:
        alaqsutils.print_error(calculate_avg_ef.__name__, Exception, e)
        return 0


def cold_mileage_percent(trip_length, temperature):
    """
    # TODO this description comes from old ALAQS and needs improved documentation
    Calculate the percentage of a trip that are associated with cold emissions
    :param trip_length: length of the trip as defined in COPERT in km
    :param temperature: the temperature associated with the road in C
    :return beta: the percentage associated with cold emissions
    """
    try:
        # Estimates the parameter beta the cold mileage percentage for Pre-EURO I vehicles
        beta = 0.6474 - 0.02545 * trip_length - (0.00974 - 0.000385 * trip_length) * temperature
        return beta
    except Exception as e:
        error = alaqsutils.print_error(cold_mileage_percent.__name__, Exception, e)
        return error


def post_euro_i_cold_mileage_percent(trip_length, temperature, pollutant, vehicle_class):
    """
    # TODO this description comes from old ALAQS and needs improved documentation
    Calculate the percentage of a trip that are associated with cold emissions for post EURO I scenarios
    :param trip_length: length of the trip as defined in COPERT in km
    :param temperature: the temperature associated with the road in C
    :param pollutant: the pollutant being considered
    :param vehicle_class: the vehicle scenario class
    :return:
    """
    try:
        beta = cold_mileage_percent(trip_length, temperature)
        if vehicle_class == "EURO II":
            if pollutant == "NO":
                beta *= (1 - 0.72)
            elif pollutant == "CO":
                beta *= (1 - 0.72)
            elif pollutant == "VOC":
                beta *= (1 - 0.56)
            else:
                beta = beta
        elif vehicle_class == "EURO III":
            if pollutant == "NO":
                beta *= (1 - 0.32)
            elif pollutant == "CO":
                beta *= (1 - 0.62)
            elif pollutant == "VOC":
                beta *= (1 - 0.32)
            else:
                beta = beta
        elif vehicle_class == "EURO IV":
            if pollutant == "NO":
                beta *= (1 - 0.18)
            elif pollutant == "CO":
                beta *= (1 - 0.18)
            elif pollutant == "VOC":
                beta *= (1 - 0.18)
            else:
                beta = beta
        return beta
    except Exception as e:
        error = alaqsutils.print_error(post_euro_i_cold_mileage_percent.__name__, Exception, e)
        return error


def get_emission_factors(copert_data, velocity, change_point):
    """
    Calculate the emission factor using ALAQS method (modified COPERT III).

    :param copert_data: list from the default_vehicle_XXX corresponding to a specific vehicle type
    :type copert_data: list
    :param velocity: the speed of the vehicle in km/h
    :type velocity: float
    :param change_point: the speed at which we switch from using A1 data to A2 data
    :type change_point: float
    :return: emission_factor: the emission factor in g/km
    :rtype: float
    """
    try:

        if velocity <= change_point:
            a1 = copert_data[4]
            b1 = copert_data[5]
            c1 = copert_data[6]
            d1 = copert_data[7]
            e1 = copert_data[8]
            f1 = copert_data[9]
            g1 = copert_data[10]
            h1 = copert_data[11]
            emission_factor = a1 + b1 * velocity + c1 * math.pow(velocity, 2) + d1 * math.pow(velocity, e1) + \
                                f1 * math.log(velocity) + g1 * math.exp(h1 * velocity)
            #debug_file("%s,%s,%s,%s,%s,%s,%s,%s,%s" % (a1, b1, c1, d1, e1, f1, g1, h1, emission_factor))
        else:
            a2 = copert_data[13]
            b2 = copert_data[14]
            c2 = copert_data[15]
            d2 = copert_data[16]
            e2 = copert_data[17]
            f2 = copert_data[18]
            g2 = copert_data[19]
            h2 = copert_data[20]
            emission_factor = a2 + b2 * velocity + c2 * math.pow(velocity, 2) + d2 * math.pow(velocity, e2) + \
                                f2 * math.log(velocity) + g2 * math.exp(h2 * velocity)
            #debug_file("%s,%s,%s,%s,%s,%s,%s,%s,%s" % (a2, b2, c2, d2, e2, f2, g2, h2, emission_factor))
        return emission_factor
    except Exception as e:
        error = alaqsutils.print_error(get_emission_factors.__name__, Exception, e)
        return error


def get_average_trip_length(country):
    """
    Get the average estimated trip Length in km as given by COPERT 1990 updated run
    :param country: a valid 2 letter COPERT country code
    :return trip_length: the average length of a trip for the selected country
    """
    try:
        trip_length = None
        if country == "AU":     # Austria
            trip_length = 12
        if country == "BE":     # Belgium
            trip_length = 12
        if country == "DA":     # Denmark
            trip_length = 14
        if country == "EI":     # Ireland
            trip_length = 14
        if country == "EU":     # EU
            trip_length = 12.74
        if country == "SP":     # Spain
            trip_length = 12
        if country == "F1" or country == "F2" or country == "FR":  # France
            trip_length = 12
        if country == "FI":     # Finland
            trip_length = 17
        if country == "GR":     # Greece
            trip_length = 12
        if country == "GM":     # Germany
            trip_length = 14
        if country == "H":      # Hungary
            trip_length = 12
        if country == "IT":     # Italy
            trip_length = 12
        if country == "LU":     # Luxembourg
            trip_length = 12
        if country == "LT":     # Lithuania
            trip_length = 14
        if country == "NL":     # Netherlands
            trip_length = 13.1
        if country == "PO":     # Portugal
            trip_length = 12
        if country == "PL":     # Poland
            trip_length = 10
        if country == "SW":     # Sweden
            trip_length = 13
        if country == "UK":     # UK
            trip_length = 10

        return trip_length

    except Exception as e:
        error = alaqsutils.print_error(get_average_trip_length.__name__, Exception, e)
        return error


def get_hot_emission_change_points(vehicle_class, vehicle_size):
    """
    Defines the velocities at which we use method A1 or A2 for emission factors for specific classes and vehicle sizes
    :param vehicle_class: the COPERT scenario being considered
    :param vehicle_size: the COPERT size definition for the vehicles being considered
    :return change_points: the speeds in km at which to switch to using A2 (B2, C2...) values for calculating EF
    :rtype: dict
    """

    try:
        change_points = dict()

        if vehicle_class == "Pre-ECE":
            change_points['NO'] = 130
            change_points['CO'] = 100
            change_points['HC'] = 100
        elif vehicle_class == "ECE 15/00-01":
            if vehicle_size == "<1.4 l":
                change_points['NO'] = 130
                change_points['CO'] = 100
                change_points['HC'] = 100
            else:
                change_points['NO'] = 130
                change_points['CO'] = 50
                change_points['HC'] = 50
        elif vehicle_class == "ECE 15/02" or vehicle_class == "ECE 15/03":
            if vehicle_size == "<1.4 l":
                change_points['NO'] = 130
                change_points['CO'] = 19.3
                change_points['HC'] = 80
            else:
                change_points['NO'] = 130
                change_points['CO'] = 19.3
                change_points['HC'] = 60
        elif vehicle_class == "ECE 15/04":
                change_points['NO'] = 130
                change_points['CO'] = 60
                change_points['HC'] = 60
        else:
            change_points['NO'] = 130
            change_points['CO'] = 130
            change_points['HC'] = 130
        #print vehicle_class, vehicle_size, change_points
        change_points['PM'] = 130

        #debug_file("%s,%s,%s" % (change_points['NO'], change_points['CO'], change_points['HC']))

        return change_points

    except Exception as e:
        error = alaqsutils.print_error(get_hot_emission_change_points.__name__, Exception, e)
        return error


def ldv_pre_euro_over_emission_ratio_gasoline(temperature, pollutant):
    """
    Calculate the over emission ratio for gasoline LDV when the COPERT class is pre-euro
    :param temperature: the temperature associated with the road in C
    :param pollutant: the pollutant under consideration
    :return ratio: the calculated over emission ratio
    """
    try:
        ratio = None
        if pollutant == "CO":
            ratio = 3.7 - 0.09 * temperature
        elif pollutant == "NO":
            ratio = 1.14 - 0.006 * temperature
        elif pollutant == "VOC":
            ratio = 1.47 - 0.009 * temperature
        return ratio
    except Exception as e:
        error = alaqsutils.print_error(ldv_pre_euro_over_emission_ratio_gasoline.__name__, Exception, e)
        return error


def ldv_pre_euro_over_emission_ratio_diesel(temperature, pollutant):
    """
    Calculate the over emission ratio for diesel LDV when the COPERT class is pre-euro
    :param temperature: the temperature associated with the road in C
    :param pollutant: the pollutant under consideration
    :return ratio: the calculated over emission ratio
    """
    try:
        ratio = None
        if pollutant == "CO":
            ratio = 1.9 - 0.03 * temperature
        elif pollutant == "NO":
            ratio = 1.3 - 0.013 * temperature
        elif pollutant == "VOC":
            ratio = 3.1 - 0.09 * temperature
        elif pollutant == "PM":
            ratio = 1.34 - 0.008 * temperature
        return ratio

    except Exception as e:
        error = alaqsutils.print_error(ldv_pre_euro_over_emission_ratio_diesel.__name__, Exception, e)
        return error


def ldv_euro_over_emission_ratio_gasoline(velocity, temperature, pollutant, vehicle_class):
    """
    Calculates the over-emission ratio for Euro I and later gasoline vehicles
    :param velocity: speed in km/h
    :param temperature: temperature in degrees C
    :param pollutant: the pollutant being considered
    :param vehicle_class: the vehicle class being considered
    :return ratio: the calculated over emission ratio
    """
    try:
        ratio = 1
        if pollutant == "CO":
            if vehicle_class == "<1.4 l":
                if (velocity >= 5) and (velocity <= 25) and temperature <= 15:
                    ratio = 0.156 * velocity - 0.155 * temperature + 3.519
                if (velocity > 25) and (velocity <= 45) and temperature <= 15:
                    ratio = 0.538 * velocity - 0.373 * temperature - 6.24
                if (velocity >= 5) and (velocity <= 45) and temperature > 15:
                    ratio = 0.08032 * velocity - 0.444 * temperature + 9.826
            elif vehicle_class == "1.4 - 2.0 l":
                if (velocity >= 5) and (velocity <= 25) and temperature <= 15:
                    ratio = 0.121 * velocity - 0.146 * temperature + 3.766
                if (velocity > 25) and (velocity <= 45) and temperature <= 15:
                    ratio = 0.299 * velocity - 0.286 * temperature - 0.58
                if (velocity >= 5) and (velocity <= 45) and temperature > 15:
                    ratio = 0.0503 * velocity - 0.363 * temperature + 8.604
            elif vehicle_class == ">2.0 l":
                if (velocity >= 5) and (velocity <= 25) and temperature <= 15:
                    ratio = 0.0782 * velocity - 0.105 * temperature + 3.116
                if (velocity > 25) and (velocity <= 45) and temperature <= 15:
                    ratio = 0.193 * velocity - 0.194 * temperature + 0.305
                if (velocity >= 5) and (velocity <= 45) and temperature > 15:
                    ratio = 0.0321 * velocity - 0.252 * temperature + 6.332
        elif pollutant == "NO":
            if vehicle_class == "<1.4 l":
                if (velocity >= 5) and (velocity <= 25) and (temperature >= -20):
                    ratio = 0.0461 * velocity + 0.00738 * temperature + 0.755
                if (velocity > 25) and (velocity <= 45) and (temperature >= -20):
                    ratio = 0.0513 * velocity + 0.0234 * temperature + 0.616
            elif vehicle_class == "1.4 - 2.0 l":
                if (velocity >= 5) and (velocity <= 25) and (temperature >= -20):
                    ratio = 0.0458 * velocity + 0.00747 * temperature + 0.764
                if (velocity > 25) and (velocity <= 45) and (temperature >= -20):
                    ratio = 0.0484 * velocity + 0.0228 * temperature + 0.685
            elif vehicle_class == ">2.0 l":
                if (velocity >= 5) and (velocity <= 25) and (temperature >= -20):
                    ratio = 0.0343 * velocity + 0.00566 * temperature + 0.827
                if (velocity > 25) and (velocity <= 45) and (temperature >= -20):
                    ratio = 0.0375 * velocity + 0.0172 * temperature + 0.728
        elif pollutant == "VOC":
            if vehicle_class == "<1.4 l":
                if (velocity >= 5) and (velocity <= 25) and (temperature <= 15):
                    ratio = 0.154 * velocity - 0.134 * temperature + 4.937
                if (velocity > 25) and (velocity <= 45) and (temperature <= 15):
                    ratio = 0.323 * velocity - 0.24 * temperature + 0.301
                if (velocity >= 5) and (velocity <= 45) and (temperature > 15):
                    ratio = 0.0992 * velocity - 0.355 * temperature + 8.967
            elif vehicle_class == "1.4 - 2.0 l":
                if (velocity >= 5) and (velocity <= 25) and (temperature <= 15):
                    ratio = 0.157 * velocity - 0.207 * temperature + 7.007
                if (velocity > 25) and (velocity <= 45) and (temperature <= 15):
                    ratio = 0.282 * velocity - 0.338 * temperature + 4.098
                if (velocity >= 5) and (velocity <= 45) and (temperature > 15):
                    ratio = 0.0476 * velocity - 0.477 * temperature + 13.44
            elif vehicle_class == ">2.0 l":
                if (velocity >= 5) and (velocity <= 25) and (temperature <= 15):
                    ratio = 0.0814 * velocity - 0.165 * temperature + 6.464
                if (velocity > 25) and (velocity <= 45) and (temperature <= 15):
                    ratio = 0.116 * velocity - 0.229 * temperature + 5.739
                if (velocity >= 5) and (velocity <= 45) and (temperature > 15):
                    ratio = 0.0175 * velocity - 0.346 * temperature + 10.462
        return ratio
    except Exception as e:
        error = alaqsutils.print_error(ldv_euro_over_emission_ratio_gasoline.__name__, Exception, e)
        return error


def ldv_euro_over_emission_ratio_diesel(temperature, pollutant):
    """
    Calculates the over-emission ratio for Euro I and later diesel vehicles
    :param temperature: temperature in degrees C
    :param pollutant: the pollutant being considered
    :return ratio: the calculated over emission ratio
    """
    try:
        ratio = None
        if pollutant == "CO":
            ratio = 1.9 - 0.03 * temperature
        elif pollutant == "NO":
            ratio = 1.3 - 0.013 * temperature
        elif pollutant == "VOC":
            ratio = 3.1 - 0.09 * temperature
        elif pollutant == "PM":
            ratio = 1.34 - 0.008 * temperature
        return ratio
    except Exception as e:
        error = alaqsutils.print_error(ldv_euro_over_emission_ratio_diesel.__name__, Exception, e)
        return error


def get_emissions_factor_ldv_gas(velocity, pollutant):
    """
    Conventional Emission factor for Gasoline LDV < 3.5 t in g/km
    :param velocity: vehicle velocity in km
    :param pollutant: the pollutant being considered
    :return emission_factor: the calculated emission factor
    """
    emission_factor = None
    if pollutant == "NO":
        emission_factor = 0.0179 * velocity + 1.9547
    elif pollutant == "CO":
        emission_factor = 0.01104 * math.pow(velocity, 2) - 1.5132 * velocity + 57.789
    elif pollutant == "VOC":
        emission_factor = 0.000677 * math.pow(velocity, 2) - 0.117 * velocity + 5.4734
    elif pollutant == "PM":
        emission_factor = 0
    return emission_factor


def get_emissions_factor_ldv_diesel(velocity, pollutant):
    """
    Conventional Emission factor for diesel LDV < 3.5 t in g/km
    :param velocity: vehicle velocity in km
    :param pollutant: the pollutant being considered
    :return emission_factor: the calculated emission factor
    """
    emission_factor = None
    if pollutant == "NO":
        emission_factor = 0.000816 * math.pow(velocity, 2) - 0.1189 * velocity + 5.1234
    elif pollutant == "CO":
        emission_factor = 0.0002 * math.pow(velocity, 2) - 0.0256 * velocity + 1.8281
    elif pollutant == "VOC":
        emission_factor = 0.0000175 * math.pow(velocity, 2) - 0.00284 * velocity + 0.2162
    elif pollutant == "PM":
        emission_factor = 0.0000125 * math.pow(velocity, 2) - 0.000577 * velocity + 0.023
    return emission_factor


def get_emission_factor_bus_coach_diesel(velocity, pollutant, vehicle_type):
    """
    Conventional Emission factor for Gasoline LDV < 3.5 t in g/km
    :param velocity: vehicle velocity in km
    :param pollutant: the pollutant being considered
    :param vehicle_type: the COPERT vehicle type being considered
    :return emission_factor: the calculated emission factor
    """
    emission_factor = None
    if pollutant == "NO":
        if vehicle_type == "Buses":
            emission_factor = 89.174 * math.pow(velocity, -0.5185)
        elif vehicle_type == "Coaches":
            if velocity < 58.8:
                emission_factor = 125.87 * math.pow(velocity, -0.6562)
            else:
                emission_factor = 0.001 * math.pow(velocity, 2) - 0.1608 * velocity + 14.308
    elif pollutant == "CO":
        if vehicle_type == "Buses":
            emission_factor = 59.003 * math.pow(velocity, -0.7447)
        elif vehicle_type == "Coaches":
            emission_factor = 63.791 * math.pow(velocity, -0.8393)
    elif pollutant == "VOC":
        if vehicle_type == "Buses":
            emission_factor = 43.647 * math.pow(velocity, -1.0301)
        elif vehicle_type == "Coaches":
            emission_factor = 44.217 * math.pow(velocity, -0.887)
    elif pollutant == "PM":
        if vehicle_type == "Buses":
            emission_factor = 7.8609 * math.pow(velocity, -0.736)
        elif vehicle_type == "Coaches":
            emission_factor = 9.2934 * math.pow(velocity, -0.7373)
    return emission_factor


def aggregated_pre_euro_ef(aggregated_input):
    """
    Replicates functionality that was originally in modAggrPcPreEuroIEf.PCAggregatedPreEUROI_EF
    """
    try:
        # Unpack our necessary data
        year = aggregated_input['roadway_year']
        country = aggregated_input['roadway_country']
        average_trip_length = aggregated_input['average_trip_length']
        average_temperature = aggregated_input['temperature_average']
        vehicle_class = aggregated_input['vehicle_class']
        vehicle_fuel = aggregated_input['vehicle_fuel']
        vehicle_size = aggregated_input['vehicle_size']
        vehicle_type = aggregated_input['vehicle_type']
        velocity = aggregated_input['velocity']

        # Get the base year total cars and average mileage for the baseline year
        sql = "SELECT base_year_%s, average_mileage FROM default_cost319_vehicle_fleet " \
              "WHERE country=\"%s\" AND category_abbreviation=\"%s\" " \
              "AND fuel_engine=\"%s\" AND size=\"%s\" AND emission_class=\"%s\";" \
              % (year, country, vehicle_type, vehicle_fuel, vehicle_size, vehicle_class)
        sql_result = alaqsdblite.query_string(sql)

        if sql_result is not []:
            base_year_total_cars = float(sql_result[0][0])      # Number of vehicles in category
            average_mileage = float(sql_result[0][1])           # Total annual mileage per vehicle (km)

            # Product is the total number of miles for all vehicles
            product = base_year_total_cars * average_mileage
            aggregated_input['weighted_sum_pc'] += product         # Total km for all vehicles
            #debug_file("%s,%s,%s" % (base_year_total_cars, average_mileage, product))

            # Set some variables as zero to avoid "used before definition" errors
            total_em_pm = 0

            # Estimates the parameter beta the cold mileage percentage for Pre-EURO I vehicles
            beta = cold_mileage_percent(average_trip_length, average_temperature)
            beta_nox = beta
            beta_co = beta
            beta_voc = beta
            beta_pm = beta

            # TODO these things need to be made unnecessary by correcting the tables
            if vehicle_class == "Uncontrolled":
                vehicle_class = "Conventional"
            # Get hot emissions

            # Get the points at which we're dealing with A1 or A2 data
            change_point = get_hot_emission_change_points(vehicle_class, vehicle_size)

            sql_nox = "SELECT * FROM default_vehicle_nox_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                      "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""), vehicle_class)
            sql_result = alaqsdblite.query_string(sql_nox)
            ef_nox = get_emission_factors(sql_result[0], velocity, change_point['NO'])

            sql_co = "SELECT * FROM default_vehicle_co_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                     "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""), vehicle_class)
            sql_result = alaqsdblite.query_string(sql_co)
            ef_co = get_emission_factors(sql_result[0], velocity, change_point['CO'])

            sql_hc = "SELECT * FROM default_vehicle_hc_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                     "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""), vehicle_class)
            sql_result = alaqsdblite.query_string(sql_hc)
            ef_voc = get_emission_factors(sql_result[0], velocity, change_point['HC'])

            # Get cold emissions
            nox_cold = None
            co_cold = None
            voc_cold = None
            if vehicle_fuel == "Gasoline":
                nox_cold = beta_nox * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "NO") - 1)
                co_cold = beta_co * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "CO") - 1)
                voc_cold = beta_voc * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "VOC") - 1)
            elif vehicle_fuel == "Diesel":
                nox_cold = beta_nox * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "NO") - 1)
                co_cold = beta_co * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "CO") - 1)
                voc_cold = beta_voc * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "VOC") - 1)

            # Add cold start contribution
            ef_nox *= (1 + nox_cold)
            ef_co *= (1 + co_cold)
            ef_voc *= (1 + voc_cold)
            #debug_file("%s,%s,%s" % (ef_nox, ef_co, ef_voc))

            # Emission rate
            total_em_nox = ef_nox * product
            total_em_co = ef_co * product
            total_em_voc = ef_voc * product

            if vehicle_fuel == "Diesel":
                sql_pm = "SELECT * FROM default_vehicle_hc_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                         "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""), vehicle_class)
                sql_result = alaqsdblite.query_string(sql_pm)
                ef_pm = get_emission_factors(sql_result[0], velocity, 130)
                pm_cold = beta_pm * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "PM") - 1)
                ef_pm *= (1 + pm_cold)
                total_em_pm = ef_pm * product

            aggregated_input['total_em_nox_pc'] += total_em_nox
            aggregated_input['total_em_voc_pc'] += total_em_voc
            aggregated_input['total_em_co_pc'] += total_em_co
            aggregated_input['total_em_pm_pc'] += total_em_pm

        #debug_file("", True)
        return aggregated_input

    except Exception as e:
        # fix_print_with_import
        # print(sys.exc_traceback.tb_lineno, ": ", e)
        print(sys.exc_info(), ": ", e)

def aggregated_euro_ef(aggregated_input):
    """
    Function that recreates method originally in modAggrPcEuroEf.PCAggregatedEURO_EF
    """
    try:
        # Unpack our necessary data
        year = aggregated_input['roadway_year']
        country = aggregated_input['roadway_country']
        average_trip_length = aggregated_input['average_trip_length']
        average_temperature = aggregated_input['temperature_average']
        vehicle_class = aggregated_input['vehicle_class']
        vehicle_fuel = aggregated_input['vehicle_fuel']
        vehicle_size = aggregated_input['vehicle_size']
        vehicle_type = aggregated_input['vehicle_type']
        velocity = aggregated_input['velocity']

        sql = "SELECT base_year_%s, average_mileage FROM default_cost319_vehicle_fleet " \
              "WHERE country=\"%s\" AND category_abbreviation=\"%s\" " \
              "AND fuel_engine=\"%s\" AND size=\"%s\" AND emission_class=\"%s\";" \
              % (year, country, vehicle_type, vehicle_fuel, vehicle_size, vehicle_class)
        sql_result = alaqsdblite.query_string(sql)

        if sql_result is not []:
            base_year_total_cars = float(sql_result[0][0])
            average_mileage = float(sql_result[0][1])
            product = base_year_total_cars * average_mileage
            aggregated_input['weighted_sum_pc'] += product
            #debug_file("%s,%s,%s" % (base_year_total_cars, average_mileage, product))

            # Zero some of the variables to avoid "used before definition" errors
            total_em_pm = 0

            beta_nox = None
            beta_co = None
            beta_voc = None
            beta_pm = None

            if vehicle_fuel == "Gasoline":
                if vehicle_class == "EURO I":
                    beta = cold_mileage_percent(average_trip_length, average_temperature)
                    beta_nox = beta
                    beta_co = beta
                    beta_voc = beta
                    beta_pm = beta
                else:
                    beta_nox = post_euro_i_cold_mileage_percent(average_trip_length, average_temperature, "NO",
                                                                vehicle_class)
                    beta_co = post_euro_i_cold_mileage_percent(average_trip_length, average_temperature, "CO",
                                                               vehicle_class)
                    beta_voc = post_euro_i_cold_mileage_percent(average_trip_length, average_temperature, "VOC",
                                                                vehicle_class)
            elif vehicle_fuel == "Diesel":
                beta = cold_mileage_percent(average_trip_length, average_temperature)
                beta_nox = beta
                beta_co = beta
                beta_voc = beta
                beta_pm = beta

            # Some of the tables for roadway data have non-equivalent keys. Correct here
            # TODO these things need to be made unnecessary by correcting the tables
            if vehicle_class == "Uncontrolled":
                vehicle_class = "Conventional"

            get_hot_emission_change_points(vehicle_class, vehicle_size)

            # NOX Emissions
            sql_nox = "SELECT * FROM default_vehicle_nox_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                      "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""),
                                                    vehicle_class)
            sql_result = alaqsdblite.query_string(sql_nox)
            ef_nox = get_emission_factors(sql_result[0], velocity, 130)

            # CO Emissions
            sql_co = "SELECT * FROM default_vehicle_co_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                     "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""),
                                                   vehicle_class)
            sql_result = alaqsdblite.query_string(sql_co)
            ef_co = get_emission_factors(sql_result[0], velocity, 130)

            # HC Emissions
            sql_hc = "SELECT * FROM default_vehicle_hc_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                     "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""),
                                                   vehicle_class)
            sql_result = alaqsdblite.query_string(sql_hc)
            ef_voc = get_emission_factors(sql_result[0], velocity, 130)

            # Get cold emissions
            nox_cold = None
            co_cold = None
            voc_cold = None
            pm_cold = None
            if vehicle_fuel == "Gasoline":
                nox_cold = beta_nox * (ldv_euro_over_emission_ratio_gasoline(velocity, average_temperature, "NO",
                                                                             vehicle_size) - 1)
                co_cold = beta_co * (ldv_euro_over_emission_ratio_gasoline(velocity, average_temperature, "CO",
                                                                           vehicle_size) - 1)
                voc_cold = beta_voc * (ldv_euro_over_emission_ratio_gasoline(velocity, average_temperature, "VOC",
                                                                             vehicle_size) - 1)
            elif vehicle_fuel == "Diesel":
                nox_cold = beta_nox * (ldv_euro_over_emission_ratio_diesel(average_temperature, "NO") - 1)
                co_cold = beta_co * (ldv_euro_over_emission_ratio_diesel(average_temperature, "CO") - 1)
                voc_cold = beta_voc * (ldv_euro_over_emission_ratio_diesel(average_temperature, "VOC") - 1)
                pm_cold = beta_pm * (ldv_euro_over_emission_ratio_diesel(average_temperature, "PM") - 1)

            # Add cold start contribution to hot emission factor
            ef_nox *= (1 + nox_cold)
            ef_co *= (1 + co_cold)
            ef_voc *= (1 + voc_cold)
            #debug_file("%s,%s,%s" % (ef_nox, ef_co, ef_voc))

            # Emission rate
            total_em_nox = ef_nox * product
            total_em_co = ef_co * product
            total_em_voc = ef_voc * product

            # Particulates only seem to have relevance for diesel emissions
            if vehicle_fuel == "Diesel":
                sql_pm = "SELECT * FROM default_vehicle_hc_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                         "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""),
                                                       vehicle_class)
                sql_result = alaqsdblite.query_string(sql_pm)
                ef_pm = get_emission_factors(sql_result[0], velocity, 130)
                ef_pm *= (1 + pm_cold)
                total_em_pm = ef_pm * product

            aggregated_input['total_em_nox_pc'] += total_em_nox
            aggregated_input['total_em_voc_pc'] += total_em_voc
            aggregated_input['total_em_co_pc'] += total_em_co
            aggregated_input['total_em_pm_pc'] += total_em_pm

        #debug_file("", True)
        return aggregated_input

    except Exception as e:
        # fix_print_with_import
        # print(sys.exc_traceback.tb_lineno, ": ", e)
        print(sys.exc_info(), ": ", e)


def aggregated_mot_ef(aggregated_input):
    """
    Function that recreates method originally in modAggrPcEuroEf.PCAggregatedMOT
    """
    try:
        # Unpack our necessary data
        year = aggregated_input['roadway_year']
        country = aggregated_input['roadway_country']
        average_trip_length = aggregated_input['average_trip_length']
        average_temperature = aggregated_input['temperature_average']
        vehicle_class = aggregated_input['vehicle_class']
        vehicle_fuel = aggregated_input['vehicle_fuel']
        vehicle_size = aggregated_input['vehicle_size']
        vehicle_type = aggregated_input['vehicle_type']
        vehicle_mot = aggregated_input['vehicle_mot']
        velocity = aggregated_input['velocity']

        # Get the base year total cars and average mileage for the baseline year
        sql = "SELECT base_year_%s, average_mileage FROM default_cost319_vehicle_fleet " \
              "WHERE country=\"%s\" AND category_abbreviation=\"%s\" " \
              "AND size=\"%s\" AND emission_class=\"%s\";" \
              % (year, country, vehicle_type, vehicle_size, vehicle_class)
        sql_result = alaqsdblite.query_string(sql)

        if sql_result is not []:
            base_year_total_cars = float(sql_result[0][0])
            average_mileage = float(sql_result[0][1])
            product = base_year_total_cars * average_mileage
            aggregated_input['weighted_sum_pc'] += product
            #debug_file("%s,%s,%s" % (base_year_total_cars, average_mileage, product))

            # Set some variables as zero to avoid "used before definition" errors
            total_em_pm = 0

            # Estimates the parameter beta the cold mileage percentage for Pre-EURO I vehicles
            beta = cold_mileage_percent(average_trip_length, average_temperature)
            beta_nox = beta
            beta_co = beta
            beta_voc = beta
            beta_pm = beta

            # TODO these things need to be made unnecessary by correcting the tables
            if vehicle_class == "Uncontrolled":
                vehicle_class = "Conventional"
            if vehicle_class == "Controlled":
                vehicle_class = "97/24/EC"
            if vehicle_size == ">50 cc 2-s":
                vehicle_size = ">50cc"
            if vehicle_size == ">50 cc 4-s":
                vehicle_size = ">50cc"

            # Get hot emissions
            change_point = get_hot_emission_change_points(vehicle_class, vehicle_size)

            sql_nox = "SELECT * FROM default_vehicle_nox_ef WHERE vehicle_type=\"%s\" AND Class=\"%s %s\" " \
                      "AND Legislation=\"%s\";" % (vehicle_type, vehicle_mot, vehicle_size.replace(" ", ""), vehicle_class)
            sql_result = alaqsdblite.query_string(sql_nox)
            ef_nox = get_emission_factors(sql_result[0], velocity, change_point['NO'])

            sql_co = "SELECT * FROM default_vehicle_co_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                     "AND Legislation =\"%s\";" % (vehicle_type, vehicle_mot, vehicle_size.replace(" ", ""), vehicle_class)
            sql_result = alaqsdblite.query_string(sql_co)
            ef_co = get_emission_factors(sql_result[0], velocity, change_point['CO'])

            sql_hc = "SELECT * FROM default_vehicle_hc_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                     "AND Legislation =\"%s\";" % (vehicle_type, vehicle_mot, vehicle_size.replace(" ", ""), vehicle_class)
            sql_result = alaqsdblite.query_string(sql_hc)
            ef_voc = get_emission_factors(sql_result[0], velocity, change_point['HC'])

            # Get cold emissions
            nox_cold = None
            co_cold = None
            voc_cold = None
            if vehicle_fuel == "Gasoline":
                nox_cold = beta_nox * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "NO") - 1)
                co_cold = beta_co * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "CO") - 1)
                voc_cold = beta_voc * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "VOC") - 1)
            elif vehicle_fuel == "Diesel":
                nox_cold = beta_nox * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "NO") - 1)
                co_cold = beta_co * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "CO") - 1)
                voc_cold = beta_voc * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "VOC") - 1)

            # Add cold start contribution
            ef_nox *= (1 + nox_cold)
            ef_co *= (1 + co_cold)
            ef_voc *= (1 + voc_cold)
            #("%s,%s,%s" % (ef_nox, ef_co, ef_voc))

            # Emission rate
            total_em_nox = ef_nox * product
            total_em_co = ef_co * product
            total_em_voc = ef_voc * product

            if vehicle_fuel == "Diesel":
                sql_pm = "SELECT * FROM default_vehicle_hc_ef WHERE vehicle_type=\"%s\" AND Class =\"%s %s\" " \
                         "AND Legislation =\"%s\";" % (vehicle_type, vehicle_fuel, vehicle_size.replace(" ", ""), vehicle_class)
                sql_result = alaqsdblite.query_string(sql_pm)
                ef_pm = get_emission_factors(sql_result[0], velocity, 130)
                pm_cold = beta_pm * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "PM") - 1)
                ef_pm *= (1 + pm_cold)
                total_em_pm = ef_pm * product

            aggregated_input['total_em_nox_pc'] += total_em_nox
            aggregated_input['total_em_voc_pc'] += total_em_voc
            aggregated_input['total_em_co_pc'] += total_em_co
            aggregated_input['total_em_pm_pc'] += total_em_pm

        #debug_file("", True)
        return aggregated_input

    except Exception as e:
        # fix_print_with_import
        # print(sys.exc_traceback.tb_lineno, ": ", e)
        print(sys.exc_info(), ": ", e)


def aggregated_ldv_ef(aggregated_input):
    """
    Function that recreates method originally in modAggrPcEuroEf.PCAggregatedLDV
    """
    try:
        # Unpack our necessary data
        year = aggregated_input['roadway_year']
        country = aggregated_input['roadway_country']
        average_trip_length = aggregated_input['average_trip_length']
        average_temperature = aggregated_input['temperature_average']
        vehicle_class = aggregated_input['vehicle_class']
        vehicle_fuel = aggregated_input['vehicle_fuel']
        vehicle_size = aggregated_input['vehicle_size']
        vehicle_type = aggregated_input['vehicle_type']
        velocity = aggregated_input['velocity']

        # Get the base year total cars and average mileage for the baseline year
        sql = "SELECT base_year_%s, average_mileage FROM default_cost319_vehicle_fleet " \
              "WHERE country=\"%s\" AND category_abbreviation=\"%s\" AND fuel_engine=\"%s\" " \
              "AND size=\"%s\" AND emission_class=\"%s\";" \
              % (year, country, vehicle_type, vehicle_fuel, vehicle_size, vehicle_class)
        sql_result = alaqsdblite.query_string(sql)

        if sql_result is not []:
            base_year_total_cars = float(sql_result[0][0])
            average_mileage = float(sql_result[0][1])
            product = base_year_total_cars * average_mileage
            aggregated_input['weighted_sum_ldv'] += product
            #debug_file("%s,%s,%s" % (base_year_total_cars, average_mileage, product))

            # Set some variables as zero to avoid "used before definition" errors
            total_em_pm = 0

            # Estimates the parameter beta the cold mileage percentage for Pre-EURO I vehicles
            beta = cold_mileage_percent(average_trip_length, average_temperature)
            beta_nox = beta
            beta_co = beta
            beta_voc = beta
            beta_pm = beta

            ef_nox = None
            ef_co = None
            ef_voc = None

            if vehicle_fuel == "Gasoline":
                ef_nox = get_emissions_factor_ldv_gas(velocity, "NO")
                ef_co = get_emissions_factor_ldv_gas(velocity, "CO")
                ef_voc = get_emissions_factor_ldv_gas(velocity, "VOC")
            elif vehicle_fuel == "Diesel":
                ef_nox = get_emissions_factor_ldv_diesel(velocity, "NO")
                ef_co = get_emissions_factor_ldv_diesel(velocity, "CO")
                ef_voc = get_emissions_factor_ldv_diesel(velocity, "VOC")

            # Get cold emissions
            nox_cold = None
            co_cold = None
            voc_cold = None
            if vehicle_fuel == "Gasoline":
                nox_cold = beta_nox * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "NO") - 1)
                co_cold = beta_co * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "CO") - 1)
                voc_cold = beta_voc * (ldv_pre_euro_over_emission_ratio_gasoline(average_temperature, "VOC") - 1)
            elif vehicle_fuel == "Diesel":
                nox_cold = beta_nox * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "NO") - 1)
                co_cold = beta_co * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "CO") - 1)
                voc_cold = beta_voc * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "VOC") - 1)

            # Add cold start contribution
            ef_nox *= (1 + nox_cold)
            ef_co *= (1 + co_cold)
            ef_voc *= (1 + voc_cold)

            # Emission rate
            total_em_nox = ef_nox * product
            total_em_co = ef_co * product
            total_em_voc = ef_voc * product

            if vehicle_fuel == "Diesel":
                ef_pm = get_emissions_factor_ldv_diesel(velocity, "PM")
                pm_cold = beta_pm * (ldv_pre_euro_over_emission_ratio_diesel(average_temperature, "PM") - 1)
                ef_pm *= (1 + pm_cold)
                total_em_pm = ef_pm * product

            aggregated_input['total_em_nox_ldv'] += total_em_nox
            aggregated_input['total_em_voc_ldv'] += total_em_voc
            aggregated_input['total_em_co_ldv'] += total_em_co
            aggregated_input['total_em_pm_ldv'] += total_em_pm

        #debug_file("", True)
        return aggregated_input

    except Exception as e:
        # fix_print_with_import
        # print(sys.exc_traceback.tb_lineno, ": ", e)
        print(sys.exc_info(), ": ", e)


def aggregated_hdv_ef(aggregated_input):
    """
    Function that recreates method originally in modAggrPcEuroEf.PCAggregatedHDV
    """
    try:
        # Unpack our necessary data
        year = aggregated_input['roadway_year']
        country = aggregated_input['roadway_country']
        vehicle_class = aggregated_input['vehicle_class']
        vehicle_fuel = aggregated_input['vehicle_fuel']
        vehicle_size = aggregated_input['vehicle_size']
        vehicle_type = aggregated_input['vehicle_type']
        velocity = aggregated_input['velocity']

        # Get the base year total cars and average mileage for the baseline year
        sql = "SELECT base_year_%s, average_mileage FROM default_cost319_vehicle_fleet " \
              "WHERE country=\"%s\" AND category_abbreviation=\"%s\" AND fuel_engine=\"%s\" " \
              "AND size=\"%s\" AND emission_class=\"%s\";" \
              % (year, country, vehicle_type, vehicle_fuel, vehicle_size, vehicle_class)
        sql_result = alaqsdblite.query_string(sql)

        if sql_result is not []:
            base_year_total_cars = float(sql_result[0][0])
            average_mileage = float(sql_result[0][1])
            product = base_year_total_cars * average_mileage
            aggregated_input['weighted_sum_hdv'] += product

            ef_nox = get_emission_factor_bus_coach_diesel(velocity, "NO", vehicle_type)
            ef_co = get_emission_factor_bus_coach_diesel(velocity, "CO", vehicle_type)
            ef_voc = get_emission_factor_bus_coach_diesel(velocity, "VOC", vehicle_type)
            ef_pm = get_emission_factor_bus_coach_diesel(velocity, "PM", vehicle_type)

            # Emission rate
            total_em_nox = ef_nox * product
            total_em_co = ef_co * product
            total_em_voc = ef_voc * product
            total_em_pm = ef_pm * product

            aggregated_input['total_em_nox_hdv'] += total_em_nox
            aggregated_input['total_em_voc_hdv'] += total_em_voc
            aggregated_input['total_em_co_hdv'] += total_em_co
            aggregated_input['total_em_pm_hdv'] += total_em_pm

        #debug_file("", True)
        return aggregated_input
    except Exception as e:
        # fix_print_with_import
        # print(sys.exc_traceback.tb_lineno, ": ", e)
        print(sys.exc_info(), ": ", e)
