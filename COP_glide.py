# -*- coding: utf-8 -*-
"""
Created on Fri Sep 11 09:32:04 2026

@author: titouanjanod
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from tabular_mixture_wrapper import TabularMixtureWrapper

# ==========================================================
# CONTROLLERS
# ==========================================================
lw = 6
ms = 12

fs = 40
fs_ticks = 20

# cop_color   = "k"
glide_color = "#D55E00"

p_evap = 8.673e-01 * 1e5
p_cond = 2.875 *1e5

# ==========================================================
# READ CSV
# ==========================================================
df = pd.read_csv("pinch_to_UA.csv")

# ==========================================================
# KEEP ONLY CYCLOPEN_BUTANE
# ==========================================================
df = df[df["Fluid"].str.contains("CYCLOPEN_BUTANE")].copy()

# mass fraction
df["x1"] = [
    float(name.split("_mass_")[1].split("_")[0])
    for name in df["Fluid"]
]

df = df.sort_values("x1")

# ==========================================================
# CALCULATE GLIDE
# ==========================================================
glides_ev = []
glides_cd= []

for fluid_name in df["Fluid"]:

    wrapper = TabularMixtureWrapper(
        fluid=fluid_name,path=f"tables/{fluid_name}.npz"
    )

    # pressure level of your HTHP evaporator
    
    glide_ev = wrapper.T_dew(p_evap) - wrapper.T_bubble(p_evap)

    glide_cd = wrapper.T_dew(p_cond) - wrapper.T_bubble(p_cond)
    
    glides_ev.append(glide_ev)
    glides_cd.append(glide_cd)
    
df["Glide_ev"] = glides_ev

df["Glide_cd"] = glides_cd

# ==========================================================
# FIGURE
# ==========================================================
fig, ax1 = plt.subplots(figsize=(10,7))

# ----------------------------------------------------------
# COP
# ----------------------------------------------------------
ax1.plot(
    df["x1"],
    df["COP"],
    "-o",
    lw=lw,
    ms=ms,
    color="k"
)

ax1.set_xlabel(
    r"$x_1$ [-]",
    fontsize=fs
)

ax1.set_ylabel(
    r"$COP$",
    fontsize=fs,
    color="k"
)

ax1.tick_params(
    axis="y",
    colors="k",
    labelsize=fs_ticks
)

ax1.tick_params(
    axis="x",
    labelsize=fs_ticks
)

ax1.spines["left"].set_color("k")

# ----------------------------------------------------------
# GLIDE
# ----------------------------------------------------------
ax2 = ax1.twinx()

ax2.plot(
    df["x1"],
    df["Glide_ev"],
    "-s",
    lw=lw,
    ms=ms,
    color=glide_color,
    label = "$glide_{ev}$"
)

ax2.plot(
    df["x1"],
    df["Glide_cd"],
    "-s",
    lw=lw,
    ms=ms,
    color="purple",
    label = "$glide_{cd}$"
)

ax2.set_ylabel(
    r"$Glide$ [$K$]",
    fontsize=fs,
    color=glide_color
)

ax2.tick_params(
    axis="y",
    colors=glide_color,
    labelsize=fs_ticks
)

ax2.legend(fontsize = 25, loc = "best")

ax2.spines["right"].set_color(glide_color)




# ----------------------------------------------------------
# GRID
# ----------------------------------------------------------
ax1.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()
