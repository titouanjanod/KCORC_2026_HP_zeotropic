    
    
def overall(selected_fluid): 
    """1"""
    
    from tespy.networks import Network
    from tespy.components import (
        Source, Sink, Compressor, Valve, SectionedHeatExchanger, CycleCloser
    )
    from tespy.connections import Connection
    
    import numpy as np
    import matplotlib.pyplot as plt
    from CoolProp.CoolProp import PropsSI
    
    
    from tabular_mixture_wrapper import TabularMixtureWrapper
    
    """2"""
    
    
    nw = Network()
    nw.units.set_defaults(
        temperature='degC', pressure='bar', pressure_difference='bar',
        enthalpy='kJ/kg', mass_flow='kg/s', power='kW', heat='kW'
    )
    
    
    """3"""
    
    
    lt_cycle_closer = CycleCloser('LT-cycle-closer')
    
    lt_compressor = Compressor('LT-compressor')
    lt_condenser = SectionedHeatExchanger('LT-condenser')
    lt_expansion_valve = Valve('LT-expansion-valve')
    lt_evaporator = SectionedHeatExchanger('LT-evaporator')
    
    geothermal_source = Source('geothermal-source')   # placeholder: from HT-evaporator (45 degC)
    geothermal_sink = Sink('geothermal-sink')           # real: injection limit (30 degC)
    
    dh_source = Source('dh-source')        # real: DH return (60 degC)
    dh_sink = Sink('dh-sink')   # placeholder: to HT-condenser (75 degC)
    
    
    
    
    """4"""
    
    
    b01 = Connection(lt_cycle_closer, 'out1', lt_compressor, 'in1', label='b01')          # compressor suction
    b02 = Connection(lt_compressor, 'out1', lt_condenser, 'in1', label='b02')   # compressor discharge
    b03 = Connection(lt_condenser, 'out1', lt_expansion_valve, 'in1', label='b03')        # subcooled liquid
    b04 = Connection(lt_expansion_valve, 'out1', lt_evaporator, 'in2', label='b04')       # evaporator inlet
    b05 = Connection(lt_evaporator, 'out2', lt_cycle_closer, 'in1', label='b05')        # closes the cycle at state 1
    
    nw.add_conns(b01, b02, b03, b04, b05)
    
    
    
    
    
    
    """5"""
    
    
    a02 = Connection(geothermal_source, 'out1', lt_evaporator, 'in1', label='a02')
    a03 = Connection(lt_evaporator, 'out1', geothermal_sink, 'in1', label='a03')
    
    nw.add_conns(a02, a03)
    
    
    
    """6"""
    
    d01 = Connection(dh_source, 'out1', lt_condenser, 'in2', label='d01')
    d02 = Connection(lt_condenser, 'out2', dh_sink, 'in1', label='d02')
    
    nw.add_conns(d01, d02)
    
    
    """7"""
    
    
    
    FLUID = selected_fluid
    T_evap = 35       # degC, saturation temperature in the evaporator (5 K below the 40 degC injection limit)
    T_cond = 80       # degC, saturation temperature in the condenser
    superheat = 5     # K, suction superheat (dry-compression margin)
    subcool = 3        # K, liquid subcooling ahead of the expansion valve
    
    p_evap = PropsSI('P', 'T', T_evap + 273.15, 'Q', 1, FLUID) / 1e5   # bar
    p_cond = PropsSI('P', 'T', T_cond + 273.15, 'Q', 0, FLUID) / 1e5   # bar
    
    print(f'p_evap = {p_evap:.3f} bar, p_cond = {p_cond:.3f} bar, pr = {p_cond / p_evap:.2f}')
    
    
    
    
    """8"""
    
    lt_evaporator.set_attr(pr1=1, pr2=1)   # no pressure drop assumed on either side
    
    a02.set_attr(fluid={'water': 1}, T=50, p=5, m=100)   # LT's own geothermal segment: 50 -> 40 degC
    a03.set_attr(T=40)                                   # real: injection limit
    
    
    
    """9"""
    
    
    lt_condenser.set_attr(pr1=1, pr2=1)   # no pressure drop assumed on either side
    
    d01.set_attr(fluid={'water': 1}, T=60, p=5)   # real: district heating return -- mass flow left FREE (result)
    d02.set_attr(T=75)                            # placeholder outlet (-> HT-condenser)
    
    
    
    
    
    """10"""
    
    
    lt_compressor.set_attr(eta_s=0.75)
    
    
    
    """ here fixing fluid properties """
    
    if selected_fluid == 'R1233zd(E)':
    
        b01.set_attr(fluid = {'R1233zd(E)':1})
    else :
        b01.set_attr(
        fluid={"MyMixture": 1},
        fluid_engines={"MyMixture": TabularMixtureWrapper},
        fluid_wrapper_kwargs={
            "MyMixture": {"path": "selected_fluid.npz"}
        })
    
    
    
    b01.set_attr(p=p_evap, td_dew=superheat)   # mass flow left FREE (result)
    b02.set_attr(p=p_cond)
    b03.set_attr(td_bubble=subcool)
    
    
    
    """11"""
    
    nw.solve('design')
    nw.print_results()
    
    
    
    """12"""
    
    print('Refrigerant (R1233zd(E)) mass flow rate:', round(b01.m.val, 3), 'kg/s')
    print('District-heating mass flow rate (RESULT):', round(d01.m.val, 2), 'kg/s')
    print()
    print(f"{'Component':<15}{'ttd_u [K]':>12}{'ttd_l [K]':>12}")
    for hx in [lt_evaporator, lt_condenser]:
        flag_u = '  <-- violation!' if hx.ttd_u.val < 0 else ''
        flag_l = '  <-- violation!' if hx.ttd_l.val < 0 else ''
        print(f"{hx.label:<15}{hx.ttd_u.val:>12.2f}{hx.ttd_l.val:>12.2f}"
              f"{flag_u if hx.ttd_u.val < 0 else flag_l}")
    
    if b02.x.val < 1:
        print()
        print(f'NOTE: compressor discharge quality x = {b02.x.val:.3f} (< 1) -- wet compression. '
              'Increase `superheat` in Section 7 and re-run from there.')
    else:
        print()
        print(f'Discharge is dry (T={b02.T.val:.1f} degC vs. T_cond={T_cond} degC, '
              f'{b02.T.val - T_cond:.1f} K of superheat at the outlet).')
    
    
    
    
    """13"""
    
    P_comp = lt_compressor.P.val
    Q_evap = lt_evaporator.Q.val
    Q_cond = lt_condenser.Q.val
    
    Q_useful = -Q_cond   # kW, heat delivered to the district-heating intermediate stream
    COP = Q_useful / P_comp
    pr = b02.p.val / b01.p.val
    
    print('================ LT LOOP SUMMARY ================')
    print(f'Refrigerant                  : {FLUID}')
    print(f'Refrigerant mass flow rate   : {b01.m.val:8.2f} kg/s')
    print(f'Pressure ratio                : {pr:8.2f}')
    print(f'Isentropic efficiency         : {lt_compressor.eta_s.val * 100:8.2f} %')
    print(f'Compressor discharge temp.    : {b02.T.val:8.1f} degC')
    print(f'Compressor power              : {P_comp:8.1f} kW')
    print(f'Evaporator duty               : {-Q_evap:8.1f} kW')
    print(f'Condenser duty                : {Q_useful:8.1f} kW')
    print(f'COP (LT loop only)            : {COP:8.2f}')
    
    
    
    
    
    """14 : T s diagram"""
    
    
    def conn_Ts(conn):
        p_Pa = conn.p.val * 1e5
        h_Jkg = conn.h.val * 1e3
        T = PropsSI('T', 'P', p_Pa, 'H', h_Jkg, FLUID) - 273.15
        s = PropsSI('S', 'P', p_Pa, 'H', h_Jkg, FLUID) / 1e3
        return T, s
    
    
    def isobar_Ts(p_bar, h1_kJkg, h2_kJkg, n=40):
        p_Pa = p_bar * 1e5
        hs = np.linspace(h1_kJkg, h2_kJkg, n) * 1e3
        T = PropsSI('T', 'P', p_Pa, 'H', hs, FLUID) - 273.15
        s = PropsSI('S', 'P', p_Pa, 'H', hs, FLUID) / 1e3
        return T, s
    
    
    T_crit = PropsSI('Tcrit', FLUID)
    T_dome = np.linspace(280, T_crit - 0.3, 200)
    sf = PropsSI('S', 'T', T_dome, 'Q', 0, FLUID) / 1e3
    sg = PropsSI('S', 'T', T_dome, 'Q', 1, FLUID) / 1e3
    T_dome_C = T_dome - 273.15
    
    fig, ax = plt.subplots(figsize=(7, 5.5))
    ax.plot(np.concatenate([sf, sg[::-1]]), np.concatenate([T_dome_C, T_dome_C[::-1]]),
            'k-', lw=1, label='sat. dome')
    
    states = {'1': b01, '2': b02, '3': b03, '4': b04}
    pts = {k: conn_Ts(v) for k, v in states.items()}
    
    ax.plot([pts['1'][1], pts['2'][1]], [pts['1'][0], pts['2'][0]], 'r-', lw=2, label='compressor')
    T23, s23 = isobar_Ts(b02.p.val, b02.h.val, b03.h.val)
    ax.plot(s23, T23, 'orange', lw=2, label='condenser')
    ax.plot([pts['3'][1], pts['4'][1]], [pts['3'][0], pts['4'][0]], 'g--', lw=2, label='expansion valve')
    T41, s41 = isobar_Ts(b04.p.val, b04.h.val, b01.h.val)
    ax.plot(s41, T41, 'b-', lw=2, label='evaporator')
    
    for k, (T, s) in pts.items():
        ax.plot(s, T, 'ko', ms=5)
        ax.annotate(k, (s, T), textcoords='offset points', xytext=(6, 4))
    
    ax.set_xlabel('specific entropy in kJ/kg-K')
    ax.set_ylabel('temperature in degC')
    ax.set_title('LT loop (R1233zd(E)) -- T-s diagram')
    ax.legend(loc='lower right')
    ax.grid(alpha=0.3)
    plt.show()
    
    
    
    
    """14 bis : T-Q diagram"""
    
    def counter_current_profile(m_hot, fluid_hot, p_hot_in_bar, p_hot_out_bar, h_hot_in, h_hot_out,
                                 m_cold, fluid_cold, p_cold_in_bar, p_cold_out_bar, h_cold_in, h_cold_out,
                                 n=40):
        Q_total = m_cold * (h_cold_out - h_cold_in)  # kW
        Q = np.linspace(0, Q_total, n)
        h_cold = h_cold_in + Q / m_cold
        h_hot = h_hot_out + Q / m_hot
        p_cold = np.linspace(p_cold_in_bar, p_cold_out_bar, n) * 1e5
        p_hot = np.linspace(p_hot_out_bar, p_hot_in_bar, n) * 1e5
        T_cold = PropsSI('T', 'P', p_cold, 'H', h_cold * 1e3, fluid_cold) - 273.15
        T_hot = PropsSI('T', 'P', p_hot, 'H', h_hot * 1e3, fluid_hot) - 273.15
        return Q, T_hot, T_cold
    
    
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.5))
    
    Q, Th, Tc = counter_current_profile(
        a02.m.val, 'water', a02.p.val, a03.p.val, a02.h.val, a03.h.val,
        b04.m.val, FLUID, b04.p.val, b01.p.val, b04.h.val, b01.h.val)
    axs[0].plot(Q, Th, 'r-o', ms=3, label='geothermal water')
    axs[0].plot(Q, Tc, 'b-o', ms=3, label=FLUID)
    axs[0].set_title(f'Evaporator (min approach = {(Th - Tc).min():.2f} K)')
    axs[0].set_xlabel('cumulative heat duty in kW')
    axs[0].set_ylabel('temperature in degC')
    axs[0].legend()
    axs[0].grid(alpha=0.3)
    
    Q, Th, Tc = counter_current_profile(
        b02.m.val, FLUID, b02.p.val, b03.p.val, b02.h.val, b03.h.val,
        d01.m.val, 'water', d01.p.val, d02.p.val, d01.h.val, d02.h.val)
    axs[1].plot(Q, Th, 'r-o', ms=3, label=FLUID)
    axs[1].plot(Q, Tc, 'b-o', ms=3, label='district heating water')
    axs[1].set_title(f'Condenser (min approach = {(Th - Tc).min():.2f} K)')
    axs[1].set_xlabel('cumulative heat duty in kW')
    axs[1].set_ylabel('temperature in degC')
    axs[1].legend()
    axs[1].grid(alpha=0.3)
    
    plt.tight_layout()
    plt.show()

    UA_ev = lt_evaporator.UA.val
    
    UA_cd = lt_condenser.UA.val


    return nw, COP, UA_ev, UA_cd