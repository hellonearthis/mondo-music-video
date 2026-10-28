"""Source provenance and real CPU FFmpeg regressions, using synthetic media only."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import shutil
import subprocess

import pytest
from PIL import Image

from mmv import final_assembly as assembly, subliminal, captions
from mmv.engine.assemble import probe_frames
from mmv.storage import write_json
from assembly_fixtures import source_recipe
from test_subliminal import video, frame_color

pytestmark = pytest.mark.skipif(not shutil.which('ffmpeg'), reason='needs ffmpeg')


def test_variants_are_separate_single_encodes_from_originals(tmp_path):
    recipe = source_recipe(tmp_path, video)
    original = tmp_path / 'original-clip.mkv'
    # A flash crosses the join between two raw passages.
    recipe['clips'] = [{'path': str(original), 'frames': 72}, {'path': str(original), 'frames': 72}]
    write_json(tmp_path / assembly.RECIPE, recipe)
    flash = tmp_path / 'red.png'
    Image.new('RGB', (128, 72), 'red').save(flash)
    store = SimpleNamespace(home=tmp_path)
    (tmp_path / 'uploads').mkdir()
    shutil.copy2(flash, tmp_path / 'uploads' / flash.name)
    sub = {'mode': 'image', 'image': flash.name, 'starts': [71], 'frames': 2, 'times': [71 / 24]}
    calls = []
    actual = assembly._run

    def record(argv, cwd):
        calls.append((argv, (Path(cwd) / 'assembly.ffgraph').read_text()))
        actual(argv, cwd)

    # Inject the recording runner at the render boundary.
    render = assembly.render
    with patch.object(assembly, 'render', side_effect=lambda recipe, dest, run=None: render(recipe, dest, run=record)):
        subliminal.apply_to_run(store, tmp_path, sub)
        flashed = (tmp_path / 'music-video.mp4').read_bytes()
        result = captions.apply_to_run(tmp_path, {**captions.clean({'mode': 'burned'}), 'cues': [(0.5, 2.0, 'caption')]})
    assert 'burn_error' not in result
    assert len(calls) == 2  # exactly one invocation for each variant
    for argv, graph in calls:
        inputs = [argv[i + 1] for i, arg in enumerate(argv) if arg == '-i']
        assert str(original) in inputs
        assert not any(Path(path).name.startswith('music-video') for path in inputs)
        assert argv[argv.index('-crf') + 1] == '6'
        assert argv[argv.index('-preset') + 1] == 'slow'
        assert 'concat=n=2:v=1:a=0' in graph
    assert 'overlay=' in calls[-1][1] and 'ass=' in calls[-1][1]
    assert (tmp_path / captions.UNCAPTIONED_NAME).read_bytes() == flashed
    for name in ('music-video.mp4', 'music-video-clean.mp4', captions.UNCAPTIONED_NAME):
        assert probe_frames(tmp_path / name) == 144
    for n in (71, 72):
        assert frame_color(tmp_path / captions.UNCAPTIONED_NAME, n, tmp_path)[0] > 180
    for n in (70, 73):
        assert frame_color(tmp_path / captions.UNCAPTIONED_NAME, n, tmp_path)[2] > 120
    # Audio is encoded from the same original track for every version.
    def audio_hash(path):
        return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a', '-c', 'copy', '-f', 'hash', '-'])
    assert audio_hash(tmp_path / 'music-video.mp4') == audio_hash(tmp_path / 'music-video-clean.mp4')


def test_attached_idents_resolve_originals_and_keep_timing(tmp_path):
    store = SimpleNamespace(home=tmp_path)
    runs, uploads = tmp_path / 'runs', tmp_path / 'uploads'
    runs.mkdir(); uploads.mkdir()
    raw = tmp_path / 'raw.mkv'
    video(raw)
    shutil.copy2(raw, uploads / 'song.mkv')
    ident = runs / 'ident'
    ident.mkdir()
    plan = {'fps': 24, 'width': 128, 'height': 72, 'total_frames': 24,
            'segments': [{'index': 0, 'trim_frames': 24}]}
    write_json(ident / 'plan.json', plan)
    write_json(ident / 'renders.json', {'seg000': {'video': str(raw)}})
    write_json(ident / 'request.json', {'kind': 'ident'})
    # No finished ident file is needed by the assembler.
    run = runs / 'song'; run.mkdir()
    request = {'kind': 'video', 'song': 'song.mkv', 'start_ident': 'ident/ident.mp4', 'end_ident': 'ident/ident.mp4'}
    recipe = assembly.build_recipe(store, run, request, plan, {'seg000': {'video': str(raw)}})
    assert recipe['frames'] == 72
    assert [a['path'] for a in recipe['audio']] == [None, str(uploads / 'song.mkv'), None]
    flash = tmp_path / 'red.png'; Image.new('RGB', (128, 72), 'red').save(flash)
    recipe['flash'] = {'picture': str(flash), 'starts': [23, 47], 'frames': 2}
    out = assembly.render(recipe, run / 'music-video.mp4')
    assert probe_frames(out) == 72
    for n in (23, 24, 47, 48):
        assert frame_color(out, n, tmp_path)[0] > 180
    for n in (22, 25, 46, 49):
        assert frame_color(out, n, tmp_path)[2] > 120
    (ident / 'renders.json').unlink()
    with pytest.raises(ValueError, match='Original assembly sources'):
        assembly.build_recipe(store, run, request, plan, {'seg000': {'video': str(raw)}})


def test_old_run_reconstruction_keeps_flash_and_replaces_captions(tmp_path):
    store = SimpleNamespace(home=tmp_path)
    run = tmp_path / 'runs' / 'old'; run.mkdir(parents=True)
    uploads = tmp_path / 'uploads'; uploads.mkdir()
    raw = tmp_path / 'raw.mkv'; video(raw)
    shutil.copy2(raw, uploads / 'song.mkv')
    write_json(run / 'request.json', {'kind': 'video', 'song': 'song.mkv'})
    write_json(run / 'plan.json', {'fps': 24, 'width': 128, 'height': 72, 'segments': [{'index': 0, 'trim_frames': 144}]})
    write_json(run / 'renders.json', {'seg000': {'video': str(raw)}})
    write_json(run / 'output.json', {'file': 'music-video.mp4', 'subliminal': {'mode': 'text'}, 'captions': {'uncaptioned_copy': 'old.mp4'}})
    write_json(run / 'prepared.json', {'subliminal': {'mode': 'text', 'text': 'hi', 'starts': [48], 'frames': 2},
                                        'captions': {'cues': [(1, 2, 'old words')], 'mode': 'burned'}})
    recipe = assembly.load_recipe(store, run)
    recipe = {**recipe, 'captions': {'cues': [(1, 2, 'new words')]}}
    work = tmp_path / 'work'; work.mkdir()
    argv = assembly.command(recipe, tmp_path / 'result.mp4', work)
    graph = (work / 'assembly.ffgraph').read_text()
    assert graph.count('ass=') == 1 and graph.count('overlay=') == 1
    assert 'new words' in next(work.glob('*.ass')).read_text()
    assert 'music-video.mp4' not in ' '.join(argv)


def test_bad_frame_count_and_cancellation_preserve_final(tmp_path):
    recipe = source_recipe(tmp_path, video)
    target = tmp_path / 'music-video.mp4'
    before = target.read_bytes()
    with patch('mmv.engine.assemble.probe_frames', return_value=143), pytest.raises(ValueError, match='143 frames'):
        assembly.render(recipe, target)
    assert target.read_bytes() == before
    def cancelled():
        raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        assembly.render(recipe, target, check=cancelled)
    assert target.read_bytes() == before
    assert not list(tmp_path.glob('assembly-*/render.mp4'))
