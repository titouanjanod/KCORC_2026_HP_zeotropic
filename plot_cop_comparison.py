"""Plot all binary families from a common archive; no solver rerun needed."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def _plot_metric(data, values, reference, ylabel, title_quantity, output):
        family = data['family']
        x = data['fractions'][:, 0]
        good = data['passes_checks'] & data['converged']
        fig, ax = plt.subplots(figsize=(11, 7), layout='constrained')
        for name in np.unique(family):
            ids = np.flatnonzero(family == name)
            ids = ids[np.argsort(x[ids])]
            below = (data['pinch_locations'][ids,:,0].min(axis=1) < 3-.01
                     if 'pinch_locations' in data else np.zeros(len(ids),dtype=bool))
            # Connect all successfully calculated values, including cases
            # with warnings or pinch below the study criterion. Failed cases
            # have no finite value and are omitted from the line.
            finite = np.isfinite(values[ids])
            line, = ax.plot(x[ids][finite], values[ids][finite], '-o', ms=4,
                            label=name.replace('_', ' / '))
            bad = ids[(~good[ids] | below) & np.isfinite(values[ids])]
            ax.scatter(x[bad], values[bad], marker='x', color=line.get_color(), s=60)
        if reference is not None:
            ax.axhline(reference, color='black', ls='--',
                       label=f"R1233zd(E): {reference:.3f}")
        mode = json.loads(data['schema_json'].item())['mode']
        ax.set(xlabel='Mass fraction of FIRST component [kg/kg]',
               ylabel=ylabel, xlim=(0, 1),
               title=f'{title_quantity} | {mode} | same composition in both loops')
        ax.grid(alpha=.25)
        ax.legend(fontsize=9, loc='best')
        fig.get_layout_engine().set(rect=(0, .05, 1, .95))
        fig.text(.5, .015, 'Lines: all successfully calculated cases. Crosses: pinch below 3 K '
                 '(0.01 K tolerance) or other warning. Failed cases are omitted. 3 K is a study criterion.',
                 ha='center', fontsize=8)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=180)
        plt.close(fig)
        print(f'Saved comparison: {output}', flush=True)


def plot_comparison(summary, output):
    output = Path(output)
    with np.load(summary, allow_pickle=False) as data:
        cop_reference = float(data['reference_metrics'][0]) if 'reference_metrics' in data else None
        _plot_metric(data, data['metrics'][:, 0], cop_reference,
                     'Overall heating COP [-]', 'LT + HT heat pump', output)

        # heat_exchangers order: LT evaporator, LT condenser,
        # HT evaporator, HT condenser. Plot sums for both loops.
        ua_evaporators = data['heat_exchangers'][:, [0, 2], 1].sum(axis=1) / 1000
        ua_condensers = data['heat_exchangers'][:, [1, 3], 1].sum(axis=1) / 1000
        if 'reference_heat_exchangers' in data:
            ref_hx = data['reference_heat_exchangers']
            ref_ua_evaporators = float(ref_hx[[0, 2], 1].sum() / 1000)
            ref_ua_condensers = float(ref_hx[[1, 3], 1].sum() / 1000)
        else:
            ref_ua_evaporators = ref_ua_condensers = None
        suffix = json.loads(data['schema_json'].item())['mode']
        _plot_metric(data, ua_condensers, ref_ua_condensers,
                     'Total condenser UA: LT + HT [kW/K]',
                     'Condenser UA | LT + HT heat pump',
                     output.with_name(f'UA_condensers_mass_fraction_{suffix}.png'))
        _plot_metric(data, ua_evaporators, ref_ua_evaporators,
                     'Total evaporator UA: LT + HT [kW/K]',
                     'Evaporator UA | LT + HT heat pump',
                     output.with_name(f'UA_evaporators_mass_fraction_{suffix}.png'))


if __name__ == '__main__':
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, default=base/'mixture_summary_fixed_ua.npz')
    parser.add_argument('--output', type=Path, default=base/'mixture_plots/COP_mass_fraction_fixed-ua.png')
    args = parser.parse_args()
    plot_comparison(args.summary, args.output)
