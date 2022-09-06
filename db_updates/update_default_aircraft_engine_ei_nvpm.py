import sys

import pandas as pd
import sqlalchemy 
import math


SCALING_FACTORS = { "non_dac":{
        "TX":0.3,
        "TO":1.0,
        "CL":0.9,
        "AP":0.3},
"aviadvigatel":{
        "TX":0.3,
        "TO":1.0,
        "CL":1.0,
        "AP":0.8},
"ge_cf34":{
        "TX":0.3,
        "TO":1.0,
        "CL":0.4,
        "AP":0.3},
"textron_lycoming":{
        "TX":0.3,
        "TO":1.0,
        "CL":1.0,
        "AP":0.6},
"cfm_dac":{
        "TX":1.0,
        "TO":0.3,
        "CL":0.3,
        "AP":0.3}
    }

AIR_FUEL_RATIO = {
        "TX":106,
        "TO":45,
        "CL":51,
        "AP":83}


GEOMTRIC_MEAN_DIAMETERS = {
        "TX":20,
        "TO":40,
        "CL":40,
        "AP":20}

NR = 10**24
STANDARD_DEVIATION_PM = 1.8
PARTICLE_EFFECTIVE_DENSITY = 1000


def rename_column(df: pd.DataFrame, name: str, new_name: str) -> pd.DataFrame:
    """
    Changes a single column of a dataframe
    """
    return df.rename(columns={name: new_name})


def get_engine(db_url: str):
    """
    Returns the database engine
    """
    return sqlalchemy.create_engine(db_url)


if __name__ == "__main__":
    """
    # NOTES
    """

    # Check if user added right number of arguments when calling the function
    if len(sys.argv) != 3:
        raise Exception(
            "Wrong number of arguments. Correct call: `python update_default_aircraft_engine_ei sqlite:///old_url sqlite:///new_url`"
        )

    # Load old table to update
    with get_engine(sys.argv[1]).connect() as conn:
        old_blank_study = pd.read_sql("SELECT * FROM default_aircraft_engine_ei", con=conn)

    old_blank_study["nvpm_ei"] = 0.0
    old_blank_study["nvpm_number_ei"] = 0.0


    # Loop over each row of the old table and update the values of the entries found there
    for index, old_line in old_blank_study.iterrows():

        if "aviadvigatel" in old_line["manufacturer"]:
            engine_based_scaling_factor = SCALING_FACTORS["aviadgatel"][old_line["mode"]]
        elif "textron" in old_line["manufacturer"]:
            engine_based_scaling_factor = SCALING_FACTORS["textron"][old_line["mode"]]
        elif "cfm" in old_line["manufacturer"]:
            engine_based_scaling_factor = SCALING_FACTORS["cfm_dac"][old_line["mode"]]
        elif "CF34" in old_line["engine_full_name"]:
            engine_based_scaling_factor = SCALING_FACTORS["ge_cf34"][old_line["mode"]]
        else:
            engine_based_scaling_factor = SCALING_FACTORS["non_dac"][old_line["mode"]]

        
        SNk = old_line["smoke_number"]
        SNmax = old_line["smoke_number_maximum"]

        #what is both snk and snmax are 0 ????
        if SNk ==0 and SNmax != 0:
            SNk = SNmax*engine_based_scaling_factor

        
        # Calculate nvPM mass concentration:
        Ck = ((648.4*(math.exp(0.0766*SNk)))/1+ (math.exp(-1.098*(SNk-3.064))))
        

        #Evaluate beta 
        # if engine with MTF : beta=BPR, else beta=0 ???????
        # if "MTF" in engine.getValue("remark"):
        # beta=BPR

        beta = 0

        engine_based_afr = AIR_FUEL_RATIO[old_line["mode"]]
        
        #Calculate  exhaust volume
        Qk = (0.777*engine_based_afr*(1+beta)+0.767)

        #Calculate EInvPMmass
        ei_nvpm_mass_k = Ck*(10**-6)*Qk

        #Calculate the mode-dependent system loss correction factor for nvPMmass(kslm,k)
        kslm_k = math.log(3.219*Ck*(1+beta)+312.5/Ck*(1+beta)+42.6)

        #Calculate EInvPM mass (g/kg fuel)
        ei_nvpm_mass_ek = kslm_k * ei_nvpm_mass_k

        #Calculate EInvPM number (#/kg fuel)
        ei_nvpm_number_ek = (6*ei_nvpm_mass_ek*NR)/math.pi*PARTICLE_EFFECTIVE_DENSITY*((GEOMTRIC_MEAN_DIAMETERS[old_line["mode"]])**3)*(math.exp(4.5*(math.log(STANDARD_DEVIATION_PM))**2))

    
        # print(f"----NVPM NUMBER EI---{type(ei_nvpm_number_ek)}")

        #Add calculated EInvPm to the row
        old_blank_study.loc[index, "nvpm_ei"] = ei_nvpm_mass_ek
        old_blank_study.loc[index, "nvpm_number_ei"] = ei_nvpm_number_ek

    # Log calculated values
    print("Calculate nvpm_mass_ei:", (old_blank_study["nvpm_ei"]))
    print("Calculate nvpm_number_ei:", (old_blank_study["nvpm_number_ei"]))


    # Save updated database
    with get_engine(sys.argv[2]).connect() as conn:
        old_blank_study.to_sql("default_aircraft_engine_ei", con=conn, index = False, if_exists = 'replace')




# Questions:
# - what is both snk and snmax are 0 ????
#  - how to evaluate beta ?
# - results precision ? 