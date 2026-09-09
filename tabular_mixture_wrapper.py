# -*- coding: utf-8 -*-
"""Runtime fluid property wrapper for exported mixture tables.

Loads an npz file created by export_mixture_tables.py and implements the
TESPy :code:`FluidPropertyWrapper` interface on top of spline interpolation,
so fixed-composition zeotropic mixtures can be used without REFPROP.

Usage on a connection:

    conn.set_attr(
        fluid={"MyMixture": 1},
        fluid_engines={"MyMixture": TabularMixtureWrapper},
        fluid_wrapper_kwargs={
            "MyMixture": {"path": "Isopentane_Isobutane_mass_0.50_0.50.npz"}
        }
    )

Interpolation layout follows the export: cubic splines in log(p) along the
saturation lines and region edges, bicubic splines over (log p, sigma) per
region, density interpolated as specific volume. Inverse calls (h_pT, h_ps,
T_ps, h_pQ, p_sat_TQ) are 1-D root searches on the splines, which stay
monotone in the search variable. Between p_sat_max and p_crit the saturation
splines are evaluated in (mild) extrapolation for the phase decision,
mirroring CoolPropWrapper.phase_ph.

sigma is the boundary-fitted enthalpy coordinate of the tables: enthalpy
normalized to the region's enthalpy window at the given pressure (e.g.
:code:`(h - h_bubble(p)) / (h_dew(p) - h_bubble(p))` in the two-phase
region), so phase boundaries are grid lines and no interpolation cell
straddles the dome. The region edge splines stored with the tables define
this coordinate transform; every (p, h) lookup first locates the region and
computes sigma from the edges, then evaluates the bicubic spline at
(log p, sigma). In the two-phase region sigma is the linear-in-enthalpy
pseudo-quality - equal to the thermodynamic quality only for pure fluids,
which is why the true zeotropic quality Q comes from its own table. See the
module docstring of export_mixture_tables.py for background and lineage of
the approach.

Transport properties are not tabulated and raise NotImplementedError.
"""

import json

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.interpolate import RectBivariateSpline
from scipy.optimize import brentq

from tespy.tools.fluid_properties.wrappers import FluidPropertyWrapper
from tespy.tools.fluid_properties.wrappers import wrapper_registry

SAT_KEYS = [
    "T_bubble", "T_dew", "h_bubble", "h_dew", "s_bubble", "s_dew",
    "d_bubble", "d_dew", "h_liquid_min", "h_vapor_max"
]


