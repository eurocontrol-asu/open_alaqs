def calculate_particulate_matter_emissions(mode, sn_mode, eihc_mode, bpr):
    """

    :param mode: the mode of flight data is required for ['TX', 'AP', 'CO', 'TO']
    :param sn_mode: the smoke number for the given flight mode
    :param eihc_mode: the emission index for HC for the given mode
    :param bpr: the by-pass ratio of the engine (use zero if pure jet)
    :return: an array of all PM values:
                - EI_{non volatile}
                - EI_{fuel sulphur content}
                - EI_{volatile}
                - EI_{total emissions}
    """
    # Modal values for ratio of EI_{vol} for CFM56 (DOC 9889)
    ratio_cfm56 = dict()
    ratio_cfm56['TX'] = 6.17
    ratio_cfm56['AP'] = 56.25
    ratio_cfm56['CO'] = 76
    ratio_cfm56['TO'] = 115

    # Air fuel ratios by mode (DOC 9889)
    afr = dict()
    afr['TX'] = 106
    afr['AP'] = 83
    afr['CO'] = 51
    afr['TO'] = 45

    # Calculate CI
    if sn_mode <= 30:
        ci = 0.06949 * sn_mode ** 1.234
    else:
        ci = 0.02970 * sn_mode ** 2 - 1.803 * sn_mode + 31.94

    # Calculate exhaust volumetric flow rate
    if bpr == 0:
        q = 0.776 * afr[mode]
    else:
        q = 0.7769 * afr[mode] * (1 + bpr) + 0.887

    # Calculate emission index for PM_{non-volatile}
    ei_nonvol = (ci * q)/1000

    # Calculate emission index for PM_{fsc}
    fsc = 0.00068
    sigma = 0.024
    mw_out = 96
    mw_sul = 32
    ei_fsc = 1000 * (fsc * sigma * mw_out)/mw_sul

    # Calculate emission index for PM_{organics}
    ei_vol = ratio_cfm56[mode] * eihc_mode / 1000

    # Calculate total PM
    ei_total = ei_nonvol + ei_fsc + ei_vol

    # Return our data
    return [ei_nonvol, ei_fsc, ei_vol, ei_total]
