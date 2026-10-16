"""Portable orchestration around the original Mondo music-video engine.

Analysis, timing, casting, prompt construction/validation, graph injection,
renderer calls and assembly are implemented by the extracted engine modules.
"""
from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse
from . import actors
from .storage import identifier, inside, read_json, write_json

ENGINE = Path(__file__).parent / 'engine'


def references(store, request):
    refs, descriptions = actors.check_cast(store, request.get('actors', []), request['content'])
    for name in request.get('references', []):
        if not name:
            continue
        try:
            path = inside(store.home / 'uploads', name)
        except ValueError:
            raise ValueError(f"Reference image '{name}' is not in the uploads directory")
        if path.suffix != '.png' or not path.is_file():
            raise ValueError(f"Reference image '{name}' not found")
        refs.append(path)
    if len(refs) > 9:
        raise ValueError('Choose at most nine total actor/reference images')
    return refs, descriptions


def roster_for(store, request, refs):
    roster = []
    ids = request.get('actors', [])
    for i, path in enumerate(refs):
        actor_id = ids[i] if i < len(ids) else 'reference_' + str(i + 1)
        record = store.actor(actor_id) if i < len(ids) else {}
        roster.append({'actor_id': actor_id, 'display_name': (record or {}).get('name') or f'Reference subject {i + 1}',
                       'sheet': str(path.name), 'sheet_path': str(path)})
    return roster


def prepare(store, request):
    from .render import get_backend
    from .engine.plan import plan
    from .engine.analyze import ScoreMap, Section
    from .engine.casting import assign
    settings = store.settings()
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('Install FFmpeg and FFprobe; run the setup doctor')
    kind = request['kind']
    if kind == 'harvest':
        if not settings['vision_model']:
            raise ValueError('Configure your vision model in Settings')
        if not request.get('references'):
            raise ValueError('Choose images to harvest')
        refs = []
        for x in request['references']:
            if not x:
                continue
            try:
                p = inside(store.home / 'uploads', x)
            except ValueError:
                raise ValueError(f"Harvest reference image '{x}' is not in the uploads directory")
            refs.append(p)
        if not refs or any(p.suffix != '.png' or not p.is_file() for p in refs):
            raise ValueError('Harvest reference image missing')
        identifier(request['style_id'])
        if (store.home / 'styles' / (request['style_id'] + '.json')).exists():
            raise ValueError('That style already exists')
        return {'settings': settings, 'segments': [], 'seconds': 0, 'references': refs,
                'estimate': settings['vision_call_estimate']}
    if not settings['writer_model']:
        raise ValueError('Configure your music-video writer model in Settings first')
    if settings['writer_mode'] == 'api' and settings['writer_call_estimate'] <= 0:
        raise ValueError('Declare an estimated API writer cost per call in Settings before generation')
    if kind == 'video':
        from .engine.validators.laya_semantic import _model_dir_staged
        if not _model_dir_staged(Path(settings['laya_model_dir']).expanduser()):
            raise ValueError('Configure your Laya model folder in Settings before music-video production')
    backend = get_backend(request['backend'])
    refs, descriptions = references(store, request)
    if request['backend'] not in ('local_h3', 'comfy_sdk_h3') and not store.key():
        raise ValueError('Configure your WaveSpeed API key in Settings')
    if request['backend'] == 'local_h3':
        for key in ('comfy_input', 'comfy_output'):
            if not settings[key] or not Path(settings[key]).expanduser().is_dir():
                raise ValueError('Configure your existing ComfyUI ' + key.removeprefix('comfy_') + ' folder in Settings')
        from .engine.comfy import WorkflowBuilder
        WorkflowBuilder.load(settings['workflow_map_path'], ENGINE)
        url = urlparse(settings['comfy_url'])
        if url.scheme != 'http' or url.path not in ('', '/'):
            raise ValueError('The original local H3 adapter needs a direct HTTP ComfyUI host and port')
    if request['backend'] == 'comfy_sdk_h3':
        from .comfy_sdk import require_sdk, validate_proxy_url, check_proxy
        require_sdk()
        validate_proxy_url(settings['comfy_sdk_url'])
        from .engine.comfy import WorkflowBuilder
        WorkflowBuilder.load(settings['workflow_map_path'], ENGINE)
        check_proxy(settings['comfy_sdk_url'], store.key('MMV_COMFY_API_KEY'))
    style = store.style(request['style_id'])
    if kind == 'video':
        if not request.get('song'):
            raise ValueError('Upload a song first')
        try:
            song = inside(store.home / 'uploads', request['song'])
        except ValueError:
            raise ValueError('Upload a song first')
        if not song.is_file():
            raise ValueError('Upload a song first')
        # Cache only original analysis, keyed by the audio bytes and meter.
        digest = hashlib.sha256(song.read_bytes() + str(request['beats_per_bar']).encode()).hexdigest()
        score_path = store.home / 'analysis' / (digest + '.json')
        score_path.parent.mkdir(exist_ok=True)
        if not score_path.exists():
            result = subprocess.run([sys.executable, '-m', 'mmv.worker', 'analyze', str(song), str(score_path),
                                     str(request['beats_per_bar'])], capture_output=True, text=True, timeout=1800)
            if result.returncode:
                raise ValueError('Original song analysis failed: ' + result.stderr[-1500:])
        score = ScoreMap.from_json(score_path)
        for key in ('start_ident', 'end_ident'):
            if request.get(key):
                try:
                    p = inside(store.home / 'runs', request[key])
                except ValueError:
                    raise ValueError(f"Ident path '{request[key]}' is invalid")
                record = read_json(p.parent / 'output.json', {})
                if not p.is_file() or record.get('kind') != 'ident' or record.get('file') != p.name:
                    raise ValueError('Choose a completed ident')
    else:
        seconds = request['ident_seconds']
        score = ScoreMap('ident', round(seconds * 24), 22050, 0, 4, sections=[Section(0, round(seconds * 24), 0, .2, 'low')])
    aspect_w, aspect_h = map(int, request['aspect'].split(':'))
    width, height = backend.plan_resolution(aspect_w, aspect_h, megapixels=request['megapixels'],
                                            resolution=request['resolution'] if request['backend'] not in ('local_h3', 'comfy_sdk_h3') else None)
    vocab = read_json(ENGINE / 'config/vocab.json')
    roster = roster_for(store, request, refs)
    p = plan(score, width=width, height=height, vocab=vocab, seed=request['seed'], slug='music-video',
             bars_per_phrase=request['bars_per_phrase'], ref_policy=request['ref_policy'],
             cast_size=len(roster), on_screen=request['on_screen'], ensemble_mode=request['ensemble_mode'], backend=backend)
    if not p.segments:
        raise ValueError('The original planner produced no musical segments for this track')
    for s in p.segments:
        if s.gen_frames > backend.max_gen_frames:
            raise ValueError('A detected passage exceeds the renderer limit; the original planner cannot fit this track')
        if s.ref_image_slots < backend.min_reference_images:
            raise ValueError('This renderer needs a reference in every passage. Choose an actor/image and Reference policy: All')
        if s.ref_image_slots > backend.capabilities()['max_reference_images']:
            raise ValueError('The planned cast exceeds this renderer’s reference limit')
    casting = assign(p, roster, policy=request['casting_policy'], seed=request['seed'],
                     ref_policy=request['ref_policy'], ensemble_mode=request['ensemble_mode'], on_screen=request['on_screen']) if roster else None
    render_cost = sum(backend.cost_for(s.duration_input, request['resolution'] if request['backend'] not in ('local_h3', 'comfy_sdk_h3') else None,
                                      s.ref_image_slots) for s in p.segments)
    writer_cost = len(p.segments) * settings['writer_call_estimate'] if settings['writer_mode'] == 'api' else 0
    return {'settings': settings, 'segments': [asdict(s) for s in p.segments], 'plan': asdict(p), 'score': asdict(score),
            'casting': casting, 'style': style, 'references': refs, 'descriptions': descriptions,
            'seconds': score.duration_seconds, 'estimate': round(render_cost + writer_cost, 4),
            'render_estimate': render_cost, 'writer_estimate': writer_cost,
            'analysis': {'tempo_bpm': score.tempo_bpm, 'beats': len(score.beat_frames),
                         'downbeats': len(score.downbeat_frames), 'sections': len(score.sections),
                         'shots': sum(len(s.shots) for s in p.segments), 'width': width, 'height': height}}


