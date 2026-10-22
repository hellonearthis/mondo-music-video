"""Render each delivery directly from its original clips in one FFmpeg invocation.

The saved recipe is local provenance, never an invitation to fall back to a final
MP4. Topaz is the sole operator-authorized exception to this rule.
"""
from pathlib import Path
import subprocess
import tempfile

from .storage import inside, read_json, write_json

RECIPE = 'assembly-source.json'


def segment_id(segment):
    return f"seg{segment['index']:03d}"


def source_file(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f'Original assembly source is missing: {path.name}. Restore the original clips/song; a finished video cannot be used instead.')
    return str(path)


def build_recipe(store, directory, request, plan, rendered, seen=()):
    """Snapshot original clip/song paths, recursively resolving attached productions."""
    directory = Path(directory).resolve()
    if directory in seen:
        raise ValueError('Circular attached-video assembly sources')
    fps = plan.get('fps', 24)
    clips = []
    final_name = read_json(directory / 'output.json', {}).get('file', 'ident.mp4' if request.get('kind') == 'ident' else 'music-video.mp4')
    for segment in plan['segments']:
        got = rendered.get(segment_id(segment), {})
        if not got.get('video'):
            raise ValueError('Original rendered clips are missing; restore renders.json and its clips')
        path = source_file(got['video'])
        # Never accept the finished output as a substitute for a renderer clip.
        if Path(path) == directory / final_name:
            raise ValueError('Original renderer clips are required, not the finished output')
        clips.append({'path': path, 'frames': segment['trim_frames']})
    frames = sum(c['frames'] for c in clips)
    node = {'clips': clips, 'frames': frames, 'fps': fps, 'width': plan['width'], 'height': plan['height'],
            'song_start_frame': 0, 'song_frames': frames,
            'audio': [{'path': source_file(inside(store.home / 'uploads', request['song'])) if request.get('kind', 'video') == 'video' else None,
                       'frames': frames}]}
    for key in ('start_ident', 'end_ident'):
        if not request.get(key):
            continue
        attached = inside(store.home / 'runs', request[key])
        child = load_recipe(store, attached.parent, (*seen, directory))
        if child['fps'] != fps:
            raise ValueError('Attached production must use the same frame rate')
        if key == 'start_ident':
            node['song_start_frame'] = child['frames']
            node['clips'] = [child, *node['clips']]
            node['audio'] = [*child['audio'], *node['audio']]
        else:
            node['clips'].append(child)
            node['audio'].extend(child['audio'])
        node['frames'] += child['frames']
    return node


def load_recipe(store, directory, seen=()):
    directory = Path(directory).resolve()
    if directory in seen:
        raise ValueError('Circular attached-video assembly sources')
    saved = read_json(directory / RECIPE, {})
    if saved:
        return saved
    request = read_json(directory / 'request.json', {})
    plan = read_json(directory / 'plan.json', {})
    rendered = read_json(directory / 'renders.json', {})
    if not plan.get('segments') or not rendered:
        raise ValueError('Original assembly sources are unavailable; restore plan.json, renders.json and the original clips/song. A finished video cannot be re-encoded instead.')
    node = build_recipe(store, directory, request, plan, rendered, seen)
    output = read_json(directory / 'output.json', {})
    prepared = read_json(directory / 'prepared.json', {})
    if output.get('subliminal'):
        if not prepared.get('subliminal'):
            raise ValueError('The original subliminal plan is missing')
        flash = prepared['subliminal']
        node = {**node, 'flash': {**flash, **({'picture': source_file(inside(store.home / 'uploads', flash['image']))}
                                               if flash['mode'] == 'image' else {})}}
    if (output.get('captions') or {}).get('uncaptioned_copy'):
        if not prepared.get('captions'):
            raise ValueError('The original caption plan is missing')
        node = {**node, 'captions': prepared['captions']}
    return node


def validate_sources(recipe):
    """Preflight all originals before a production can authorize paid generation."""
    for clip in recipe['clips']:
        if 'path' in clip:
            source_file(clip['path'])
        else:
            validate_sources(clip)
    for span in recipe['audio']:
        if span.get('path'):
            source_file(span['path'])
    if recipe.get('flash', {}).get('picture'):
        source_file(recipe['flash']['picture'])


def with_flash(store, directory, recipe, plan):
    from .subliminal import text_png
    assets = Path(directory) / 'assembly-assets'
    assets.mkdir(exist_ok=True)
    from uuid import uuid4
    picture = assets / f'flash-{uuid4().hex}.png'
    if plan['mode'] == 'text':
        text_png(plan['text'], recipe['width'], recipe['height'], picture)
    else:
        # Snapshot the uploaded picture so later caption renders reproduce it.
        from PIL import Image
        with Image.open(inside(store.home / 'uploads', plan['image'])) as image:
            image.convert('RGB').save(picture)
    return {**recipe, 'flash': {**plan, 'picture': str(picture.resolve())}}


