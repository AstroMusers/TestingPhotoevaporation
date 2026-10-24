from pathlib import Path
import runpy

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def workflow():
    return runpy.run_path(str(Path(__file__).parent / 'scripts' / 'energy_limited_escape.py'))


def test_example_uses_shared_escape_helper_and_retains_physical_inputs(workflow, monkeypatch):
    original = workflow['energy_limited_mass_loss']
    calls = []
    def tracked(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setitem(workflow['escape_table'].__globals__, 'energy_limited_mass_loss', tracked)
    table = workflow['escape_table']()
    assert len(calls) == 9 and len(table) == 720
    assert table.mass_loss_g_s.gt(0).all()
    assert table.planet_mass_earth.eq(5).all()
    for _, group in table.groupby(['planet_radius_earth', 'efficiency']):
        ratio = group.mass_loss_g_s / group.xuv_flux_w_m2
        np.testing.assert_allclose(ratio, ratio.iloc[0])


@pytest.mark.parametrize('theme,extension', [('white', 'png'), ('dark', 'png'), ('white', 'pdf')])
def test_example_artifacts_themes_formats_and_preservation(workflow, tmp_path, monkeypatch, theme, extension):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from PIL import Image
    original_save = workflow['run_example'].__globals__['save_plot']
    def save(figure, path, **kwargs):
        FigureCanvasAgg(figure)
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        texts = [*figure.texts]
        for axis in figure.axes:
            texts.extend([axis.title, axis.xaxis.label, axis.yaxis.label])
            texts.extend(axis.get_legend().get_texts())
        for text in texts:
            bounds = text.get_window_extent(renderer)
            assert bounds.x0 >= 0 and bounds.y0 >= 0
            assert bounds.x1 <= figure.bbox.width and bounds.y1 <= figure.bbox.height
            assert text.get_fontsize() == 10
        original_save(figure, path, **kwargs)
    monkeypatch.setitem(workflow['run_example'].__globals__, 'save_plot', save)
    result = workflow['run_example'](tmp_path, typeplotback=theme, typefileplot=extension, time_tag='20261024_020000')
    table = pd.read_csv(result['paths']['table'])
    pd.testing.assert_frame_equal(table, result['table'], check_exact=False)
    if extension == 'png':
        image = np.asarray(Image.open(result['paths']['static']).convert('RGB'))
        assert image.shape[0] > 1000 and image.shape[1] > 2000
        assert np.any(image != image[0, 0])
        np.testing.assert_array_equal(image[0, 0], [0, 0, 0] if theme == 'dark' else [255, 255, 255])
    else:
        assert result['paths']['static'].read_bytes().startswith(b'%PDF')
    hashes = {name: path.read_bytes() for name, path in result['paths'].items()}
    with pytest.raises(FileExistsError):
        workflow['run_example'](tmp_path, typeplotback=theme, typefileplot=extension, time_tag='20261024_020000')
    assert hashes == {name: path.read_bytes() for name, path in result['paths'].items()}


def test_optional_bokeh_contains_same_flux_and_rate_values(workflow, tmp_path, monkeypatch):
    embed = pytest.importorskip('bokeh.embed')
    original = embed.file_html
    def capture(layout, *args, **kwargs):
        table = workflow['escape_table']()
        for panel, parameter, subset in zip(layout.children, ['planet_radius_earth', 'efficiency'],
                                            [table.loc[table.efficiency.eq(0.1)], table.loc[table.planet_radius_earth.eq(2)]]):
            for renderer, (_, group) in zip(panel.renderers, subset.groupby(parameter)):
                np.testing.assert_array_equal(renderer.data_source.data['x'], group.xuv_flux_w_m2)
                np.testing.assert_array_equal(renderer.data_source.data['y'], group.mass_loss_g_s)
        return original(layout, *args, **kwargs)
    monkeypatch.setattr(embed, 'file_html', capture)
    result = workflow['run_example'](tmp_path, write_bokeh=True)
    assert 'Incident XUV flux' in result['paths']['bokeh'].read_text()


def test_notebook_calls_pipeline_and_has_no_private_output_paths():
    import ast
    import json

    path = Path(__file__).parent / 'examples' / 'energy_limited_escape.ipynb'
    notebook = json.loads(path.read_text())
    source = '\n'.join(''.join(cell['source']) for cell in notebook['cells'] if cell['cell_type'] == 'code')
    assert "workflow['run_example']" in source
    assert 'energy_limited_escape.py' in source
    assert not any(isinstance(node, ast.Assert) and isinstance(node.test, ast.Call)
                   and isinstance(node.test.func, ast.Attribute) and node.test.func.attr in ('exists', 'is_file')
                   for node in ast.walk(ast.parse(source)))
    for cell in notebook['cells']:
        for output in cell.get('outputs', []):
            assert output['output_type'] != 'error'
            text = output.get('text', '') + str(output.get('data', {}).get('text/plain', '')) + str(output.get('data', {}).get('text/html', ''))
            assert not any(marker in text for marker in ('/Users/', '/private/var/', '/var/folders/'))


def test_unsupported_bokeh_is_rejected_before_output_writes(workflow, tmp_path, monkeypatch):
    bokeh = pytest.importorskip('bokeh')
    monkeypatch.setattr(bokeh, '__version__', '3.9.0')
    with pytest.raises(ImportError, match='Bokeh >= 3.10'):
        workflow['run_example'](tmp_path, write_bokeh=True)
    assert list(tmp_path.iterdir()) == []