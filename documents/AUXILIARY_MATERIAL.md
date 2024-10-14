# Open-ALAQS User Guide - Auxiliary Material

## [Table of Contents](#table-of-contents)
- [Open-ALAQS Database](#open-alaqs-database)
  - [Emissions factors](#emission-factors)
- [ANP](#anp)
  - [Aircraft trajectories](#aircraft-trajectories)
  - [Performance profiles](#performance-profiles)
- [AUSTAL](#austal)
- [COPERT](#copert)
- [Smooth and Shift](#smooth-and-shift)

## [Open-ALAQS Database](#open-alaqs-database)
[(Back to top)](#table-of-contents)

[DB Browser for SQLite](https://sqlitebrowser.org/)

### [Emissions factors](#emission-factors)

## [ANP](#anp)
[(Back to top)](#table-of-contents)

### [Aircraft trajectories](#aircraft-trajectories)

### [Performance profiles](#performance-profiles)

## [AUSTAL](#austal)
[(Back to top)](#table-of-contents)

The dispersion model [AUSTAL](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/overview) is the reference implementation to Annex 2 of the German Environment Agency’s Technical Instructions on Air Quality Control (TA Luft) and implements the specifications and requirements given therein.

The program is the successor of AUSTAL2000 (which was previously used with Open-ALAQS), the reference implementation to Annex 3 of the TA Luft 2002. AUSTAL and AUSTAL2000 were developed by Janicke Consulting on behalf of the German Environment Agency and are freely available and widely used internationally.

AUSTAL 3.3.0 (released on 22.03.2024) has been developed and tested under Windows and Linux. It is exclusively provided, free of charge under the GNU Public Licence, from the dedicated webpage
of the German Environment Agency.

No installation is needed for use with Open-ALAQS as the executables are already included in the Open-ALAQS package.

## [COPERT](#copert)
[(Back to top)](#table-of-contents)

The estimation of roadway traffic emissions (landside, airside and parking lots) in Open-ALAQS is based on COPERT Emission Factors (EF) (version 5.4.52), the EU standard vehicle emissions calculator, developed by [EMISIA](https://www.emisia.com/utilities/copert/) for the European Environment Agency (EEA) for calculating emissions associated with road transportation.

COPERT contains emission factors for more than 450 individual vehicle types (e.g. PC, LDV, HDV) considering various factors such as vehicle type, age, mileage, and driving conditions and operation modes to provide accurate emissions estimates for a specific country or region. Its methodology comprises the road transport chapters in the [EMEP/EEA Air Emissions Inventory Guidebook](https://www.eea.europa.eu/publications/emep-eea-guidebook-2023) and is consistent with the 2006 IPCC Guidelines for the calculation of greenhouse gas emissions.

The implementation (see [copert5.py](./../open_alaqs/core/tools/copert5.py)) of the COPERT methodology in Open-ALAQS preserves the core information from the original model, albeit with some simplification tailored to the scope of Open-ALAQS. It generates typical emission factors for roadway segments or parking areas based on parameters such as fleet year (as a proxy for Euro standard), country, fleet mix and total number of vehicles, temperature, average speed (all set via the study setup UI) and roadway segment length (taken from segment geometry).

The vehicle categories that are examined are Passenger Cars (PCs), Light Commercial Vehicles (LCVs), Heavy Duty Trucks (HDTs), buses and motorcycles which are commonly operating within and around the airports. Only petrol and diesel engines are included in the database. Emission factors are provided for 37 countries: EU27 Member States, EU27 aggregated, UK, Iceland, Norway, Switzerland, Liechtenstein, North Macedonia, Turkey, Albania, Serbia and Montenegro.

**Special remarks**:
- HDTs petrol: only “Conventional” Euro standard option is available
- Motorcycles: only “Petrol” fuel option is available
- Buses: only “Diesel” fuel option is available
- Evaporative emissions: only VOC pollutant is available
- Information on vehicle age is included in the Euro standard technology information
- The EF include information for idling, since they are developed based on both real-world driving and on lab tests, both of which include indling periods in the respective real-world driving and driving cycles

The EF values used in Open-ALAQS are available in [default_vehicle_ef_copert5](./../open_alaqs/database/data/default_vehicle_ef_copert5.csv).

## [Smooth and Shift](smooth-and-shift)
[(Back to top)](#table-of-contents)

Open-ALAQS calculates three-dimensional emission distributions for source groups associated with an airport. To apply this output to dispersion models, it is necessary to account for source dynamics such as turbulence, exhaust momentum from aircraft engines, and thermal plume rise. To simplify the application of emission outputs to a dispersion model—without the need to address each individual source's dynamics or specific model details—the effects of source dynamics can be included in an approximate manner within the spatial emission distribution. This is achieved through the "Smooth & Shift" approach, which involves smoothing and shifting the initial source extent.

This approach has been used to connect the emission grid provided by Open-ALAQS' precursor model, ALAQS-AV, to dispersion models. The details  are outlined in the report [EEC/SEE/2005/016](038_Derivation_of_Smooth_and_Shift_Parameters_for_ALAQS-AV.pdf) by EUROCONTROL. The "Smooth & Shift" parameters were originally derived from [LASPORT](https://www.janicke.de/en/lasport.html) (version 1.6), which handles source dynamics in a detailed and time-dependent manner.

Since 2005, the LASPORT parameter values used to describe the source dynamics of main engines have been updated. The following describes the new parameters based on LASPORT version 2.2. Finally, it is worth noting that the "Smooth & Shift" parameters are transparently derived and easy to modify. They have been implemented for all airport-related sources, including aircraft, GSE, and GPU. APU emissions are incorporated into aircraft movements.

The figure below illustrates the change in the geometry of taxiing emissions after applying the "Smooth & Shift" parametrization. Each linestring segment of the taxiway (black line) is expanded into a polygon to account for source dynamics.

<img src="./../open_alaqs/assets/smooth-and-shift.png" alt="smooth and shift" width="50%">

The default values used in Open-ALAQS are available in [default_emission_dynamics](./../open_alaqs/database/data/default_emission_dynamics.csv).