def fingerprint(store, request, prepared):
    payload = {k:v for k,v in prepared.items() if k not in ('references',)}
    digest = hashlib.sha256(json.dumps({'request': request, 'prepared': payload}, sort_keys=True).encode())
    files = list(prepared['references'])
    if request.get('song'): files.append(inside(store.home / 'uploads', request['song']))
    for key in ('start_ident', 'end_ident'):
        if request.get(key): files.append(inside(store.home / 'runs', request[key]))
    if request['backend'] in ('local_h3', 'comfy_sdk_h3') and request['kind'] != 'harvest':
        from .engine.comfy import WorkflowBuilder
        builder = WorkflowBuilder.load(prepared['settings']['workflow_map_path'], ENGINE)
        digest.update(json.dumps(builder.base, sort_keys=True).encode())
        files.append(Path(prepared['settings']['workflow_map_path']))
    for actor_id in request.get('actors', []):
        digest.update(json.dumps(store.actor(actor_id), sort_keys=True).encode())
    for file in files:
        digest.update(str(file).encode()); digest.update(file.read_bytes())
    return digest.hexdigest()


def produce(store, request, prepared, context, *, resume=False):
    directory = context.log_path.parent
    write_json(directory / 'request.json', request)
    write_json(directory / 'consent.json', prepared['consent'])
    data = {**prepared, 'references': [str(p) for p in prepared['references']]}
    write_json(directory / 'prepared.json', data)
    context.update('Starting original Mondo production pipeline', 1)
    from .jobs import Cancelled
    try:
        context.command([sys.executable, '-u', '-m', 'mmv.worker', 'produce', str(store.home), str(directory), *(['resume'] if resume else [])],
                        progress_path=directory / 'progress.json')
    except Cancelled:
        if request['backend'] == 'comfy_sdk_h3':
            from .comfy_sdk import cancel_requests
            try:
                cancel_requests(directory, prepared['settings']['comfy_sdk_url'], store.key('MMV_COMFY_API_KEY'))
            except Exception:
                context.update('Proxy cancellation could not be confirmed; inspect saved Comfy request IDs.')
        if request['backend'] == 'local_h3':
            receipt = read_json(directory / 'local-request.json', {})
            prompt_id = receipt.get('prompt_id')
            if prompt_id:
                from .render import request_json
                base = prepared['settings']['comfy_url'].rstrip('/')
                try:
                    queue = request_json(base + '/queue', timeout=3)
                    request_json(base + '/queue', {'delete':[prompt_id]}, timeout=3)
                    if any(len(item)>1 and item[1]==prompt_id for item in queue.get('queue_running',[])):
                        request_json(base + '/interrupt', {}, timeout=3)
                except ValueError:
                    pass
        raise
    if request['kind'] == 'harvest':
        return read_json(directory / 'result.json')
    result = read_json(directory / 'output.json')
    return {'file': context.record['id'] + '/' + result['file'], 'duration': result['duration']}
