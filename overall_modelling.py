"""Two-loop heat pump converted from LT_HT_complete_HeatPump_R1233zdE_Series_GroupB.ipynb.

Mixture properties come from the selected NPZ table using TabularMixtureWrapper;
CoolProp supplies water properties and the pure R1233zd(E) reference.
Default: run every NPZ table in the adjacent tables folder and save one summary.
Each case uses the same composition in both independent loops.
Retains notebook design assumptions: evaporation temperatures are DEW points
(35/45 C), condensation temperatures are BUBBLE points (80/95 C).
Superheat is relative to dew; subcooling is relative to bubble.
User-selected suction superheat is LT 8 K / HT 10 K.
These exceed the calculated dry-discharge thresholds for the supplied tables.
This is not a broader cycle optimization.
A converged solution must still have positive exchanger pinch differences.

Run with the workshop Python environment:
    python LT_HT_complete_HeatPump_Mixture_Series_GroupB.py
    python LT_HT_complete_HeatPump_Mixture_Series_GroupB.py --table Isopentane_Isobutane_mass_0.30_0.70.npz
    python LT_HT_complete_HeatPump_Mixture_Series_GroupB.py --plots

Default mode: fixed-ua; output: mixture_summary_fixed_ua.npz beside this script.
Use --mode fixed-pinch --pinch-k 3 to solve exchanger pressures from a
specified minimum temperature difference and recalculate UA.
Use --mode fixed-temperature to reproduce the original pressure-specified study.
Fixed-UA mode calculates a pure R1233zd(E) reference, then replaces the two
evaporating-pressure and two superheat specifications with its four sectioned
UA values. Condensing pressures and subcooling remain specified; superheat and
evaporating pressures are solved. Solved evaporation temperatures can differ
from initial values.
All relative input/output paths resolve from the script directory.
--table selects one case; omission runs all provided tables.
--plots saves per-case PNGs; batch execution never opens plot windows.
The archive contains numeric/string arrays and JSON schema metadata, without pickle.
Requires tespy, CoolProp, numpy, scipy and matplotlib. REFPROP is not required.
"""
# ---1_Imports---
import argparse
import json
from pathlib import Path

# User-selected superheats; calculated thresholds below are retained for reference.
# LT threshold: 7.340524921603881 K; R1336MZZZ_R1336MZZE_mass_0.80_0.20.
# HT threshold: 9.515431312759121 K; Isopentane_Isobutane_mass_0.90_0.10.
# Recompute if operating conditions or input tables change.
LT_SUPERHEAT_K = 8.0
HT_SUPERHEAT_K = 10.0


