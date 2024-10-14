# Open-ALAQS User Guide - Auxiliary Material

## [Table of Contents](#table-of-contents)
- [Open-ALAQS Database](#open-alaqs-database)
- [ANP](#anp)
- [AUSTAL](#austal)
- [COPERT](#copert)
- [Smooth and Shift](smooth-and-shift)

## [Open-ALAQS Database](#open-alaqs-database)
[(Back to top)](#table-of-contents)

## [ANP](#anp)
[(Back to top)](#table-of-contents)

## [AUSTAL](#austal)
[(Back to top)](#table-of-contents)

The dispersion model [AUSTAL](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/overview) is the reference implementation to Annex 2 of the German Environment Agency’s Technical Instructions on Air Quality Control (TA Luft) and implements the specifications and requirements given therein.

The program is the successor of AUSTAL2000 (which was previously used with Open-ALAQS), the reference implementation to Annex 3 of the TA Luft 2002. AUSTAL and AUSTAL2000 were developed by Janicke Consulting on behalf of the German Environment Agency and are freely available and widely used internationally.

AUSTAL 3.3.0 (released on 22.03.2024) has been developed and tested under Windows and Linux. It is exclusively provided, free of charge under the GNU Public Licence, from the dedicated webpage
of the German Environment Agency.

No installation is needed for use with Open-ALAQS as the executables are already included in the Open-ALAQS package.

## [COPERT](#copert)
[(Back to top)](#table-of-contents)

## [Smooth and Shift](smooth-and-shift)
[(Back to top)](#table-of-contents)

Open-ALAQS calculates three-dimensional emission distributions for source groups associated with an airport. To apply this output to dispersion models, it is necessary to account for source dynamics such as turbulence, exhaust momentum from aircraft engines, and thermal plume rise.

To simplify the application of emission outputs to a dispersion model—without the need to address each individual source's dynamics or specific model details—the effects of source dynamics can be included in an approximate manner within the spatial emission distribution. This is achieved through the "Smooth & Shift" approach, which involves smoothing and shifting the initial source extent.

This approach has been used to connect the emission grid provided by Open-ALAQS' precursor model, ALAQS-AV, to dispersion models. The details  are outlined in the report [EEC/SEE/2005/016](038_Derivation_of_Smooth_and_Shift_Parameters_for_ALAQS-AV.pdf) by EUROCONTROL. The "Smooth & Shift" parameters were originally derived from [LASPORT](https://www.janicke.de/en/lasport.html) (version 1.6), which handles source dynamics in a detailed and time-dependent manner.

Since 2005, the LASPORT parameter values used to describe the source dynamics of main engines have been updated. The following describes the new parameters based on LASPORT version 2.2. Finally, it is worth noting that the "Smooth & Shift" parameters are transparently derived and easy to modify. They have been implemented for all airport-related sources, including aircraft, GSE, and GPU. APU emissions are incorporated into aircraft movements.

The default values used in Open-ALAQS are available in [default_emission_dynamics](./../open_alaqs/database/data/default_emission_dynamics.csv).
