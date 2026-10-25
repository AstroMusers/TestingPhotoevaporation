"""Static toy escape rates from TDpy's unit-aware energy budget."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

from astropy import units as u
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tdpy.exoplanet import energy_limited_mass_loss
from tdpy.plotting import plot_style, save_plot
from tdpy.verbosity import print


def escape_table():
    """Evaluate a stated toy grid without time evolution or observed inputs."""
    mass = 5 * u.M_earth  # [Earth mass]
    radii = np.array([1, 2, 3]) * u.R_earth  # [Earth radius]
    flux = np.geomspace(1, 1e4, 80) * u.W / u.m**2  # [W/m^2]
    efficiencies = [0.05, 0.1, 0.3]
    frames = []
    for radius in radii:  # [Earth radius]
        for efficiency in efficiencies:
            rate = energy_limited_mass_loss(mass, radius, flux, efficiency=efficiency)  # [kg/s]
            frames.append(pd.DataFrame({
                'planet_mass_earth': mass.to_value(u.M_earth),
                'planet_radius_earth': radius.to_value(u.R_earth),
                'xuv_flux_w_m2': flux.to_value(u.W / u.m**2),
                'efficiency': efficiency, 'absorption_radius_ratio': 1.0,
                'roche_factor': 1.0, 'mass_loss_g_s': rate.to_value(u.g / u.s),
            }))
    return pd.concat(frames, ignore_index=True)


def run_example(output_directory, typefileplot='png', typeplotback='white', write_bokeh=False, time_tag=None):
    """Return the toy table and append-only CSV, figure, and optional HTML paths."""
    if typefileplot not in ('png', 'pdf') or typeplotback not in ('white', 'dark'):
        raise ValueError('Use png/pdf output and white/dark backgrounds')
    tag = time_tag or datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    if not re.fullmatch(r'\d{8}_\d{6}', tag):
        raise ValueError('time_tag must use YYYYMMDD_HHMMSS')
    datetime.strptime(tag, '%Y%m%d_%H%M%S')
    directory = Path(output_directory)
    stem = f'energy_limited_escape_{typeplotback}_{tag}'
    paths = {'table': directory / f'{stem}.csv', 'static': directory / f'{stem}.{typefileplot}'}
    if write_bokeh:
        import bokeh
        from packaging.version import Version
        if Version(bokeh.__version__) < Version('3.10'):
            raise ImportError('Interactive output requires Bokeh >= 3.10')
        from bokeh.embed import file_html
        from bokeh.layouts import row
        from bokeh.plotting import figure
        from bokeh.resources import INLINE
        paths['bokeh'] = directory / f'{stem}.html'
    if any(path.exists() for path in paths.values()):
        raise FileExistsError('Existing escape outputs will not be overwritten')
    table = escape_table()
    directory.mkdir(parents=True, exist_ok=True)
    print(f"Writing to {paths['table']}...")
    table.to_csv(paths['table'], index=False, mode='x')
    panels = [
        (table.loc[table.efficiency.eq(0.1)], 'planet_radius_earth', 'Radius [Earth radius]', 'Efficiency = 0.1'),
        (table.loc[table.planet_radius_earth.eq(2)], 'efficiency', 'Heating efficiency', 'Radius = 2 Earth radii'),
    ]
    background, foreground = ('black', 'white') if typeplotback == 'dark' else ('white', 'black')
    colors = ['#ff7878', '#69c99a', '#78baff'] if typeplotback == 'dark' else ['#a51417', '#006b54', '#0068a2']
    interactive_panels = []
    sizes = {'font.size': 10, 'axes.titlesize': 10, 'axes.labelsize': 10,
             'xtick.labelsize': 10, 'ytick.labelsize': 10, 'legend.fontsize': 10}
    with plot_style(typeplotback=typeplotback), plt.rc_context(sizes):
        static, axes = plt.subplots(1, 2, figsize=(9, 4.2), sharey=True, layout='constrained')
        for axis, (subset, parameter, label, title) in zip(axes, panels):
            if write_bokeh:
                interactive = figure(width=480, height=360, x_axis_type='log', y_axis_type='log',
                                     x_axis_label='Incident XUV flux [W/m^2]', y_axis_label='Mass-loss rate [g/s]',
                                     title=title, background_fill_color=background, border_fill_color=background)
            for color, (value, group) in zip(colors, subset.groupby(parameter, sort=True)):
                axis.plot(group.xuv_flux_w_m2, group.mass_loss_g_s, color=color, label=f'{value:g}')
                if write_bokeh:
                    interactive.line(group.xuv_flux_w_m2, group.mass_loss_g_s, color=color,
                                     line_width=2, legend_label=f'{label} = {value:g}')
            axis.set(xscale='log', yscale='log', xlabel='Incident XUV flux [W/m^2]', title=title)
            axis.grid(False)
            axis.legend(title=label, title_fontsize=10, framealpha=1, fancybox=True)
            if write_bokeh:
                interactive.grid.visible = False
                interactive.title.text_color = foreground
                interactive.title.text_font_size = '10pt'
                interactive.legend.background_fill_color = background
                interactive.legend.background_fill_alpha = 1
                interactive.legend.label_text_color = foreground
                interactive.legend.label_text_font_size = '10pt'
                interactive.legend.border_radius = 6
                for side in interactive.axis:
                    side.axis_line_color = foreground
                    side.axis_label_text_color = foreground
                    side.major_label_text_color = foreground
                    side.major_tick_line_color = foreground
                    side.minor_tick_line_color = foreground
                    side.axis_label_text_font_size = side.major_label_text_font_size = '10pt'
                interactive_panels.append(interactive)
        axes[0].set_ylabel('Mass-loss rate [g/s]')
        static.text(0.5, 0.01, 'Static toy grid. Mass = 5 Earth masses. R_abs = R_p. Roche factor = 1.',
                    ha='center', fontsize=10)
        static.get_layout_engine().set(rect=(0, 0.08, 1, 0.92))
        print(f"Writing to {paths['static']}...")
        save_plot(static, paths['static'], dpi=300)
        plt.close(static)
    if write_bokeh:
        print(f"Writing to {paths['bokeh']}...")
        paths['bokeh'].write_text(file_html(row(*interactive_panels), INLINE, 'Static toy escape rates'), encoding='utf-8')
    return {'table': table, 'paths': paths}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, default=Path(__file__).resolve().parents[1] / 'visuals')
    parser.add_argument('--typefileplot', choices=('png', 'pdf'), default='png')
    parser.add_argument('--typeplotback', choices=('white', 'dark'), default='white')
    parser.add_argument('--bokeh', action='store_true')
    arguments = parser.parse_args()
    run_example(arguments.output_directory, arguments.typefileplot, arguments.typeplotback, arguments.bokeh)