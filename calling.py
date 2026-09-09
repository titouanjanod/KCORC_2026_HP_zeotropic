# -*- coding: utf-8 -*-
"""
Created on Wed Sep  9 16:04:46 2026

@author: titouanjanod
"""

from overall_modelling_woIA import overall

import pandas as pd

import numpy as np

from pathlib import Path

tables_folder = Path("tables")
npz_file_names = [
    file.stem
    for file in tables_folder.glob("*.npz")
    if file.is_file()
]

# CYCLOPEN_BUTANE_mass_0.25_0.75.npz

# print(npz_file_names)


# selected_fluid = 'R1233zd(E)'


# selected_fluid = 'CYCLOPEN_BUTANE_mass_0.25_0.75'

COP = np.zeros(len(npz_file_names))
UA_ev = np.zeros(len(npz_file_names))
UA_cd  = np.zeros(len(npz_file_names))


for i, one_fluid in enumerate(npz_file_names) :
    
    _, COP[i], UA_ev[i], UA_cd[i] = overall(one_fluid)
    
df = pd.DataFrame({ "Fluid":npz_file_names, 
                   "COP":COP, 
                   "UA_ev" :UA_ev, 
                   "UA_cd":UA_cd})




#%%




import numpy as np
import pandas as pd


import matplotlib.pyplot as plt

# ==========================================================
# PLOT CONTROLLERS
# ==========================================================
lw = 5            # line width
ms = 10           # marker size
fs = 16           # font size
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

# ==========================================================
# COLORS
# ==========================================================
colors = {
    "CYCLOPEN_BUTANE": "tab:blue",
    "Isopentane_Isobutane": "tab:red",
    "PENTANE_R1336MZZE": "tab:green",
    "R1224YDZ_R1234ZEE": "tab:orange",
    "R1336MZZZ_R1336MZZE": "tab:purple",
}

# ==========================================================
# CREATE 3 SUBPLOTS
# ==========================================================
fig, axes = plt.subplots(3, 1, figsize=(12, 15), sharex=True)

variables = ["COP", "UA_ev", "UA_cd"]

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

    ax.set_ylabel(var, fontsize=fs)
    ax.grid(True, alpha=0.3)

# ==========================================================
# FINAL FORMATTING
# ==========================================================
axes[-1].set_xlabel("Mass fraction of first component [-]", fontsize=fs)

axes[0].legend(
    fontsize=12,
    loc='best'
)

for ax in axes:
    ax.tick_params(labelsize=fs-2)

plt.tight_layout()
plt.show()

