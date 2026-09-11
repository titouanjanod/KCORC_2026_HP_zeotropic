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

cop_color   = "#0072B2"
glide_color = "#D55E00"

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
glides = []

for fluid_name in df["Fluid"]:

    wrapper = TabularMixtureWrapper(
        fluid=fluid_name,path=f"tables/{fluid_name}.npz"
    )

    # pressure level of your HTHP evaporator
    p = wrapper.p_dew(40 + 273.15)

    glide = wrapper.T_dew(p) - wrapper.T_bubble(p)

    glides.append(glide)

df["Glide"] = glides

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
    color=cop_color
)

ax1.set_xlabel(
    r"$x_1$ [-]",
    fontsize=fs
)

ax1.set_ylabel(
    r"$COP$",
    fontsize=fs,
    color=cop_color
)

ax1.tick_params(
    axis="y",
    colors=cop_color,
    labelsize=fs_ticks
)

ax1.tick_params(
    axis="x",
    labelsize=fs_ticks
)

ax1.spines["left"].set_color(cop_color)

# ----------------------------------------------------------
# GLIDE
# ----------------------------------------------------------
ax2 = ax1.twinx()

ax2.plot(
    df["x1"],
    df["Glide"],
    "-s",
    lw=lw,
    ms=ms,
    color=glide_color
)

ax2.set_ylabel(
    r"$Glide$ [$^\circ$C]",
    fontsize=fs,
    color=glide_color
)

ax2.tick_params(
    axis="y",
    colors=glide_color,
    labelsize=fs_ticks
)

ax2.spines["right"].set_color(glide_color)

# ----------------------------------------------------------
# GRID
# ----------------------------------------------------------
ax1.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()