def run_case(args):
    # ---1b_Model_and_property_imports---
    from tespy.networks import Network
    from tespy.components import (
        Source, Sink, Compressor, Valve, SectionedHeatExchanger, CycleCloser
    )
    from tespy.connections import Connection

    import numpy as np
    import matplotlib.pyplot as plt
    from CoolProp.CoolProp import PropsSI as water_props
    from tabular_mixture_wrapper import TabularMixtureWrapper
    from tespy.tools.fluid_properties.wrappers import CoolPropWrapper


    # ---2_Network_and_units---
    nw = Network()
    nw.units.set_defaults(
        temperature='degC', pressure='bar', pressure_difference='bar',
        enthalpy='kJ/kg', mass_flow='kg/s', power='kW', heat='kW'
    )


    # ---3_Components---
    lt_cycle_closer = CycleCloser('LT-cycle-closer')
    lt_compressor = Compressor('LT-compressor')
    lt_condenser = SectionedHeatExchanger('LT-condenser')
    lt_expansion_valve = Valve('LT-expansion-valve')
    lt_evaporator = SectionedHeatExchanger('LT-evaporator')

    ht_cycle_closer = CycleCloser('HT-cycle-closer')
    ht_compressor = Compressor('HT-compressor')
    ht_condenser = SectionedHeatExchanger('HT-condenser')
    ht_expansion_valve = Valve('HT-expansion-valve')
    ht_evaporator = SectionedHeatExchanger('HT-evaporator')

    geothermal_source = Source('geothermal-source')   # real: 60 degC
    geothermal_sink = Sink('geothermal-sink')      # real: injection limit, 40 degC
    dh_source = Source('dh-source')   # real: 60 degC
    dh_sink = Sink('dh-sink')       # real: supply target, 90 degC


    # ---4_Connections_working_fluid_loops---
    # ---4a_Connections_LT_working_fluid_loop---
    b01 = Connection(lt_cycle_closer, 'out1', lt_compressor, 'in1', label='b01')          # LT compressor suction
    b02 = Connection(lt_compressor, 'out1', lt_condenser, 'in1', label='b02')   # LT compressor discharge
    b03 = Connection(lt_condenser, 'out1', lt_expansion_valve, 'in1', label='b03')        # LT subcooled liquid
    b04 = Connection(lt_expansion_valve, 'out1', lt_evaporator, 'in2', label='b04')       # LT evaporator inlet
    b05 = Connection(lt_evaporator, 'out2', lt_cycle_closer, 'in1', label='b05')        # closes the LT cycle

    nw.add_conns(b01, b02, b03, b04, b05)


    # ---4b_Connections_HT_working_fluid_loop---
    c01 = Connection(ht_cycle_closer, 'out1', ht_compressor, 'in1', label='c01')          # HT compressor suction
    c02 = Connection(ht_compressor, 'out1', ht_condenser, 'in1', label='c02')   # HT compressor discharge
    c03 = Connection(ht_condenser, 'out1', ht_expansion_valve, 'in1', label='c03')        # HT subcooled liquid
    c04 = Connection(ht_expansion_valve, 'out1', ht_evaporator, 'in2', label='c04')       # HT evaporator inlet
    c05 = Connection(ht_evaporator, 'out2', ht_cycle_closer, 'in1', label='c05')        # closes the HT cycle

    nw.add_conns(c01, c02, c03, c04, c05)


    # ---5_Connections_geothermal_side---
    a01 = Connection(geothermal_source, 'out1', ht_evaporator, 'in1', label='a01')   # production -> HT-evaporator
    a02 = Connection(ht_evaporator, 'out1', lt_evaporator, 'in1', label='a02')   # HT-evaporator -> LT-evaporator
    a03 = Connection(lt_evaporator, 'out1', geothermal_sink, 'in1', label='a03')        # LT-evaporator -> injection

    nw.add_conns(a01, a02, a03)


    # ---6_Connections_district_heating_side---
    d01 = Connection(dh_source, 'out1', lt_condenser, 'in2', label='d01')     # return -> LT-condenser
    d02 = Connection(lt_condenser, 'out2', ht_condenser, 'in2', label='d02')  # LT-condenser -> HT-condenser
    d03 = Connection(ht_condenser, 'out2', dh_sink, 'in1', label='d03')    # HT-condenser -> supply

    nw.add_conns(d01, d02, d03)


    # ---7_Refrigerant_side_design_point---
    # ---7a_Mixture_table_and_property_wrapper---
    reference = getattr(args, 'reference', False)
    if reference:
        FLUID = 'R1233zd(E)'
        engine_class = CoolPropWrapper
        engine_kwargs = {}
        wrapper = CoolPropWrapper(FLUID)
        table_path = None
        meta = {}
        dome_Tb = np.linspace(280, water_props('Tcrit',FLUID)-0.3,200)
        dome_Td = dome_Tb.copy()
        dome_sb = water_props('S','T',dome_Tb,'Q',0,FLUID)
        dome_sd = water_props('S','T',dome_Td,'Q',1,FLUID)
        print('Reference fluid: R1233zd(E), CoolProp')
    else:
        FLUID = 'TabulatedMixture'
        table_path = args.table
        if not table_path.is_absolute():
            table_path = Path(__file__).resolve().parent / 'tables' / table_path
        table_path = table_path.resolve()
        if not table_path.is_file():
            raise FileNotFoundError(f'Mixture table not found: {table_path}')
        wrapper = TabularMixtureWrapper(FLUID, path=str(table_path))
        with np.load(table_path, allow_pickle=False) as data:
            meta = json.loads(str(data['metadata']))
            dome_Tb = data['sat_T_bubble'].copy()
            dome_Td = data['sat_T_dew'].copy()
            dome_sb = data['sat_s_bubble'].copy()
            dome_sd = data['sat_s_dew'].copy()
        print(f'Using mixture properties: {table_path}')
        print(f'Composition: {meta["fractions"]} ({meta["mixture_type"]})')
        engine_class = TabularMixtureWrapper
        engine_kwargs = {'path': str(table_path)}

    # All refrigerant property calls use the supplied table. CoolProp is water-only.
    def fluid_property(output, key1, value1, key2, value2, fluid):
        if fluid == 'water' or (reference and fluid == FLUID):
            return water_props(output, key1, value1, key2, value2, fluid)
        if fluid != FLUID:
            raise ValueError(f'Unexpected fluid: {fluid}')
        if (output, key1, key2) == ('P', 'T', 'Q'):
            temperature = float(value1)
            curve = dome_Tb if value2 == 0 else dome_Td
            if not curve.min() <= temperature <= curve.max():
                raise ValueError('Saturation temperature outside table range.')
            return wrapper.p_sat_TQ(temperature, value2)
        if key1 == 'P' and key2 == 'H' and output in ('T', 'S'):
            fn = wrapper.T_ph if output == 'T' else wrapper.s_ph
            return np.vectorize(fn, otypes=[float])(value1, value2)
        raise ValueError(f'Unsupported tabular property request: {output}, {key1}, {key2}')


    # ---7b_Design_temperatures_and_pressures---
    T_evap, T_cond, superheat, subcool = 35, 80, LT_SUPERHEAT_K, 3          # LT loop
    ht_T_evap, ht_T_cond, ht_superheat, ht_subcool = 45, 95, HT_SUPERHEAT_K, 5   # HT loop

    p_evap = fluid_property('P', 'T', T_evap + 273.15, 'Q', 1, FLUID) / 1e5
    p_cond = fluid_property('P', 'T', T_cond + 273.15, 'Q', 0, FLUID) / 1e5
    ht_p_evap = fluid_property('P', 'T', ht_T_evap + 273.15, 'Q', 1, FLUID) / 1e5
    ht_p_cond = fluid_property('P', 'T', ht_T_cond + 273.15, 'Q', 0, FLUID) / 1e5

    print(f'LT: p_evap = {p_evap:.3f} bar, p_cond = {p_cond:.3f} bar, pr = {p_cond / p_evap:.2f}')
    print(f'HT: p_evap = {ht_p_evap:.3f} bar, p_cond = {ht_p_cond:.3f} bar, pr = {ht_p_cond / ht_p_evap:.2f}')


    # ---8_Parameters_geothermal_side---
    lt_evaporator.set_attr(pr1=1, pr2=1)
    ht_evaporator.set_attr(pr1=1, pr2=1)

    a01.set_attr(fluid={'water': 1}, T=60, p=5, m=100)   # real: geothermal production
    a02.set_attr(T=50)                                    # design choice: LT/HT geothermal split
    a03.set_attr(T=40)                                    # real: injection limit


    # ---9_Parameters_district_heating_side---
    lt_condenser.set_attr(pr1=1, pr2=1)
    ht_condenser.set_attr(pr1=1, pr2=1)

    d01.set_attr(fluid={'water': 1}, T=60, p=5)   # real: district heating return -- mass flow left FREE (result)
    d03.set_attr(T=90)                            # real: district heating supply target


    # ---10_Compressors_constant_isentropic_efficiency---
    lt_compressor.set_attr(eta_s=0.75)
    b01.set_attr(fluid={FLUID: 1}, fluid_engines={FLUID: engine_class}, fluid_wrapper_kwargs={FLUID: engine_kwargs}, p=p_evap, td_dew=superheat)   # LT mass flow left FREE (result)
    b02.set_attr(p=p_cond)
    b03.set_attr(td_bubble=subcool)

    ht_compressor.set_attr(eta_s=0.75)
    c01.set_attr(fluid={FLUID: 1}, fluid_engines={FLUID: engine_class}, fluid_wrapper_kwargs={FLUID: engine_kwargs}, p=ht_p_evap, td_dew=ht_superheat)   # HT mass flow left FREE (result)
    c02.set_attr(p=ht_p_cond)
    c03.set_attr(td_bubble=ht_subcool)


    # ---11_Solve---
    nw.solve('design')
    if not nw.converged:
        raise RuntimeError('TESPy design calculation did not converge.')

    # ---11c_Fixed_UA_same_heating_task---
    # First solve at the original pressure specifications to obtain a warm start.
    target_ua = getattr(args, 'fixed_ua', None)
    exchangers = [lt_evaporator, lt_condenser, ht_evaporator, ht_condenser]
    target_pinch = getattr(args, 'target_pinch', None)
    if target_pinch is not None:
        if target_ua is not None:
            raise ValueError('Fixed UA and fixed pinch cannot both replace the same pressures.')
        if target_pinch <= 0:
            raise ValueError('Target pinch must be positive.')
        start_pinch = np.array([hx.td_pinch.val for hx in exchangers])
        for conn in (b01,b02,c01,c02):
            conn.set_attr(p=None)
        # UA is free: each minimum-pinch equation replaces one fixed pressure.
        for weight in np.linspace(0,1,6)[1:]:
            for hx,value in zip(exchangers,start_pinch+weight*(target_pinch-start_pinch)):
                hx.set_attr(td_pinch=float(value))
            nw.solve('design')
            if not nw.converged:
                raise RuntimeError(f'Pinch solve did not converge at continuation {weight:.1f}.')
        p_evap,p_cond,ht_p_evap,ht_p_cond=[c.p.val for c in (b01,b02,c01,c02)]
    if target_ua is not None:
        start_ua = np.array([hx.UA.val_SI for hx in exchangers])
        # Four UA equations replace two evaporating-pressure and two
        # superheat specifications. Condensing pressures remain fixed.
        b01.set_attr(p=None, td_dew=None)
        c01.set_attr(p=None, td_dew=None)
        # Continue gradually from the initial exchanger conductances to reference.
        for weight in np.linspace(0,1,6)[1:]:
            for hx,value in zip(exchangers, start_ua+weight*(target_ua-start_ua)):
                hx.set_attr(UA=float(value))
            nw.solve('design')
            if not nw.converged:
                raise RuntimeError(f'Fixed-UA solve did not converge at continuation {weight:.1f}.')
        actual_ua = np.array([hx._calc_UA_from_sections() for hx in exchangers])
        np.testing.assert_allclose(actual_ua, target_ua, rtol=1e-5, atol=0.1)
        p_evap,p_cond,ht_p_evap,ht_p_cond = [c.p.val for c in (b01,b02,c01,c02)]
    nw.print_results()

    # ---11_Wrapper_integration_verification---
    # Verify the actual engines propagated by TESPy, not just the input settings.
    refrigerant_connections = (b01,b02,b03,b04,b05,c01,c02,c03,c04,c05)
    for conn in refrigerant_connections:
        engine = conn.fluid.wrapper.get(FLUID)
        if not isinstance(engine, engine_class):
            raise RuntimeError(f'{conn.label}: TESPy is not using TabularMixtureWrapper.')
        if not reference and Path(engine.path).resolve() != table_path:
            raise RuntimeError(f'{conn.label}: TESPy is using the wrong mixture table.')
        if not reference and not np.allclose(engine.fractions, meta['fractions'], rtol=0, atol=1e-12):
            raise RuntimeError(f'{conn.label}: mixture composition does not match the table.')
        # TESPy display units: bar, kJ/kg, C. Wrapper units: Pa, J/kg, K.
        p_si, h_si = conn.p.val*1e5, conn.h.val*1e3
        if not np.isclose(conn.T.val+273.15, wrapper.T_ph(p_si,h_si), atol=1e-5, rtol=0):
            raise RuntimeError(f'{conn.label}: TESPy and table temperatures disagree.')
        if not reference and not np.isclose(conn.x.val, wrapper.Q_ph(p_si,h_si), atol=1e-6, rtol=0):
            raise RuntimeError(f'{conn.label}: TESPy and table vapor qualities disagree.')
    solved_superheats = []
    wet_suction = False
    for inlet,outlet,liquid,sh,sc in [
        (b01,b02,b03,superheat,subcool),
        (c01,c02,c03,ht_superheat,ht_subcool)]:
        actual_superheat = inlet.T.val + 273.15 - wrapper.T_dew(inlet.p.val*1e5)
        solved_superheats.append(actual_superheat)
        if target_ua is None:
            # Pressure-specified and fixed-pinch modes prescribe superheat.
            np.testing.assert_allclose(actual_superheat, sh, atol=1e-5, rtol=0)
        elif not np.isfinite(actual_superheat):
            # In fixed-UA mode superheat is solved and must remain finite.
            raise ValueError(
                f'{inlet.label}: solved superheat must be finite; '
                f'got {actual_superheat:.6g} K.')
        elif actual_superheat <= 0:
            # Keep the case for comparison, but flag a physically wet suction.
            wet_suction = True
            print(
                f'WARNING: {inlet.label}: solved superheat is '
                f'{actual_superheat:.3f} K (wet suction).')
        np.testing.assert_allclose(liquid.T.val+273.15,
            wrapper.T_bubble(liquid.p.val*1e5)-sc, atol=1e-5, rtol=0)
        h_ideal=wrapper.isentropic(inlet.p.val*1e5,inlet.h.val*1e3,outlet.p.val*1e5)
        np.testing.assert_allclose(outlet.h.val*1e3,
            inlet.h.val*1e3+(h_ideal-inlet.h.val*1e3)/0.75, atol=1e-3, rtol=1e-8)
    print('Wrapper integration verified: all 10 refrigerant connections, table path, '
          'composition, SI conversions, dew/bubble offsets and isentropic compression.')

    # ---11a_Table_range_and_temperature_glide_checks---
    for conn in (() if reference else (b01, b02, b03, b04, c01, c02, c03, c04)):
        region, logp, sigma = wrapper._locate(conn.p.val * 1e5, conn.h.val * 1e3)
        if not meta['p_min'] <= conn.p.val * 1e5 <= meta['p_max'] or not -1e-8 <= sigma <= 1 + 1e-8:
            raise ValueError(f'{conn.label}: solved state outside mixture table range.')
    for name, pe, pc in [('LT', p_evap, p_cond), ('HT', ht_p_evap, ht_p_cond)]:
        for process, pressure in [('evaporation', pe), ('condensation', pc)]:
            tb = wrapper.T_bubble(pressure * 1e5) - 273.15
            td = wrapper.T_dew(pressure * 1e5) - 273.15
            print(f'{name} {process}: bubble={tb:.2f} C, dew={td:.2f} C, glide={td-tb:.2f} K')
    # ---11b_Internal_pinch_check---
    for hx in (lt_evaporator, lt_condenser, ht_evaporator, ht_condenser):
        pinch = hx.td_pinch.val
        print(f'{hx.label}: sectioned pinch = {pinch:.3f} K')
        if pinch <= 0:
            print('WARNING: temperature crossover; this design is not physically feasible.')


    # ---12_Pinch_point_check---
    print('LT refrigerant mass flow rate:', round(b01.m.val, 3), 'kg/s')
    print('HT refrigerant mass flow rate:', round(c01.m.val, 3), 'kg/s')
    print('District heating mass flow rate (RESULT):', round(d01.m.val, 2), 'kg/s')
    print('District heating intermediate temperature (RESULT):', round(d02.T.val, 2), 'degC')
    print()
    print(f"{'Component':<15}{'ttd_u [K]':>12}{'ttd_l [K]':>12}")
    for hx in [lt_evaporator, lt_condenser, ht_evaporator, ht_condenser]:
        flag_u = '  <-- violation!' if hx.ttd_u.val < 0 else ''
        flag_l = '  <-- violation!' if hx.ttd_l.val < 0 else ''
        print(f"{hx.label:<15}{hx.ttd_u.val:>12.2f}{hx.ttd_l.val:>12.2f}"
              f"{flag_u if hx.ttd_u.val < 0 else flag_l}")

    for name, conn, T_target in [('LT', b02, T_cond), ('HT', c02, ht_T_cond)]:
        if conn.x.val < 1:
            print()
            print(f'NOTE: {name} compressor discharge quality x = {conn.x.val:.3f} (< 1) -- wet compression.')
        else:
            print(f'{name} discharge is dry ({conn.T.val - (wrapper.T_dew(conn.p.val * 1e5) - 273.15):.1f} K of superheat at the outlet).')


    # ---13_Key_results---
    P_LT, P_HT = lt_compressor.P.val, ht_compressor.P.val
    Q_LT_evap, Q_HT_evap = lt_evaporator.Q.val, ht_evaporator.Q.val
    Q_LT_cond, Q_HT_cond = lt_condenser.Q.val, ht_condenser.Q.val

    Q_useful = -Q_LT_cond + -Q_HT_cond   # kW, total heat delivered to the district-heating network
    P_total = P_LT + P_HT
    COP_overall = Q_useful / P_total

    print('================ LT LOOP ================')
    print(f'Refrigerant mass flow rate   : {b01.m.val:8.2f} kg/s')
    print(f'Pressure ratio                : {b02.p.val / b01.p.val:8.2f}')
    print(f'Compressor power              : {P_LT:8.1f} kW')
    print(f'Evaporator / condenser duty   : {-Q_LT_evap:8.1f} / {-Q_LT_cond:8.1f} kW')
    print(f'COP (LT loop only)            : {-Q_LT_cond / P_LT:8.2f}')

    print()
    print('================ HT LOOP ================')
    print(f'Refrigerant mass flow rate   : {c01.m.val:8.2f} kg/s')
    print(f'Pressure ratio                : {c02.p.val / c01.p.val:8.2f}')
    print(f'Compressor power              : {P_HT:8.1f} kW')
    print(f'Evaporator / condenser duty   : {-Q_HT_evap:8.1f} / {-Q_HT_cond:8.1f} kW')
    print(f'COP (HT loop only)            : {-Q_HT_cond / P_HT:8.2f}')

    print()
    print('================ FULL SYSTEM ================')
    print(f'Total compressor power        : {P_total:8.1f} kW')
    print(f'Total heat delivered           : {Q_useful:8.1f} kW')
    print(f'Overall COP                    : {COP_overall:8.2f}')



    # ---13a_Collect_plotting_data_and_case_results---
    connections = [a01, a02, a03, b01, b02, b03, b04, b05,
                   c01, c02, c03, c04, c05, d01, d02, d03]
    exchangers = [lt_evaporator, lt_condenser, ht_evaporator, ht_condenser]
    state = np.array([[c.m.val, c.p.val, c.h.val, c.T.val, c.x.val,
                       (wrapper.s_ph(c.p.val*1e5, c.h.val*1e3) if c in
                        [b01,b02,b03,b04,b05,c01,c02,c03,c04,c05] else
                        water_props('S','P',c.p.val*1e5,'H',c.h.val*1e3,'water'))/1e3]
                      for c in connections])
    hx_results = np.array([[abs(hx.Q.val), hx.UA.val, hx.td_pinch.val,
                            hx.ttd_u.val, hx.ttd_l.val] for hx in exchangers])
    metrics = np.array([COP_overall, -Q_LT_cond/P_LT, -Q_HT_cond/P_HT,
                        P_total, P_LT, P_HT, Q_useful, -Q_LT_cond, -Q_HT_cond,
                        -Q_LT_evap, -Q_HT_evap, b01.m.val, c01.m.val,
                        d01.m.val, d02.T.val, sum(hx.UA.val for hx in exchangers)])
    profiles = []
    for hot_in, hot_out, cold_in, cold_out, hot_fluid, cold_fluid in [
        (a02,a03,b04,b01,'water',FLUID), (b02,b03,d01,d02,FLUID,'water'),
        (a01,a02,c04,c01,'water',FLUID), (c02,c03,d02,d03,FLUID,'water')]:
        q = np.linspace(0, cold_in.m.val*(cold_out.h.val-cold_in.h.val), 200)
        hh = hot_out.h.val+q/hot_in.m.val
        hc = cold_in.h.val+q/cold_in.m.val
        th = fluid_property('T','P',hot_in.p.val*1e5,'H',hh*1e3,hot_fluid)-273.15
        tc = fluid_property('T','P',cold_in.p.val*1e5,'H',hc*1e3,cold_fluid)-273.15
        profiles.append(np.column_stack([q,th,tc]))
    cycles = []
    for states in [(b01,b02,b03,b04),(c01,c02,c03,c04)]:
        curves = []
        for i,j in [(0,1),(1,2),(2,3),(3,0)]:
            ci,cj = states[i], states[j]
            h = np.linspace(ci.h.val,cj.h.val,100)*1e3
            pressure = np.linspace(ci.p.val,cj.p.val,100)*1e5
            # Compression and throttling paths are endpoint illustrations.
            curves.append(np.column_stack([
                np.linspace(ci.T.val,cj.T.val,100) if i in (0,2) else
                fluid_property('T','P',pressure,'H',h,FLUID)-273.15,
                np.linspace(wrapper.s_ph(ci.p.val*1e5,ci.h.val*1e3),
                            wrapper.s_ph(cj.p.val*1e5,cj.h.val*1e3),100)/1e3 if i in (0,2) else
                fluid_property('S','P',pressure,'H',h,FLUID)/1e3]))
        cycles.append(curves)
    from pinch_locator import locate_pinch
    pinch_locations, pinch_labels = locate_pinch(
        state, [c.label for c in connections], wrapper, points=501)
    np.testing.assert_allclose(Q_useful, P_total-Q_LT_evap-Q_HT_evap,
                               rtol=1e-7, atol=1e-4)
    wet = bool(b02.x.val < 1-1e-6 or c02.x.val < 1-1e-6)
    wet_suction = wet_suction or bool(b01.x.val < 1-1e-6 or c01.x.val < 1-1e-6)
    crossover = bool(np.min(hx_results[:,2]) <= 0 or
                     any(np.min(pr[:,1]-pr[:,2]) <= 0 for pr in profiles))
    crossover = crossover or bool(np.min(pinch_locations[:,0]) <= 0)
    if not np.isfinite(pinch_locations).all():
        raise ValueError('Non-finite continuous pinch results.')
    if not np.isfinite(metrics).all() or not np.isfinite(state).all():
        raise ValueError('Non-finite solved results.')
    result = dict(metrics=metrics, states=state, heat_exchangers=hx_results,
                  tq_profiles=np.array(profiles), ts_cycles=np.array(cycles),
                  wet_discharge=wet, wet_suction=wet_suction,
                  temperature_crossover=crossover,
                  passes_checks=not (wet or wet_suction or crossover),
                  pinch_locations=pinch_locations,
                  pressure_ratios=np.array([b02.p.val/b01.p.val,c02.p.val/c01.p.val]),
                  superheats=np.array(solved_superheats))
    if not args.plots:
        return result

    # ---14_T_s_diagram_and_T_Q_diagrams---
    # ---14a_T_s_diagram---
    def conn_Ts(conn):
        p_Pa = conn.p.val * 1e5
        h_Jkg = conn.h.val * 1e3
        T = fluid_property('T', 'P', p_Pa, 'H', h_Jkg, FLUID) - 273.15
        s = fluid_property('S', 'P', p_Pa, 'H', h_Jkg, FLUID) / 1e3
        return T, s


    def isobar_Ts(p_bar, h1_kJkg, h2_kJkg, n=40):
        p_Pa = p_bar * 1e5
        hs = np.linspace(h1_kJkg, h2_kJkg, n) * 1e3
        T = fluid_property('T', 'P', p_Pa, 'H', hs, FLUID) - 273.15
        s = fluid_property('S', 'P', p_Pa, 'H', hs, FLUID) / 1e3
        return T, s


    # Saturation boundaries are read from the selected mixture table.
    sf, sg = dome_sb / 1e3, dome_sd / 1e3
    T_dome_b, T_dome_d = dome_Tb - 273.15, dome_Td - 273.15

    fig, ax = plt.subplots(figsize=(7.5, 6))
    ax.plot(np.concatenate([sf, sg[::-1]]), np.concatenate([T_dome_b, T_dome_d[::-1]]),
            'k-', lw=1, label='sat. dome')

    for label_suffix, states, color in [('', {'1': b01, '2': b02, '3': b03, '4': b04}, 'tab:blue'),
                                         ("'", {'1': c01, '2': c02, '3': c03, '4': c04}, 'tab:red')]:
        pts = {k: conn_Ts(v) for k, v in states.items()}
        ax.plot([pts['1'][1], pts['2'][1]], [pts['1'][0], pts['2'][0]], '-', color=color, lw=2)
        T23, s23 = isobar_Ts(states['2'].p.val, states['2'].h.val, states['3'].h.val)
        ax.plot(s23, T23, '-', color=color, lw=2)
        ax.plot([pts['3'][1], pts['4'][1]], [pts['3'][0], pts['4'][0]], '--', color=color, lw=2)
        T41, s41 = isobar_Ts(states['4'].p.val, states['4'].h.val, states['1'].h.val)
        ax.plot(s41, T41, '-', color=color, lw=2, label=f'{"LT" if label_suffix=="" else "HT"} loop')
        for k, (T, s) in pts.items():
            ax.plot(s, T, 'o', color=color, ms=5)
            ax.annotate(k + label_suffix, (s, T), textcoords='offset points', xytext=(6, 4))

    ax.set_xlabel('specific entropy in kJ/kg-K')
    ax.set_ylabel('temperature in degC')
    ax.set_title('Tabulated mixture two-loop system -- T-s diagram')
    ax.legend(loc='lower right')
    ax.grid(alpha=0.3)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output_dir / ('T_s.png' if len(fig.axes) == 1 else 'T_Q.png'), dpi=160)
    if not args.no_show:
        plt.show()
    else:
        plt.close(fig)


    # ---14b_T_Q_diagrams---
    def counter_current_profile(m_hot, fluid_hot, p_hot_in_bar, p_hot_out_bar, h_hot_in, h_hot_out,
                                 m_cold, fluid_cold, p_cold_in_bar, p_cold_out_bar, h_cold_in, h_cold_out,
                                 n=40):
        Q_total = m_cold * (h_cold_out - h_cold_in)  # kW
        Q = np.linspace(0, Q_total, n)
        h_cold = h_cold_in + Q / m_cold
        h_hot = h_hot_out + Q / m_hot
        p_cold = np.linspace(p_cold_in_bar, p_cold_out_bar, n) * 1e5
        p_hot = np.linspace(p_hot_out_bar, p_hot_in_bar, n) * 1e5
        T_cold = fluid_property('T', 'P', p_cold, 'H', h_cold * 1e3, fluid_cold) - 273.15
        T_hot = fluid_property('T', 'P', p_hot, 'H', h_hot * 1e3, fluid_hot) - 273.15
        return Q, T_hot, T_cold


    fig, axs = plt.subplots(2, 2, figsize=(11, 8.5))

    Q, Th, Tc = counter_current_profile(
        a02.m.val, 'water', a02.p.val, a03.p.val, a02.h.val, a03.h.val,
        b04.m.val, FLUID, b04.p.val, b01.p.val, b04.h.val, b01.h.val)
    axs[0, 0].plot(Q, Th, 'r-o', ms=3, label='geothermal water')
    axs[0, 0].plot(Q, Tc, 'b-o', ms=3, label=FLUID)
    axs[0, 0].set_title(f'LT evaporator (min approach = {(Th - Tc).min():.2f} K)')

    Q, Th, Tc = counter_current_profile(
        b02.m.val, FLUID, b02.p.val, b03.p.val, b02.h.val, b03.h.val,
        d01.m.val, 'water', d01.p.val, d02.p.val, d01.h.val, d02.h.val)
    axs[0, 1].plot(Q, Th, 'r-o', ms=3, label=FLUID)
    axs[0, 1].plot(Q, Tc, 'b-o', ms=3, label='district heating water')
    axs[0, 1].set_title(f'LT condenser (min approach = {(Th - Tc).min():.2f} K)')

    Q, Th, Tc = counter_current_profile(
        a01.m.val, 'water', a01.p.val, a02.p.val, a01.h.val, a02.h.val,
        c04.m.val, FLUID, c04.p.val, c01.p.val, c04.h.val, c01.h.val)
    axs[1, 0].plot(Q, Th, 'r-o', ms=3, label='geothermal water')
    axs[1, 0].plot(Q, Tc, 'b-o', ms=3, label=FLUID)
    axs[1, 0].set_title(f'HT evaporator (min approach = {(Th - Tc).min():.2f} K)')

    Q, Th, Tc = counter_current_profile(
        c02.m.val, FLUID, c02.p.val, c03.p.val, c02.h.val, c03.h.val,
        d02.m.val, 'water', d02.p.val, d03.p.val, d02.h.val, d03.h.val)
    axs[1, 1].plot(Q, Th, 'r-o', ms=3, label=FLUID)
    axs[1, 1].plot(Q, Tc, 'b-o', ms=3, label='district heating water')
    axs[1, 1].set_title(f'HT condenser (min approach = {(Th - Tc).min():.2f} K)')

    for ax in axs.flat:
        ax.set_xlabel('cumulative heat duty in kW')
        ax.set_ylabel('temperature in degC')
        ax.legend()
        ax.grid(alpha=0.3)

    plt.tight_layout()
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output_dir / ('T_s.png' if len(fig.axes) == 1 else 'T_Q.png'), dpi=160)
    if not args.no_show:
        plt.show()
    else:
        plt.close(fig)

    return result


