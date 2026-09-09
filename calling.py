# -*- coding: utf-8 -*-
"""
Created on Wed Sep  9 16:04:46 2026

@author: titouanjanod
"""

from overall_modelling_woIA import overall



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


selected_fluid = 'CYCLOPEN_BUTANE_mass_0.25_0.75'

cycle = overall(selected_fluid)

