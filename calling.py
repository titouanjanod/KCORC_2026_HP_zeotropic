# -*- coding: utf-8 -*-
"""
Created on Wed Sep  9 16:04:46 2026

@author: titouanjanod
"""

from overall_modelling_woIA import overall

import matplotlib.pyplot as plt

import pandas as pd

import numpy as np

from pathlib import Path

tables_folder = Path("tables")
npz_file_names = [
    file.stem
    for file in tables_folder.glob("*.npz")
    if file.is_file()
]


# print(npz_file_names)


# selected_fluid = 'R1233zd(E)'
selected_fluid = 'CYCLOPEN_BUTANE_mass_0.85_0.15'

COP = np.zeros(len(npz_file_names))
UA_ev = np.zeros(len(npz_file_names))
UA_cd  = np.zeros(len(npz_file_names))
pinch_ev = np.zeros(len(npz_file_names))
pinch_cd = np.zeros(len(npz_file_names))

mode = "pinch_in" # "pinch_in" or "UA_in" or "base"
results_name = "UA_to_pinch"

pinches = {"pinch_ev" : 5,
           "pinch_cd" : 5}

nw_1, COP_1, UA_ev_1, UA_cd_1, pinch_ev_1, pinch_cd_1 = overall(selected_fluid, mode, pinches, plots=True)

UAs = {"UA_ev": 460976.8631329016,
       "UA_cd": 492569.33126388316}
# nw_2, COP_2, UA_ev_2, UA_cd_2, pinch_ev_2, pinch_cd_2 = overall(selected_fluid, mode, UAs = UAs)


""" Pinch based"""

# mode = "pinch_in"
# for i, one_fluid in enumerate(npz_file_names) :
    
#     _, COP[i], UA_ev[i], UA_cd[i], pinch_ev[i], pinch_cd[i]  = overall(one_fluid, mode, pinches)
    
# df = pd.DataFrame({ "Fluid":npz_file_names, 
#                    "COP":COP, 
#                    "UA_ev" :UA_ev, 
#                    "UA_cd":UA_cd})


""" UA based """

# mode = "UA_in"

# for i, one_fluid in enumerate(npz_file_names) :
    
#     _, COP[i], UA_ev[i], UA_cd[i], pinch_ev[i], pinch_cd[i] = overall(one_fluid, mode, UAs = UAs)
    
# df = pd.DataFrame({ "Fluid":npz_file_names, 
#                    "COP":COP, 
#                    "UA_ev" :UA_ev, 
#                    "UA_cd":UA_cd,
#                    "pinch_ev": pinch_ev,
#                    "pinch_cd":pinch_cd})

#%%

# df.to_csv(f"{results_name}.csv", index=False)

#%%





# ==========================================================
# PLOT CONTROLLERS
# ==========================================================
lw = 5            # line width
ms = 10           # marker size
fs = 40           # font size
fs_ticks = 20
alpha = 0.9
figsize = (10, 7)

# ==========================================================
# EXTRACT MIXTURE FAMILY & MASS FRACTION
# ==========================================================
df_plot = df.copy()

families = []
mass_frac = []

for name in df_plot["Fluid"]:

    # Everything before "_mass_"
    family = name.split("_mass_")[0]

    # First mass fraction after "_mass_"
    z1 = float(name.split("_mass_")[1].split("_")[0])

    families.append(family)
    mass_frac.append(z1)

df_plot["Family"] = families
df_plot["MassFraction"] = mass_frac

ylabel_dict = {
    "COP": r"$COP$",
    "UA_ev": r"$UA_{ev}$",
    "UA_cd": r"$UA_{cd}$",
    "pinch_ev": r"$\Delta T_{pp,ev}$",
    "pinch_cd": r"$\Delta T_{pp,cd}$"
}


# ==========================================================
# COLORS
# ==========================================================
# colors = {
#     "CYCLOPEN_BUTANE": "tab:blue",
#     "CYCLOPEN_R1233ZDE3" : "tab:yellow",
#     "Isopentane_Isobutane": "tab:red",
#     "PENTANE_R1336MZZE": "tab:green",
#     "R1224YDZ_R1234ZEE": "tab:orange",
#     "R1336MZZZ_R1336MZZE": "tab:purple",
# }
colors = {
    "CYCLOPEN_BUTANE"      : "#0072B2",  # bleu
    "CYCLOPEN_R1233ZDE"    : "#D55E00",  # vermillon
    "CYCLOPEN_R1336MZZZ"   : "#009E73",  # vert
    "Isopentane_Isobutane" : "#CC79A7",  # magenta
    "PENTANE_R1336MZZE"    : "#E69F00",  # orange
    "R1224YDZ_R1234ZEE"    : "#56B4E9",  # cyan
    "R1336MZZZ_R1336MZZE"  : "#000000",  # noir
}
# ==========================================================
# CREATE 3 SUBPLOTS
# ==========================================================
fig, axes = plt.subplots(1, 3, figsize=(20, 7), sharex=True)

if mode == 'pinch_in':
    variables = ["COP", "UA_ev", "UA_cd"]
if mode == 'UA_in' :
    variables = ["COP", "pinch_ev", "pinch_cd"]

for ax, var in zip(axes, variables):

    for family in df_plot["Family"].unique():

        sub = df_plot[df_plot["Family"] == family].sort_values("MassFraction")

        ax.plot(
            sub["MassFraction"],
            sub[var],
            '-o',
            lw=lw,
            ms=ms,
            color=colors.get(family, None),
            alpha=alpha,
            label=family
        )

    # ax.set_ylabel(var, fontsize=fs)
    ax.grid(True, alpha=0.3)

# ==========================================================
# FINAL FORMATTING
# ==========================================================
axes[1].set_xlabel("Mass fraction of first component [-]", fontsize=fs)
axes[1].set_xlabel(
    r"$x_1$ [-]",
    fontsize=fs)

# axes_len = [0,1,2]
# for i in axes_len:
#     print(i)
#     axes[i].set_ylabel(ylabel_dict[var], fontsize=fs)

for i, var in enumerate(variables):
    axes[i].set_ylabel(ylabel_dict[var], fontsize=fs)
    
    
axes[0].legend(
    fontsize=12,
    loc='best'
)

for ax in axes:
    ax.tick_params(labelsize=fs_ticks)

plt.tight_layout()
plt.show()

