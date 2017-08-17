"""
Code that uses CMAC to remove and correct second trip returns, correct velocity,
produce a quasi-vertical profile, and more. """

import copy

import netCDF4
import pyart
import numpy as np


from . import processing_code


def cmac(radar, sonde, clutter_field, alt=320.0, attenuation_a_coef=None,
         **kwargs):
    """
    Corrected Moments in Antenna Coordinates

    Parameters
    ----------
    radar : Radar
        Radar object to use in the CMAC calculation.
    sonde : Object
        Object containing all the sonde data.
    clutter_field : array
        Array with xsapr_clutter field data for addition of clutter gate id.

    Other Parameters
    ----------------
    alt : float
        Value to use as default altitude for the radar object.

    Returns
    -------
    radar : Radar
        Radar object with new CMAC added fields.

    """

    radar.altitude['data'][0] = alt

    radar_start_date = netCDF4.num2date(
        radar.time['data'][0], radar.time['units'])
    print('##', str(radar_start_date))
    # ymd_string = datetime.strftime(radar_start_date, '%Y%m%d')
    # hms_string = datetime.strftime(radar_start_date, '%H%M%S')
    # print('##', ymd_string, hms_string)

    z_dict, temp_dict = pyart.retrieve.map_profile_to_gates(
        sonde.variables['tdry'][:], sonde.variables['alt'][:], radar)
    texture = processing_code.get_texture(radar)

    snr = pyart.retrieve.calculate_snr_from_reflectivity(radar)
    print('##')
    print('## These radar fields are being added:')
    radar.add_field('sounding_temperature', temp_dict, replace_existing=True)
    print('##    sounding_temperature')
    radar.add_field('height', z_dict, replace_existing=True)
    print('##    height')
    radar.add_field('SNR', snr, replace_existing=True)
    print('##    SNR')
    radar.add_field('velocity_texture', texture, replace_existing=True)
    print('##    velocity_texture')

    print('##    gate_id')
    my_fuzz, cats = processing_code.do_my_fuzz(radar, **kwargs)
    radar.add_field('gate_id', my_fuzz,
                    replace_existing=True)
    radar.fields['gate_id']['data'][clutter_field == 1] = 5
    notes = radar.fields['gate_id']['notes']
    radar.fields['gate_id']['notes'] = notes + ',5:clutter'
    radar.fields['gate_id']['valid_max'] = 5
    cat_dict = {}
    for pair_str in radar.fields['gate_id']['notes'].split(','):
        cat_dict.update(
            {pair_str.split(':')[1]:int(pair_str.split(':')[0])})

    print('##    corrected_velocity')
    cmac_gates = pyart.correct.GateFilter(radar)
    cmac_gates.exclude_all()
    cmac_gates.include_equal('gate_id', cat_dict['rain'])
    cmac_gates.include_equal('gate_id', cat_dict['melting'])
    cmac_gates.include_equal('gate_id', cat_dict['snow'])
    corr_vel = pyart.correct.dealias_region_based(
        radar, vel_field='velocity', keep_original=False,
        gatefilter=cmac_gates, centered=True)
    radar.add_field('corrected_velocity', corr_vel, replace_existing=True)

    print('##    corrected_differential_phase')
    phidp, kdp = pyart.correct.phase_proc_lp(radar, 0.0, debug=True)
    radar.add_field('corrected_differential_phase', phidp)
    print('##    corrected_specific_diff_phase')
    radar.add_field('corrected_specific_diff_phase', kdp)

    print('##    specific_attenuation')
    if attenuation_a_coef is None:
        attenuation_a_coef = 0.17 #X-Band


    spec_at, cor_z_atten = pyart.correct.calculate_attenuation(
        radar, 0, refl_field='reflectivity',
        ncp_field='normalized_coherent_power',
        rhv_field='cross_correlation_ratio',
        phidp_field='corrected_differential_phase',
        a_coef=attenuation_a_coef)

    cat_dict = {}
    for pair_str in radar.fields['gate_id']['notes'].split(','):
        print(pair_str)
        cat_dict.update({pair_str.split(':')[1]: int(pair_str.split(':')[0])})

    rain_gates = pyart.correct.GateFilter(radar)
    rain_gates.exclude_all()
    rain_gates.include_equal('gate_id', cat_dict['rain'])

    spec_at['data'][rain_gates.gate_excluded] = 0.0

    radar.add_field('specific_attenuation', spec_at)
    print('##    corrected_reflectivity_attenuation')
    radar.add_field('corrected_reflectivity_attenuation', cor_z_atten)

    print('## Rainfall rate as a function of A ##')
    R = 51.3 * (radar.fields['specific_attenuation']['data']) ** 0.81
    rainrate = copy.deepcopy(radar.fields['specific_attenuation'])
    rainrate['data'] = R
    rainrate['valid_min'] = 0.0
    rainrate['valid_max'] = 400.0
    rainrate['standard_name'] = 'rainfall_rate'
    rainrate['long_name'] = 'rainfall_rate'
    rainrate['least_significant_digit'] = 1
    rainrate['units'] = 'mm/hr'
    radar.fields.update({'rain_rate_A': rainrate})

    #This needs to be updated to a gatefilter
    mask = radar.fields['reflectivity']['data'].mask

    radar.fields['rain_rate_A']['data'][np.where(mask)] = 0.0
    radar.fields['rain_rate_A'].update({
        'comment': ('Rain rate calculated from specific_attenuation,',
                    ' R=51.3*specific_attenuation**0.81, note R=0.0 where',
                    ' norm coherent power < 0.4 or rhohv < 0.8')})


    print('##')
    print('## All CMAC fields have been added to the radar object.')
    print('##')

    print('## A quasi-vertical profile is being created.')
    qvp = processing_code.retrieve_qvp(radar, radar.fields['height']['data'])
    radar.qvp = qvp
    print('## The quasi-vertical profile has been created and',
          'can be accessed with radar.qvp')
    return radar