def command(recipe, target, work, quality='high'):
    """Compile a source tree to one graph: trim/concat, effects, song, encode."""
    from .captions import to_ass
    argv = ['ffmpeg', '-nostdin', '-y', '-v', 'error', '-filter_complex_threads', '1']
    graph = []
    inputs = 0
    labels = 0
    width, height, fps = recipe['width'], recipe['height'], recipe['fps']

    def label():
        nonlocal labels
        labels += 1
        return f'[v{labels}]'

    def input_file(path, picture=False):
        nonlocal inputs
        index = inputs
        inputs += 1
        if picture:
            argv.extend(['-framerate', str(fps), '-loop', '1'])
        argv.extend(['-threads', '1', '-i', source_file(path)])
        return index

    def video(node):
        if 'path' in node:
            index, out = input_file(node['path']), label()
            graph.append(f'[{index}:v]fps={fps},trim=end_frame={node["frames"]},setpts=PTS-STARTPTS,'
                         f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,'
                         f'setsar=1,format=yuv420p,settb=AVTB{out}')
            return out
        parts = [video(c) for c in node['clips']]
        if not parts:
            raise ValueError('No original clips to assemble')
        out = label()
        graph.append(''.join(parts) + f'concat=n={len(parts)}:v=1:a=0{out}')
        if node.get('flash'):
            flash = node['flash']
            picture_path = flash.get('picture')
            if not picture_path:
                from .subliminal import text_png
                picture_path = text_png(flash['text'], width, height, Path(work) / f'flash{labels}.png')
            index, picture, flashed = input_file(picture_path, True), label(), label()
            enable = '+'.join(f'between(n,{s},{s + flash["frames"] - 1})' for s in flash['starts'])
            graph.append(f'[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,format=yuv420p{picture}')
            graph.append(f"{out}{picture}overlay=enable='{enable}':shortest=1{flashed}")
            out = flashed
        if node.get('captions'):
            plan = node['captions']
            script = Path(work) / f'captions{labels}.ass'
            script.write_text(to_ass(plan['cues'], width, height, plan), encoding='utf-8')
            captioned = label()
            graph.append(f'{out}ass={script.name}{captioned}')
            out = captioned
        return out

    picture = video(recipe)
    tracks = []
    for span in recipe['audio']:
        out = label()
        seconds = span['frames'] / fps
        if span.get('path'):
            index = input_file(span['path'])
            graph.append(f'[{index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,'
                         f'apad,atrim=duration={seconds:.9f},asetpts=PTS-STARTPTS{out}')
        else:
            graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={seconds:.9f},asetpts=PTS-STARTPTS{out}')
        tracks.append(out)
    audio = label()
    graph.append(''.join(tracks) + f'concat=n={len(tracks)}:v=0:a=1{audio}')
    # Script file avoids OS command-line length limits on long productions.
    script = Path(work) / 'assembly.ffgraph'
    script.write_text(';\n'.join(graph), encoding='utf-8')
    argv.extend(['-filter_complex_script', script.name, '-map', picture, '-map', audio,
                 '-frames:v', str(recipe['frames']), '-r', str(fps), '-c:v', 'libx264', '-crf', '16' if quality == 'low' else '6',
                 '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '320k', '-movflags', '+faststart', str(Path(target).resolve())])
    return argv


def _run(argv, cwd):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Final assembly failed: ' + result.stderr[-1500:])


def render(recipe, target, run=_run, check=lambda: None, quality='high'):
    """Publish only a verified first-generation output. Failure preserves target."""
    from .engine.assemble import probe_frames
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='assembly-', dir=target.parent) as temp:
        work = Path(temp)
        staged = work / 'render.mp4'
        run(command(recipe, staged, work, quality), work)
        actual = probe_frames(staged)
        if actual != recipe['frames']:
            raise ValueError(f'Assembly has {actual} frames instead of {recipe["frames"]}; original output preserved')
        check()
        staged.replace(target)
    return target


def assemble(store, directory, request, plan, rendered):
    recipe = build_recipe(store, directory, request, plan, rendered)
    output = render(recipe, Path(directory) / ('ident.mp4' if request['kind'] == 'ident' else 'music-video.mp4'))
    write_json(Path(directory) / RECIPE, recipe)
    from .engine import assemble as engine
    report_dir = Path(directory) / 'assembly'
    report_dir.mkdir(exist_ok=True)
    write_json(report_dir / 'assembly_report.json', {
        'source': 'original renderer clips', 'video_encodes_per_variant': 1,
        'quality': {'codec': 'libx264', 'crf': 6, 'preset': 'slow'},
        'frames': recipe['frames'], 'segments': [
            {'segment': segment_id(s), 'trimmed_to': s['trim_frames']} for s in plan['segments']]})
    if request['kind'] == 'video' and not (request.get('start_ident') or request.get('end_ident')):
        # Preserve the optional editing stem. PCM audio work never re-encodes picture.
        work = report_dir / 'work'
        stems = [engine.extract_audio_span(source_file(rendered[segment_id(s)]['audio']),
                 work / (segment_id(s) + '.wav'), s['trim_frames'], fps=recipe['fps'])
                 for s in plan['segments'] if rendered[segment_id(s)].get('audio')]
        if stems:
            engine.concat_diegetic(stems, report_dir / f"{plan.get('slug', 'music-video')}_diegetic.wav", work)
    return output