@wrapper_registry
class TabularMixtureWrapper(FluidPropertyWrapper):

    def __init__(self, fluid, back_end=None, **kwargs):
        """Wrapper for tabulated fixed-composition mixture data

        Parameters
        ----------
        fluid : str
            Name of the fluid (label only, data comes from the file).
        back_end : str, optional
            Unused, kept for interface compatibility.
        path : str
            Path to the npz file created by export_mixture_tables.py.
        """
        super().__init__(fluid, back_end)

        path = kwargs.get("path")
        if path is None:
            msg = (
                f"The {self.__class__.__name__} requires the 'path' keyword "
                "pointing to an npz table file."
            )
            raise KeyError(msg)
        self.path = path

        data = np.load(path)
        meta = json.loads(str(data["metadata"]))
        self.mixture_type = meta["mixture_type"]
        self.fractions = meta["fractions"]
        self._molar_mass = meta["molar_mass"]
        self._T_crit = meta["T_crit"]
        self._p_crit = meta["p_crit"]
        self._T_min = meta["T_min"]
        self._T_max = meta["T_max"]
        self._p_min = meta["p_min"]
        self._p_max = meta["p_max"]
        self._p_sat_max = meta["p_sat_max"]

        for key in data.files:
            if key != "metadata" and np.isnan(data[key]).any():
                msg = (
                    f"Table '{key}' in {path} contains failed grid points, "
                    "regenerate the file with adjusted limits."
                )
                raise ValueError(msg)

        logp = np.log(data["p"])
        sigma = data["sigma"]
        self._sat = {
            key: CubicSpline(logp, data[f"sat_{key}"]) for key in SAT_KEYS
        }
        self._logp_bubble = CubicSpline(data["sat_T_bubble"], logp)
        self._logp_dew = CubicSpline(data["sat_T_dew"], logp)

        self._tables = {}
        for region in ["liquid", "twophase", "vapor"]:
            self._tables[region] = {
                "T": RectBivariateSpline(logp, sigma, data[f"{region}_T"]),
                "s": RectBivariateSpline(logp, sigma, data[f"{region}_s"]),
                "v": RectBivariateSpline(logp, sigma, 1 / data[f"{region}_d"]),
            }
        self._tables["twophase"]["Q"] = RectBivariateSpline(
            logp, sigma, data["twophase_Q"]
        )

        logp_sc = np.log(data["sc_p"])
        self._sc_h_min = CubicSpline(logp_sc, data["sc_h_min"])
        self._sc_h_max = CubicSpline(logp_sc, data["sc_h_max"])
        self._tables["supercritical"] = {
            "T": RectBivariateSpline(logp_sc, data["sc_sigma"], data["sc_T"]),
            "s": RectBivariateSpline(logp_sc, data["sc_sigma"], data["sc_s"]),
            "v": RectBivariateSpline(logp_sc, data["sc_sigma"], 1 / data["sc_d"]),
        }

        self._edges = {
            "liquid": (self._sat["h_liquid_min"], self._sat["h_bubble"]),
            "twophase": (self._sat["h_bubble"], self._sat["h_dew"]),
            "vapor": (self._sat["h_dew"], self._sat["h_vapor_max"]),
            "supercritical": (self._sc_h_min, self._sc_h_max),
        }

    def _locate(self, p, h):
        logp = np.log(p)
        if p > self._p_sat_max:
            region = "supercritical"
        elif h <= self._sat["h_bubble"](logp):
            region = "liquid"
        elif h >= self._sat["h_dew"](logp):
            region = "vapor"
        else:
            region = "twophase"

        h_lo, h_hi = self._edges[region]
        sg = (h - h_lo(logp)) / (h_hi(logp) - h_lo(logp))
        return region, logp, float(sg)

    def _h_bounds(self, p):
        logp = np.log(p)
        if p > self._p_sat_max:
            return float(self._sc_h_min(logp)), float(self._sc_h_max(logp))
        return (
            float(self._sat["h_liquid_min"](logp)),
            float(self._sat["h_vapor_max"](logp))
        )

    def _is_below_T_critical(self, T):
        return T < self._T_crit

    def get_T_max(self, p):
        return self._T_max

    def isentropic(self, p_1, h_1, p_2):
        return self.h_ps(p_2, self.s_ph(p_1, h_1))

    def T_ph(self, p, h):
        region, logp, sg = self._locate(p, h)
        return self._tables[region]["T"].ev(logp, sg).item()

    def s_ph(self, p, h):
        region, logp, sg = self._locate(p, h)
        return self._tables[region]["s"].ev(logp, sg).item()

    def d_ph(self, p, h):
        region, logp, sg = self._locate(p, h)
        return 1 / self._tables[region]["v"].ev(logp, sg).item()

    def Q_ph(self, p, h):
        region, logp, sg = self._locate(p, h)
        if region == "twophase":
            return np.clip(
                self._tables["twophase"]["Q"].ev(logp, sg), 0, 1
            ).item()
        elif region == "liquid":
            return 0
        elif region == "vapor":
            return 1
        else:
            return -1

    def phase_ph(self, p, h):
        if p >= self._p_crit:
            if self.T_ph(p, h) >= self._T_crit:
                return "sc"
            else:
                return "l"
        logp = np.log(p)
        if h <= self._sat["h_bubble"](logp):
            return "l"
        elif h >= self._sat["h_dew"](logp):
            return "g"
        else:
            return "tp"

    def h_pT(self, p, T):
        h_lo, h_hi = self._h_bounds(p)
        return brentq(lambda h: self.T_ph(p, h) - T, h_lo, h_hi)

    def h_ps(self, p, s):
        h_lo, h_hi = self._h_bounds(p)
        return brentq(lambda h: self.s_ph(p, h) - s, h_lo, h_hi)

    def T_ps(self, p, s):
        return self.T_ph(p, self.h_ps(p, s))

    def h_pQ(self, p, Q):
        if p > self._p_sat_max:
            msg = f"No saturation data above p={self._p_sat_max} Pa."
            raise ValueError(msg)
        logp = np.log(p)
        if Q <= 0:
            return float(self._sat["h_bubble"](logp))
        elif Q >= 1:
            return float(self._sat["h_dew"](logp))
        table = self._tables["twophase"]["Q"]
        sg = brentq(lambda sg: table.ev(logp, sg).item() - Q, 0, 1)
        h_b = float(self._sat["h_bubble"](logp))
        h_d = float(self._sat["h_dew"](logp))
        return h_b + sg * (h_d - h_b)

    def T_sat(self, p):
        return self.T_bubble(p)

    def T_dew(self, p):
        return float(self._sat["T_dew"](np.log(p)))

    def T_bubble(self, p):
        return float(self._sat["T_bubble"](np.log(p)))

    def p_sat(self, T):
        return self.p_sat_TQ(T, 0.5)

    def p_dew(self, T):
        return float(np.exp(self._logp_dew(T)))

    def p_bubble(self, T):
        return float(np.exp(self._logp_bubble(T)))

    def _Q_pT(self, logp, T):
        table = self._tables["twophase"]["T"]

        def residual(sg):
            return table.ev(logp, sg).item() - T

        # spline round-off can push the residual marginally past zero at the
        # dome edges, which would break the bracket of the outer root search
        # in p_sat_TQ
        if residual(0) >= 0:
            return 0.0
        elif residual(1) <= 0:
            return 1.0
        sg = brentq(residual, 0, 1)
        return self._tables["twophase"]["Q"].ev(logp, sg).item()

    def p_sat_TQ(self, T, Q):
        if Q <= 0:
            return self.p_bubble(T)
        elif Q >= 1:
            return self.p_dew(T)
        logp = brentq(
            lambda logp: self._Q_pT(logp, T) - Q,
            float(self._logp_dew(T)),
            float(self._logp_bubble(T))
        )
        return float(np.exp(logp))

    def h_QT(self, Q, T):
        return self.h_pQ(self.p_sat_TQ(T, Q), Q)

    def s_QT(self, Q, T):
        p = self.p_sat_TQ(T, Q)
        return self.s_ph(p, self.h_pQ(p, Q))

    def d_QT(self, Q, T):
        p = self.p_sat_TQ(T, Q)
        return self.d_ph(p, self.h_pQ(p, Q))

    def d_pT(self, p, T):
        return self.d_ph(p, self.h_pT(p, T))

    def s_pT(self, p, T):
        return self.s_ph(p, self.h_pT(p, T))
