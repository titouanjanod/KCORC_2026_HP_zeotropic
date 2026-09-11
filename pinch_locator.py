"""Locate the true temperature pinch along constant-pressure counterflow exchangers.

The coordinate q_fraction is cumulative heat duty / total duty, measured from
the cold inlet/hot outlet. It is NOT a fraction of physical exchanger length.
End points, refrigerant bubble/dew boundaries and smooth internal minima are
checked. Requires the zero-pressure-drop assumption of the heat-pump model.
"""
import numpy as np
from scipy.optimize import minimize_scalar
from CoolProp.CoolProp import PropsSI

HX_CONNECTIONS = [
    ("a02","a03","b04","b01","water","refrigerant"),
    ("b02","b03","d01","d02","refrigerant","water"),
    ("a01","a02","c04","c01","water","refrigerant"),
    ("c02","c03","d02","d03","refrigerant","water"),
]


def locate_pinch(states, labels, wrapper, points=301):
    """Return (4,6) numeric results and four descriptions; states use summary units."""
    result, descriptions = [], []
    lookup = dict(zip(labels, states))
    for hi,ho,ci,co,hf,cf in HX_CONNECTIONS:
        hot_in,hot_out,cold_in,cold_out = [lookup[k] for k in (hi,ho,ci,co)]
        for inlet,outlet in [(hot_in,hot_out),(cold_in,cold_out)]:
            if not np.isclose(inlet[1],outlet[1],rtol=1e-9,atol=1e-8):
                raise ValueError("Pinch locator requires constant pressure.")
        duty = cold_in[0]*(cold_out[2]-cold_in[2])
        if duty <= 0:
            raise ValueError("Non-positive exchanger duty.")
        np.testing.assert_allclose(duty, hot_in[0]*(hot_in[2]-hot_out[2]),rtol=1e-7,atol=1e-4)
        boundaries = [(0., "cold inlet / hot outlet"),(1., "cold outlet / hot inlet")]
        for state,fluid,side in [(hot_out,hf,"hot"),(cold_in,cf,"cold")]:
            if fluid == "refrigerant":
                for quality,phase in [(0,"bubble"),(1,"dew")]:
                    h = wrapper.h_pQ(state[1]*1e5,quality)/1e3
                    u = state[0]*(h-state[2])/duty
                    if 0 <= u <= 1:
                        boundaries.append((float(u),f"{side} refrigerant {phase} boundary"))
        def temp(u,state,fluid):
            h=(state[2]+u*duty/state[0])*1e3
            p=state[1]*1e5
            if fluid == "water":
                return float(PropsSI("T","P",p,"H",h,"water"))-273.15
            # Prevent silently clamped table extrapolation in postprocessing.
            if hasattr(wrapper,"_locate"):
                region,lp,sigma=wrapper._locate(p,h)
                if not wrapper._p_min <= p <= wrapper._p_max or not -1e-7 <= sigma <= 1+1e-7:
                    raise ValueError("Pinch search outside property table.")
            return float(wrapper.T_ph(p,h))-273.15
        def gap(u):
            return temp(u,hot_out,hf)-temp(u,cold_in,cf)
        grid = np.unique(np.r_[np.linspace(0,1,points),[u for u,_ in boundaries]])
        values = np.array([gap(u) for u in grid])
        candidates = [(float(v),float(u)) for u,v in zip(grid,values)]
        for i in range(1,len(grid)-1):
            if values[i] <= values[i-1] and values[i] <= values[i+1]:
                opt = minimize_scalar(gap,bounds=(grid[i-1],grid[i+1]),method="bounded",
                                      options={"xatol":1e-11})
                if opt.success:
                    candidates.append((float(opt.fun),float(opt.x)))
        delta,u = min(candidates)
        description = "internal smooth minimum"
        for ub,label in boundaries:
            if abs(u-ub)<1e-6:
                description=label
                break
        result.append([delta,u,u*duty,duty,temp(u,hot_out,hf),temp(u,cold_in,cf)])
        descriptions.append(description)
    return np.array(result),np.array(descriptions)


COLUMNS = ["pinch_k","q_fraction","q_at_pinch_kw","duty_kw","hot_temperature_c","cold_temperature_c"]