# ---15_Batch_execution_and_summary_export---
def _run_table_worker(payload):
    """Run one independent mixture case in a separate process."""
    import contextlib
    import io
    import json
    import numpy as np
    import argparse
    import matplotlib
    matplotlib.use('Agg')
    table, mode, target_ua, pinch_k, plots, output_dir = payload
    buffer = io.StringIO()
    table_meta = {}
    try:
        with np.load(table, allow_pickle=False) as data:
            table_meta = json.loads(str(data['metadata']))
        case_args = argparse.Namespace(
            table=table, no_show=True,
            fixed_ua=target_ua if mode == 'fixed-ua' else None,
            target_pinch=pinch_k if mode == 'fixed-pinch' else None,
            plots=plots, output_dir=output_dir)
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            result = run_case(case_args)
        return dict(ok=True, result=result, metadata=table_meta,
                    log=buffer.getvalue(), error='')
    except Exception as exc:
        return dict(ok=False, result=None, metadata=table_meta,
                    log=buffer.getvalue(),
                    error=f'{type(exc).__name__}: {exc}')


def main():
    import contextlib
    import io
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mode', choices=['fixed-ua','fixed-temperature','fixed-pinch'], default='fixed-ua')
    parser.add_argument('--pinch-k', type=float, default=3.0,
                        help='Minimum exchanger temperature difference for fixed-pinch mode [K].')
    parser.add_argument('--table', type=Path, help='Optional single table filename.')
    parser.add_argument('--tables-dir', type=Path, default=Path('tables'))
    parser.add_argument('--summary', type=Path, default=None)
    parser.add_argument('--plots', dest='plots', action='store_true', default=True,
                        help='Save per-case plots to mixture_plots (default).')
    parser.add_argument('--no-plots', dest='plots', action='store_false',
                        help='Disable saving T-s and Q-T plots.')
    parser.add_argument('--output-dir', type=Path, default=Path('mixture_plots'))
    parser.add_argument('--workers', type=int, default=None,
                        help='Number of parallel worker processes (default: CPU cores - 1).')
    parser.add_argument('--no-show', action='store_true', help='Compatibility option; runs are always headless.')
    args = parser.parse_args()
    if args.workers is None:
        import os
        args.workers = max(1, (os.cpu_count() or 1) - 1)
    if args.workers < 1:
        parser.error('--workers must be at least 1')
    def relative(path):
        return path if path.is_absolute() else base / path
    tables_dir = relative(args.tables_dir)
    tables = [args.table if args.table.is_absolute() else tables_dir/args.table] if args.table else sorted(tables_dir.glob('*.npz'))
    if not tables:
        parser.error(f'No NPZ tables found in {tables_dir}')
    if args.mode == 'fixed-pinch' and args.pinch_k <= 0:
        parser.error('--pinch-k must be positive in fixed-pinch mode')
    default_summary = (
        'mixture_summary_fixed_ua.npz' if args.mode == 'fixed-ua' else
        'mixture_summary_pinch_%gK.npz' % args.pinch_k if args.mode == 'fixed-pinch' else
        'mixture_summary.npz'
    )
    destination = relative(args.summary or Path(default_summary))
    if destination.resolve() in [f.resolve() for f in tables]:
        parser.error('Summary output must not overwrite an input table.')
    # Every comparison includes the same pure-fluid design reference.
    print('Calculating R1233zd(E) reference at LT 8 K / HT 10 K superheat...', flush=True)
    reference_buffer=io.StringIO()
    with contextlib.redirect_stdout(reference_buffer), contextlib.redirect_stderr(reference_buffer):
        reference_result=run_case(argparse.Namespace(reference=True, fixed_ua=None,
            plots=args.plots, no_show=True,
            output_dir=relative(args.output_dir)/'reference_R1233zdE'))
    if not reference_result['passes_checks']:
        raise RuntimeError('Reference design failed physical checks.')
    reference_log=reference_buffer.getvalue()
    target_ua=reference_result['heat_exchangers'][:,1].copy()
    print(f'Reference UA [W/K]: {target_ua}; COP={reference_result["metrics"][0]:.4f}',flush=True)
    metric_names = ['cop_total','cop_lt','cop_ht','power_total_kw','power_lt_kw','power_ht_kw',
                    'heat_total_kw','heat_lt_kw','heat_ht_kw','source_lt_kw','source_ht_kw',
                    'mass_lt_kg_s','mass_ht_kg_s','mass_dh_kg_s','temperature_dh_intermediate_c','ua_total_w_k']
    shapes = dict(metrics=(16,),states=(16,6),heat_exchangers=(4,5),
                  tq_profiles=(4,200,3),ts_cycles=(2,4,100,2),
                  pinch_locations=(4,6),pressure_ratios=(2,),superheats=(2,))
    arrays = {key:np.full((len(tables),)+shape,np.nan) for key,shape in shapes.items()}
    status=[]; errors=[]; logs=[]; families=[]; compositions=[]; metadata=[]
    converged=[]; passes=[]; wet=[]; suction_wet=[]; cross=[]
    worker_payloads = [(table.resolve(), args.mode, target_ua, args.pinch_k,
                        args.plots, relative(args.output_dir)/table.stem)
                       for table in tables]
    if args.workers == 1:
        worker_results = [_run_table_worker(payload) for payload in worker_payloads]
    else:
        from concurrent.futures import ProcessPoolExecutor
        print(f'Running {len(tables)} cases with {args.workers} worker processes.', flush=True)
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            worker_results = list(executor.map(_run_table_worker, worker_payloads))

    for i, (table, case) in enumerate(zip(tables, worker_results)):
        print(f'[{i+1}/{len(tables)}] {table.name}', flush=True)
        families.append(table.stem.split('_mass_')[0])
        table_meta = case['metadata']
        values = table_meta.get('fractions', [])
        if not values and '_mass_' in table.stem:
            values = [float(v) for v in table.stem.split('_mass_')[1].split('_')]
        compositions.append(values)
        result = case['result']
        if case['ok']:
            for key in shapes:
                arrays[key][i] = result[key]
            converged.append(True)
            passes.append(result['passes_checks'])
            wet.append(result['wet_discharge'])
            suction_wet.append(result['wet_suction'])
            cross.append(result['temperature_crossover'])
            status.append('ok' if result['passes_checks'] else 'warning')
            errors.append('')
            print(f'  {status[-1]}: COP={result["metrics"][0]:.3f}', flush=True)
        else:
            converged.append(False); passes.append(False); wet.append(False); suction_wet.append(False); cross.append(False)
            status.append('failed'); errors.append(case['error'])
            print(f'  failed: {case["error"]}', flush=True)
        logs.append(case['log'])
        metadata.append(json.dumps(table_meta))
    max_components=max(2,max(map(len,compositions)))
    fractions=np.full((len(tables),max_components),np.nan)
    for i,values in enumerate(compositions):
        fractions[i,:len(values)]=values
    schema = {
        'schema_version':4, 'mode':args.mode, 'case_axis':'Every result array first dimension matches table_files.',
        'reference_note':'R1233zd(E), study superheat 8/10 K; original notebook uses 5/5 K.',
        'pressure_ratios_columns':['LT','HT'],
        'superheats_columns':['LT suction superheat K','HT suction superheat K'],
        'pinch_locations_columns':['pinch_k','q_fraction','q_at_pinch_kw','duty_kw','hot_temperature_c','cold_temperature_c'],
        'pinch_coordinate':'Heat-duty fraction from cold inlet/hot outlet; not physical length.',
        'failed_cases':'Numeric results are NaN; see status and errors. Check converged before interpreting flags.',
        'passes_checks':'Converged, finite exported states/metrics, solved states within table bounds, positive pinch, dry compressor discharge. Not a complete engineering validation.',
        'fractions':'Component order follows table family name; fraction basis is in table_metadata_json.',
        'states_columns':['mass_kg_s','pressure_bar','enthalpy_kj_kg','temperature_c','quality','entropy_kj_kg_k'],
        'heat_exchangers_columns':['heat_kw','ua_w_k','pinch_k','ttd_u_k','ttd_l_k'],
        'tq_profiles_columns':['heat_kw','hot_temperature_c','cold_temperature_c'],
        'ts_cycles_columns':['temperature_c','entropy_kj_kg_k'],
        'ts_cycles_axes':['case','loop LT/HT','segment 1-2/2-3/3-4/4-1','sample','property'],
        'ts_cycle_note':'Compression and expansion are straight endpoint illustrations, not resolved process paths.',
        'design':{'initial_evaporation_dew_c':[35,45],'initial_condensation_bubble_c':[80,95],
                  'superheat_k':[LT_SUPERHEAT_K,HT_SUPERHEAT_K],'subcooling_k':[3,5],'eta_s':0.75,
                  'geo_temperatures_c':[60,50,40],'geo_mass_kg_s':100,'dh_endpoints_c':[60,90],
                  'same_composition_both_loops':True,'fixed_ua':args.mode == 'fixed-ua',
                  'fixed_ua_released_variables':['LT evaporation pressure','HT evaporation pressure',
                                                 'LT suction superheat','HT suction superheat'],
                  'fixed_ua_fixed_variables':['LT condensation pressure','HT condensation pressure',
                                              'LT subcooling','HT subcooling'],
                  'fixed_pinch':args.mode == 'fixed-pinch',
                  'target_pinch_k':args.pinch_k if args.mode == 'fixed-pinch' else None}
    }
    destination.parent.mkdir(parents=True,exist_ok=True)
    reference_arrays = {}
    if reference_result is not None:
        reference_arrays = {'reference_'+key: reference_result[key] for key in shapes}
        reference_arrays['reference_ua_w_k'] = target_ua
        reference_arrays['reference_fluid'] = np.array('R1233zd(E)')
        reference_arrays['reference_run_log'] = np.array(reference_log)
    with destination.open('wb') as handle:
        np.savez_compressed(handle, **arrays, **reference_arrays, table_files=np.array([t.name for t in tables]),
            family=np.array(families), fractions=fractions, status=np.array(status),
            errors=np.array(errors), converged=np.array(converged), passes_checks=np.array(passes),
            wet_discharge=np.array(wet),wet_suction=np.array(suction_wet),
            temperature_crossover=np.array(cross),
            metric_names=np.array(metric_names),
            connection_labels=np.array(['a01','a02','a03','b01','b02','b03','b04','b05','c01','c02','c03','c04','c05','d01','d02','d03']),
            heat_exchanger_labels=np.array(['LT-evaporator','LT-condenser','HT-evaporator','HT-condenser']),
            table_metadata_json=np.array(metadata), run_logs=np.array(logs),
            schema_json=np.array(json.dumps(schema,indent=2)))
    print(f'Saved {destination}: {sum(converged)}/{len(tables)} completed; {sum(passes)} passed checks.')
    if args.plots:
        from plot_cop_comparison import plot_comparison
        plot_comparison(destination, relative(args.output_dir)/f'COP_mass_fraction_{args.mode}.png')


# ---Script_entry_point---
if __name__ == '__main__':
    main()
