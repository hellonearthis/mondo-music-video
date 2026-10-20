"""Cancellable process boundary for the extracted music-video pipeline."""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from .storage import Storage, inside, read_json, write_json


def render_timeout(backend, minutes=120):
    """Seconds to wait for one local clip; 0 minutes means no limit (the adapter needs a number, so infinity)."""
    if backend != 'local_h3': return None
    return minutes * 60.0 if minutes else float('inf')


def passage_cache_key(system, job, validators_version=''):
    # Empty version deliberately preserves every existing cache identity.
    prefix = "validated-v2\n" + ("validators:" + validators_version + "\n" if validators_version else "")
    return hashlib.sha256((prefix + system + "\n---\n" + json.dumps(job, sort_keys=True)).encode('utf-8')).hexdigest()


def cached_shot_bodies(prompt):
    """Recover assembled shot clauses for opt-in cache validators (never writer prose)."""
    detailed = prompt.partition('\ndetailed_description:\n')[2].partition('\noverall_soundscape:')[0]
    return re.split(r'\[Shot \d+\]', detailed)[1:]


def find_cached_passage_prompt(cache_dir, runs_dir, system, job, seg, tags, cleared_at=0.0,
                               *, extra_validators=(), validators_version=''):
    cache_key = passage_cache_key(system, job, validators_version)
    def acceptable(prompt):
        return all(not validate(prompt) for validate in extra_validators)
    cache_file = cache_dir / f"{cache_key}.json"
    if cache_file.exists() and (cleared_at <= 0 or cache_file.stat().st_mtime >= cleared_at):
        try:
            cached = read_json(cache_file)
            if cached and isinstance(cached.get("prompt"), str) and cached["prompt"] and acceptable(cached["prompt"]):
                return cached["prompt"]
        except Exception:
            pass

    if runs_dir and runs_dir.exists():
        for run_dir in sorted(runs_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
            if not run_dir.is_dir() or (cleared_at > 0 and run_dir.stat().st_mtime < cleared_at):
                continue
            job_file = run_dir / "writer_jobs" / f"{seg.segment_id}.json"
            if not job_file.exists():
                continue
            try:
                if not any(path.read_text(encoding="utf-8") == system for path in run_dir.glob("writer_system*.md")) or read_json(job_file) != job:
                    continue
            except Exception:
                continue

            run_prompts = run_dir / "prompts.json"
            if run_prompts.exists():
                try:
                    p_dict = read_json(run_prompts, {})
                    if seg.segment_id in p_dict and isinstance(p_dict[seg.segment_id], str):
                        prompt = p_dict[seg.segment_id]
                        if not acceptable(prompt):
                            continue
                        write_json(cache_file, {"prompt": prompt, "segment_id": seg.segment_id})
                        return prompt
                except Exception:
                    pass

    return None


def save_cached_passage_prompt(cache_dir, system, job, prompt, seg_id, *, validators_version=''):
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = passage_cache_key(system, job, validators_version)
        write_json(cache_dir / f"{cache_key}.json", {"prompt": prompt, "segment_id": seg_id})
    except Exception:
        pass


def _compact_writer_job(job: dict) -> str:
    """Serialize writer job without indentation or empty dialogue stubs to minimize LLM tokens."""
    payload = dict(job)
    if isinstance(payload.get("cast"), list):
        compact_cast = []
        for entry in payload["cast"]:
            if isinstance(entry, dict):
                cleaned = {k: v for k, v in entry.items() if not (k in ("lines", "direction", "part") and not v)}
                compact_cast.append(cleaned)
            else:
                compact_cast.append(entry)
        payload["cast"] = compact_cast
    return json.dumps(payload, separators=(",", ":"))


def _compact_ident_prompt(prompt: str, mode: str = "standard") -> str:
    """Prune mode-irrelevant sections and future-only i2v specs from the 64 KB ident prompt."""
    mode = str(mode or "standard").strip().lower()
    # Always omit the unused future IMAGE-TO-VIDEO IDENT template block.
    i2v_start = prompt.find("\nIMAGE-TO-VIDEO IDENT (SCENOGRAPHIC)")
    i2v_end = prompt.find("\nFailure modes\n", i2v_start if i2v_start != -1 else 0)
    if i2v_start != -1 and i2v_end != -1:
        prompt = prompt[:i2v_start] + prompt[i2v_end:]
    if mode != "scenographic":
        # Omit the 155-line Scenographic mode essay and Scenographic boxes when not in scenographic mode.
        sceno_start = prompt.find("\nScenographic mode\n")
        sceno_end = prompt.find("\nThe law of fresh starts\n", sceno_start if sceno_start != -1 else 0)
        if sceno_start != -1 and sceno_end != -1:
            prompt = prompt[:sceno_start] + prompt[sceno_end:]
        boxes_start = prompt.find("\nScenographic boxes\n")
        boxes_end = prompt.find("\nFailure modes\n", boxes_start if boxes_start != -1 else 0)
        if boxes_start != -1 and boxes_end != -1:
            prompt = prompt[:boxes_start] + prompt[boxes_end:]
    if mode == "standard":
        # In standard mode, vision harvesting has not been requested; omit the forensic reference-reading essay.
        ref_start = prompt.find("\nReading a reference image\n")
        ref_end = prompt.find("\nFailure modes\n", ref_start if ref_start != -1 else 0)
        if ref_start != -1 and ref_end != -1:
            prompt = prompt[:ref_start] + prompt[ref_end:]
    return prompt



def run(home, directory, *, resume=False):
    os.environ['MMV_HOME'] = str(home)
    store = Storage(home)
    request = read_json(directory / 'request.json')
    prepared = read_json(directory / 'prepared.json')
    from . import passage_plans
    if resume:
        passage_plans.verify_prompts(directory, prepared)
    settings = prepared['settings']
    from .engine import style, actor, casting, assemble
    from .engine.plan import ShotPlan
    from .engine.schema import WriterResponse, build_writer_request, assemble_prompt, validate_prompt, ValidationError, RIGGING_TAIL
    from . import quality
    from .engine.writer import call_llm
    from .render import get_backend
    from .pipeline import ENGINE
    from .render import request_json
    def progress(message, value):
        print(message, flush=True)
        write_json(directory / 'progress.json', {'message': message, 'progress': value})
    def llm(system, user):
        ok, text, error = call_llm(None, system, user, .7, 4096, 900,
                                   profile=(settings, store.key('MMV_WRITER_API_KEY')))
        if not ok:
            mode = "local llama.cpp" if settings.get('writer_mode') == 'local' else "API writer"
            endpoint = runtime.safe_endpoint(settings.get('writer_url', ''))
            err_str = str(error or '')
            if any(term in err_str.lower() for term in ("connection refused", "winerror 10061", "offline", "unreachable", "failed to establish", "connection error", "target machine actively refused")):
                raise ValueError(f"Prompt Writer is offline or unreachable ({mode} at {endpoint}): {error}. Please ensure the writer service is running.")
            raise ValueError(f"Writer ({mode} at {endpoint}) failed: {error or 'Writer returned no output'}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Writer ({settings.get('writer_model') or 'llama.cpp'}) returned empty text")
        return text
    if request['kind'] == 'harvest':
        progress('Harvesting visual style with the original style contract', 10)
        try:
            response = request_json(settings['vision_url'].rstrip('/') + '/chat/completions',
                 {'model': settings['vision_model'], 'messages': [{'role':'user', 'content': style.build_harvest_payload([Path(p) for p in prepared['references']])}],
                  'max_tokens':4096, 'temperature':.4}, key=store.key('MMV_VISION_API_KEY'), timeout=900)
        except Exception as exc:
            err_str = str(exc).lower()
            endpoint = runtime.safe_endpoint(settings.get('vision_url', ''))
            if any(term in err_str for term in ("connection refused", "winerror 10061", "offline", "unreachable", "failed to establish", "target machine actively refused")):
                raise ValueError(f"Vision engine is offline or unreachable at {endpoint}: {exc}. Please ensure your vision model service is running.") from exc
            raise ValueError(f"Vision service ({endpoint}) failed during style harvest: {exc}") from exc
        card, aesthetic = style.parse_harvest_response(response['choices'][0]['message']['content'])
        if not card.strip() or not aesthetic.strip(): raise ValueError('Harvest did not return a style card and aesthetic directives')
        record = {'id':request['style_id'], 'name':request['title'] or request['style_id'], 'direction':aesthetic, 'style_card':card}
        write_json(store.home / 'styles' / (request['style_id'] + '.json'), record)
        write_json(directory / 'result.json', {'style':record['id']})
        return
    plan_path = directory / 'plan.json'
    write_json(plan_path, prepared['plan'])
    write_json(directory / 'score.json', prepared['score'])
    write_json(directory / 'casting.json', prepared['casting'])
    plan = ShotPlan.from_json(plan_path)
    plan.slug = 'mmv-' + directory.name
    plan.to_json(plan_path)
    backend = get_backend(request['backend'])
    style_dir = directory / 'style';style_dir.mkdir(exist_ok=True)
    (style_dir / 'aesthetic.md').write_text(prepared['style']['direction'], encoding='utf-8')
    (style_dir / 'style_card.md').write_text(prepared['style'].get('style_card', prepared['style']['direction']), encoding='utf-8')
    # Public records are adapted to the original visual-contract reader in this process only.
    roster = (prepared['casting'] or {}).get('roster', [])
    actor_records = {}
    for member in roster:
        record = store.actor(member['actor_id']) or {}
        actor_records[member['actor_id']] = {**record, 'display_name':member['display_name'],
            'reference_sheets':[member['sheet']], 'visual_contract':record.get('visual_contract') or {'default_sheet':member['sheet'],
            'sheets':{member['sheet']:{'canonical_summary':record.get('description','')}}}}
    actor.load_actor_meta = lambda actor_id: actor_records[actor_id]
    # Sealed-lips rigging applies to every production unless the operator picks natural
    # expressions; lyrics text no longer switches it off (a lip-sync mode will own that).
    mouth_mode = request.get('mouth_mode') or ('sealed' if request.get('silent_mouths', True) else 'natural')
    # Lip sync keeps every passage sealed except those the approved plan marks as singing.
    effective_silent_mouths = mouth_mode in ('sealed', 'lip_sync')
    singing_plan = ((prepared.get('lipsync') or {}).get('passages') or {}) if mouth_mode == 'lip_sync' else {}
    dance_plan = prepared.get('dance') or None
    dance_passages = ((dance_plan or {}).get('passages') or {}) if request['kind'] == 'video' else {}
    cast_block = actor.cast_writer_block([a['actor_id'] for a in roster], silent_mouths=effective_silent_mouths)
    restrictions = [name for name in ('nudity','blood','violence','sexual') if request['content'].get({'blood':'blood_gore','sexual':'sexual_content'}.get(name,name), 'none') == 'none']
    # OAP's own category names are enforced independently by check_cast.
    if all(value == 'none' for value in request['content'].values()): restrictions = ['nudity','blood','violence','sexual']
    from . import runtime
    if not resume:
        writer_process = None
        if settings['writer_mode'] == 'local':
            progress('Starting music-video writer', 2)
            writer_process = runtime.start_service(settings['writer_launch'],settings['writer_cwd'],
                             settings['writer_url'].rstrip('/')+'/models',directory/'writer-service.log',
                             name='llama.cpp (Writer)', launch_setting='writer_launch')
        prompts = {}
        validator = None
        if request['kind'] == 'video':
            from .engine.validators import LayaSemanticValidator
            validator = LayaSemanticValidator()
            progress('Loading Laya prompt reviewer', 3)
            try:
                validator._load_agent()
                if getattr(validator, "device", None):
                    progress(f'Laya prompt reviewer loaded on {validator.device}', 3)
            except Exception as exc:
                raise ValueError(f"Laya semantic validator failed to load: {exc}") from exc

        if request['kind'] == 'ident':
            system = style.compose_ident_prompt()
            if request.get('compact_prompts'):
                system = _compact_ident_prompt(system, request['ident_mode'])
            message = style.build_ident_writer_message(request['title'], request['ident_seconds'], request['ident_mode'],
                       style_card=prepared['style'].get('style_card', prepared['style']['direction']), ident_notes=request['direction'])
            (directory / 'writer_system.md').write_text(system, encoding='utf-8')
            cache_dir = store.home / 'cache' / 'prompts'
            cache_key = hashlib.sha256((system + "\n---\n" + message).encode('utf-8')).hexdigest()
            cache_file = cache_dir / f"ident_{cache_key}.json"
            cleared_info = read_json(store.home / 'cache_cleared.json', {})
            cleared_at = float(cleared_info.get('cleared_at', 0))
            reuse_prompts = request.get('reuse_prompts', True)
            if reuse_prompts and cache_file.exists() and (cleared_at <= 0 or cache_file.stat().st_mtime >= cleared_at):
                try:
                    cached = read_json(cache_file)
                    if cached and "prompt" in cached:
                        prompts[plan.segments[0].segment_id] = cached["prompt"]
                        write_json(directory / 'prompts.json', prompts)
                        progress('Ident prompt resumed from cache', 30)
                except Exception:
                    pass
            if plan.segments[0].segment_id not in prompts:
                progress('Writing ident with the original ident prompt', 10)
                raw = llm(system, message).strip()
                if raw.startswith('```'): raw = '\n'.join(raw.splitlines()[1:-1]).strip()
                if request['title'] not in raw: raise ValueError('Ident writer omitted the exact requested title')
                prompts[plan.segments[0].segment_id] = raw
                write_json(directory / 'prompts.json', prompts)
                try:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    write_json(cache_file, {"prompt": raw})
                except Exception:
                    pass
        else:
            system = style.compose_writer_prompt(str(style_dir), actor_block=cast_block, restrictions=restrictions,
                        silent_mouths=effective_silent_mouths, lyrics=request['lyrics'] or None, direction=request['direction'] or None)
            system += quality.WRITER_RULES
            (directory / 'writer_system.md').write_text(system, encoding='utf-8')
            system_singing = cast_block_singing = None
            if any(item.get('singing') for item in singing_plan.values()):
                from . import lipsync
                cast_block_singing = actor.cast_writer_block([a['actor_id'] for a in roster], silent_mouths=False)
                system_singing = style.compose_writer_prompt(str(style_dir), actor_block=cast_block_singing, restrictions=restrictions,
                        silent_mouths=False, lyrics=request['lyrics'] or None, direction=request['direction'] or None)
                system_singing += '\n\n' + lipsync.SINGING_RULES + quality.WRITER_RULES
                (directory / 'writer_system_singing.md').write_text(system_singing, encoding='utf-8')
            system_dance = system_singing_dance = None
            if any(item.get('dancing') for item in dance_passages.values()):
                from . import dance
                tail = quality.WRITER_RULES            # the quality rules stay last: base, singing rules, dance rules, quality rules
                system_dance = system[:-len(tail)] + '\n\n' + dance.writer_rules(dance_plan) + tail
                (directory / 'writer_system_dance.md').write_text(system_dance, encoding='utf-8')
                if system_singing is not None:
                    system_singing_dance = system_singing[:-len(tail)] + '\n\n' + dance.writer_rules(dance_plan) + ' ' + dance.DANCE_SINGER_SENTENCE + tail
                    (directory / 'writer_system_singing_dance.md').write_text(system_singing_dance, encoding='utf-8')
            jobs_dir = directory / 'writer_jobs';jobs_dir.mkdir(exist_ok=True)
            cache_dir = store.home / 'cache' / 'prompts'
            cache_dir.mkdir(parents=True, exist_ok=True)
            cleared_info = read_json(store.home / 'cache_cleared.json', {})
            cleared_at = float(cleared_info.get('cleared_at', 0))
            reuse_prompts = request.get('reuse_prompts', True)
            for index, seg in enumerate(plan.segments):
                tags = backend.ref_tags(seg.ref_image_slots, 0, 1)
                sing = singing_plan.get(seg.segment_id) or {}
                singing = bool(sing.get('singing')) and system_singing is not None
                seg_silent = effective_silent_mouths and not singing
                dpass = dance_passages.get(seg.segment_id) or {}
                dancing = bool(dpass.get('dancing')) and system_dance is not None
                seg_system = (system_singing_dance if dancing else system_singing) if singing else (system_dance if dancing else system)
                seg_cast_block = cast_block_singing if singing else cast_block
                cast_entries = casting.cast_for(prepared['casting'], seg.segment_id)
                if singing:
                    from . import lipsync
                    cast_entries = lipsync.with_singer_lines(cast_entries, sing['actor_id'], sing['lines'])
                job = build_writer_request(plan, seg, tags, cast_entries, silent_mouths=seg_silent)
                if singing:
                    job['singing'] = {'actor_id': sing['actor_id'], 'picture_tag': sing['picture_tag'], 'lines': sing['lines'],
                                      'shots': lipsync.shot_lyrics(seg, sing['lines'])}
                if dancing:
                    job['dance'] = dance.job(dpass, dance_plan)
                if request['conceptual_theme']: job['conceptual_theme'] = request['conceptual_theme']
                write_json(jobs_dir / (seg.segment_id+'.json'), job)

                cache_validators = []
                if singing:
                    cache_validators = [
                        lambda prompt: validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=False),
                        lambda prompt: lipsync.lipsync_problems(prompt, cached_shot_bodies(prompt), seg, sing,
                                                              *lipsync.cast_refs(cast_entries, sing['actor_id']))]
                dance_version = ''
                if dancing:
                    if not singing:
                        cache_validators.append(lambda prompt: validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=seg_silent))
                    dance_version = f"dance-v{dance_plan.get('version', dance.VERSION)}"
                    cache_validators.append(lambda prompt: dance.dance_problems(prompt, cached_shot_bodies(prompt), seg, dpass, dance_plan))
                if reuse_prompts:
                    cached = find_cached_passage_prompt(cache_dir, store.home / 'runs', seg_system, job, seg, tags,
                                                        cleared_at=cleared_at, extra_validators=cache_validators, validators_version=dance_version)
                    if cached and not quality.prompt_problems(cached, seg, request['direction']):
                        if seg_silent and RIGGING_TAIL.rstrip(".").lower() not in cached.lower():
                            soundscape_pos = cached.find("\noverall_soundscape:")
                            if soundscape_pos > 0:
                                cached = cached[:soundscape_pos].rstrip() + f" {RIGGING_TAIL}\n" + cached[soundscape_pos:]
                            else:
                                cached = cached.rstrip() + f" {RIGGING_TAIL}\n"
                        prompts[seg.segment_id] = cached
                        write_json(directory / 'prompts.json', prompts)
                        progress(f'Musical passage {index+1} of {len(plan.segments)} (resumed from cache)', 5 + int(25*(index+1)/len(plan.segments)))
                        continue

                progress(f'Writing musical passage {index+1} of {len(plan.segments)}', 5 + int(25*index/len(plan.segments)))
                feedback, soft_fallback = '', None
                compact = bool(request.get('compact_prompts'))
                attempts = (4 if singing or dancing else 3) if settings['writer_mode'] == 'local' else 1
                for attempt in range(attempts):
                    if compact:
                        raw = llm(seg_system, _compact_writer_job(job) + feedback)
                    else:
                        raw = llm(seg_system + feedback, json.dumps(job, indent=2))
                    (directory / f'{seg.segment_id}.writer-{attempt+1}.json').write_text(raw, encoding='utf-8')
                    try:
                        response = WriterResponse.parse(raw, seg.segment_id)
                        prompt = assemble_prompt(seg, response, tags)
                        if singing:
                            prompt = lipsync.swap_audio_sentence(prompt, tags.music_tag)
                        if seg_silent and RIGGING_TAIL.rstrip(".").lower() not in prompt.lower():
                            soundscape_pos = prompt.find("\noverall_soundscape:")
                            if soundscape_pos > 0:
                                prompt = prompt[:soundscape_pos].rstrip() + f" {RIGGING_TAIL}\n" + prompt[soundscape_pos:]
                            else:
                                prompt = prompt.rstrip() + f" {RIGGING_TAIL}\n"
                        problems = (validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=seg_silent)
                                    + quality.prompt_problems(prompt, seg, request['direction'])
                                    + (lipsync.lipsync_problems(prompt, response.shot_bodies, seg, sing, *lipsync.cast_refs(cast_entries, sing['actor_id'])) if singing else [])
                                    + (dance.dance_problems(prompt, response.shot_bodies, seg, dpass, dance_plan) if dancing else []))
                    except (ValidationError, TypeError, AttributeError, KeyError) as exc:
                        prompt = None
                        problems = [str(exc)]
                    if dancing and prompt is not None and problems and all(dance.is_soft(x) for x in problems) and soft_fallback is None:
                        soft_fallback = (prompt, problems)          # only style advice left: keep the first such draft as the fallback
                    if dancing and problems and attempt == attempts - 1 and soft_fallback is not None:
                        prompt, kept = soft_fallback                # a later try got worse; use the best draft and record its advice
                        write_json(directory / f'{seg.segment_id}.dance-advice-kept.json', kept)
                        problems = []
                    if not problems:
                        progress(f'Laya reviewing musical passage {index+1} of {len(plan.segments)}', 5 + int(25*index/len(plan.segments)))
                        state = {'slug':plan.slug, 'backend':request['backend'], 'restrictions':{x:True for x in restrictions},
                                 'lyrics_flavor':(' / '.join(item['text'] for item in sing['lines']) if singing else request['lyrics']), 'director_direction':request['direction'],
                                 'style_digest':prepared['style'].get('style_card',prepared['style']['direction']), 'cast_digest':seg_cast_block}
                        response, problems = validator.run_clipboard(prompt,seg,tags,silent_mouths=seg_silent,state=state)
                        clip = validator.last_clipboard_request if hasattr(validator, 'last_clipboard_request') else validator.build_clipboard_request(prompt,seg,tags,silent_mouths=seg_silent,state=state)
                        write_json(directory / f'{seg.segment_id}.laya-request-{attempt+1}.json', clip)
                        write_json(directory / f'{seg.segment_id}.laya-response-{attempt+1}.json', response)
                    if not problems:
                        prompts[seg.segment_id] = prompt
                        write_json(directory / 'prompts.json', prompts)
                        save_cached_passage_prompt(cache_dir, seg_system, job, prompt, seg.segment_id, validators_version=dance_version)
                        break
                    write_json(directory / f'{seg.segment_id}.validation-{attempt+1}.json', problems)
                    feedback = '\n\nCorrect these validation failures in your next response:\n' + validator.format_retry_feedback(problems)
                else:
                    hint = ""
                    if settings.get('writer_mode') == 'local':
                        hint = " Note: Incomplete responses, JSON formatting errors, or shot-count mismatches often indicate your local writer's context allocation size (-c) or token limit is too small (see Settings > Local writer setup guide)."
                    raise ValueError(f'{seg.segment_id}: prompt validation failed after {attempts} attempts (evaluated by Laya and schema validator). See {directory / f"{seg.segment_id}.validation-{attempts}.json"}.{hint} Nothing rendered.')
            write_json(directory / 'prompts.json', prompts)
        if validator is not None:
            validator._agent = None
            del validator
            import gc
            gc.collect()
            torch = sys.modules.get("torch")
            if torch is not None and torch.cuda.is_available(): torch.cuda.empty_cache()
        runtime.stop_process(writer_process)
    else:
        prompts = read_json(directory / 'prompts.json', {})
        if any(not isinstance(prompts.get(seg.segment_id), str) or not prompts[seg.segment_id] for seg in plan.segments):
            raise ValueError('Resume requires saved validated prompts for every passage')
    if not resume:
        passage_plans.bind_prompts(directory, prepared, prompts)
    progress('All prompts validated; opening renderer', 32)
    vision_wanted = request['kind'] == 'video' and request.get('vision_quality_check')
    def start_comfy():
        # Returns a handle only when this production launched ComfyUI; None means it was already running.
        return runtime.start_service(settings['comfy_launch'],settings['comfy_cwd'],
                                     settings['comfy_url'].rstrip('/')+'/system_stats',directory/'comfy-service.log',
                                     name='ComfyUI', launch_setting='comfy_launch')
    comfy_process = None
    if request['backend'] == 'local_h3' or (request['backend'] == 'comfy_sdk_h3' and vision_wanted):
        comfy_process = start_comfy()
    rendered = {}
    sheets = casting.sheet_paths(prepared['casting']) if prepared['casting'] else {}
    url = urlparse(settings['comfy_url'])
    if request['backend'] == 'local_h3':
        from .engine.comfy import ComfyClient
        original_queue = ComfyClient.queue
        def record_queue(client, graph):
            write_json(directory / 'render-graph.json', graph)
            prompt_id = original_queue(client, graph)
            write_json(directory / 'local-request.json', {'prompt_id':prompt_id})
            return prompt_id
        ComfyClient.queue = record_queue
    backend.open_render(slug=plan.slug, out_dir=directory / 'renders', cast_sheets=list(sheets.items()), subject_image=None,
                        song=None, steps=20, timeout_s=render_timeout(request['backend'], settings.get('render_timeout_minutes', 120)), comfy_host=url.hostname, comfy_port=url.port or 8188,
                        comfy_input=settings['comfy_input'], comfy_output=settings['comfy_output'],
                        map_path=settings['workflow_map_path'], root=ENGINE,
                        comfy_sdk_url=settings['comfy_sdk_url'], comfy_sdk_key=store.key('MMV_COMFY_API_KEY'),
                        clip_quality=request.get('clip_quality') or 'standard')
    try:
        song = inside(store.home / 'uploads', request['song']) if request['kind'] == 'video' else directory / 'silence.wav'
        if request['kind'] == 'ident':
            subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-f','lavfi','-i','anullsrc=r=44100:cl=stereo','-t',str(plan.segments[0].gen_frames/24),str(song)],check=True)
        def render_passage(seg, segment_id, seed):
            images = [(member['actor_id'],sheets[member['actor_id']]) for member in casting.cast_for(prepared['casting'],seg.segment_id)]
            if len(images) != seg.ref_image_slots: raise ValueError('Original cast/reference-slot contract disagrees; refusing render')
            try:
                result = backend.render_segment(segment_id=segment_id,index=seg.index,slug=plan.slug,
                    prompt=prompts[seg.segment_id],duration_input=seg.duration_input,gen_frames=seg.gen_frames,
                    width=plan.width,height=plan.height,seed=seed,images=images,song=str(song),
                    audio_start_s=seg.audio_slice_start_s,audio_end_s=seg.audio_slice_end_s)
            except Exception as exc:
                err_str = str(exc).lower()
                if any(term in err_str for term in ("connection refused", "winerror 10061", "offline", "unreachable", "failed to establish", "target machine actively refused")):
                    endpoint = runtime.safe_endpoint(settings.get('comfy_url', 'http://127.0.0.1:8188'))
                    raise ValueError(f"ComfyUI video renderer is offline or unreachable at {endpoint}: {exc}. Please check that ComfyUI is running.") from exc
                raise
            video = result.get('video')
            if not video or not Path(video).is_file() or assemble.probe_frames(video) < seg.trim_frames:
                raise ValueError('Renderer returned a missing or short clip; refusing an incomplete final video')
            return result
        for index, seg in enumerate(plan.segments):
            progress(f'Rendering musical passage {index+1} of {len(plan.segments)}', 35+int(40*index/len(plan.segments)))
            rendered[seg.segment_id] = render_passage(seg, seg.segment_id, request['seed']+seg.index)
            write_json(directory / 'renders.json', rendered)
        if request['kind'] == 'video':
            vision, vision_note = None, None
            if vision_wanted:
                from . import quality
                from .vision_stage import VisionStage
                uses_comfy = request['backend'] in ('local_h3', 'comfy_sdk_h3')
                if uses_comfy and comfy_process is None:
                    vision_note = ('Vision check skipped: ComfyUI was already running outside Mondo, so it was not '
                                   'stopped to make room for the vision model. Close ComfyUI before starting to let Mondo manage it.')
                else:
                    vision = VisionStage(settings, directory, plan, quality.framing_requested(request.get('direction')),
                                         comfy_process, start_comfy if uses_comfy else None, progress,
                                         compact=bool(request.get('compact_prompts')))
            quality_completed = False
            try:
                # All passages exist before model swaps; vision retries share one further swap batch.
                rendered = run_quality_stage(directory, backend, request, plan, rendered, render_passage, progress, vision)
                quality_completed = True
            finally:
                if vision is not None:
                    vision.close()
                    vision_note = vision.note()
                write_json(directory / 'vision.json', {'requested': True, 'ran': quality_completed and vision is not None and not vision_note,
                                                       'note': vision_note} if vision_wanted else {'requested': False})
            write_json(directory / 'renders.json', rendered)
    finally:
        backend.close_render()
    progress('Assembling frame-exact music video', 85)
    if request['kind'] == 'ident':
        output = directory / 'ident.mp4'
        assemble.trim_to_frames(rendered[plan.segments[0].segment_id]['video'], output, plan.total_frames)
    else:
        opening, closing = request.get('start_ident'), request.get('end_ident')
        if opening and closing:
            # Original primitives, one encode per raw clip, stream-copy join and song mux.
            work=directory/'assembly/work';work.mkdir(parents=True,exist_ok=True)
            clips=[assemble.trim_to_frames(rendered[s.segment_id]['video'],work/(s.segment_id+'.mp4'),s.trim_frames) for s in plan.segments]
            first=inside(store.home/'runs',opening);last=inside(store.home/'runs',closing)
            clips=[assemble.normalize_clip(first,work/'opening.mp4')]+clips+[assemble.normalize_clip(last,work/'closing.mp4')]
            picture=assemble.concat_video(clips,work/'picture.mp4',work)
            audio=[assemble.extract_audio(first,work/'opening.wav'),assemble.extract_audio(song,work/'song.wav'),assemble.extract_audio(last,work/'closing.wav')]
            track=assemble.concat_audio(audio,work/'song-with-idents.wav',work)
            output=assemble.mux(picture,track,directory/'music-video.mp4')
        else:
            if opening or closing:
                result=assemble.assemble_run_with_ident(plan,rendered,song,inside(store.home/'runs',opening or closing),
                      'start' if opening else 'end',directory/'assembly')
            else:
                result=assemble.assemble_run(plan,rendered,song,directory/'assembly')
            output=directory/'music-video.mp4';shutil.copy2(result['video'],output)
    sub_result = sub_error = None
    if request['kind'] == 'video' and prepared.get('subliminal'):
        progress('Adding the subliminal flashes', 96)
        from . import subliminal
        try:
            sub_result = subliminal.apply_to_run(store, directory, prepared['subliminal'])
        except Exception as exc:                  # a bonus effect never fails the production: the clean video stays
            sub_error = str(exc)
    from .media import duration
    warnings = [entry['warning'] for entry in read_json(directory / 'quality.json', {}).values() if entry.get('warning')]
    vision_note = read_json(directory / 'vision.json', {}).get('note')
    if vision_note:
        warnings.insert(0, vision_note)
    if sub_error:
        warnings.insert(0, 'The subliminal flashes could not be added, so the finished video is the clean one: ' + sub_error[:200])
    # Studio-quality clips: say plainly when the requested master was not delivered (never resubmitted automatically).
    lost = sorted(sid for sid, got in rendered.items() if isinstance(got, dict) and got.get('clip_quality_note'))
    if lost:
        warnings.insert(0, 'Studio-quality clip not delivered for ' + ', '.join(lost) + '; the standard clip was used for the final video and the export.')
    delivered = request.get('clip_quality') or 'standard'
    if lost and len(lost) == len(rendered):
        delivered = 'standard'
    write_json(directory/'output.json',{'file':output.name,'duration':duration(output),'kind':request['kind'],
                                       'title':request['title'] or 'Music video',
                                       **({'clip_quality': delivered, 'clip_quality_requested': request.get('clip_quality')}
                                          if (request.get('clip_quality') or 'standard') != 'standard' else {}),
                                       **({'subliminal': sub_result} if sub_result else {}),
                                       **({'quality_warnings': warnings} if warnings else {})})
    progress('Complete',100)


# Seeds for the single automatic re-render stay distinct from every passage's first seed.
RETRY_SEED_OFFSET = 7919
# Only these free local renderers may re-render a passage automatically; paid
# renderers are never resubmitted, whatever their price card says.
QUALITY_RETRY_BACKENDS = ('local_h3', 'comfy_sdk_h3')
# Passing beats a measured failure, which beats an unmeasurable clip.
_PIXEL = {'pass': 0, 'fail': 1}
_VISION = {'fail': 1, 'error': 2}


def _rank(attempt):
    vision = attempt.get('vision') or {}
    return (_PIXEL.get(attempt['status'], 2), _VISION.get(vision.get('status'), 0),
            len(attempt['problems']) + len(vision.get('problems', [])))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run_quality_stage(directory, backend, request, plan, rendered, render_passage, progress, vision=None):
    """Check every rendered passage, then re-render failures once as a batch; record outcomes.

    Only completed, structurally valid clips reach this stage: renderer errors,
    including ambiguous SDK submissions, have already stopped the run. Each passage
    has one retry budget, used only on free local renderers, under a deterministic
    segment ID and seed, so SDK receipts stay exact. Every attempt records its clip
    hash; a resumed run reuses saved verdicts for unchanged clips and recovers
    spent retries instead of discarding them.

    `vision`, when supplied, has `judge(items)` and `prepare_render()`. `judge`
    receives [(segment_id, attempt, result)] and returns {attempt_segment_id:
    {'status': 'pass'|'warn'|'fail'|'error', 'problems': [...], 'retry': bool}}.
    It is called for the chosen attempts, then once more for vision retries, so a
    production swaps renderer -> vision -> renderer -> vision at most.
    `prepare_render()` runs before rendering vision retries.
    """
    from . import quality
    borders = not quality.framing_requested(request.get('direction'))
    free = request['backend'] in QUALITY_RETRY_BACKENDS and all(
        backend.cost_for(seg.duration_input) == 0 for seg in plan.segments)
    by_id = {seg.segment_id: seg for seg in plan.segments}
    total = len(plan.segments)
    saved = read_json(directory / 'quality.json', {})
    report, results = {}, {}

    def inspect(seg, result, segment_id, seed):
        digest = _sha256(result['video'])
        previous = next((a for a in saved.get(seg.segment_id, {}).get('attempts', [])
                         if a.get('segment_id') == segment_id and a.get('sha256') == digest
                         and a.get('status') in ('pass', 'fail')), None)
        if previous is not None:
            return dict(previous)
        found = quality.inspect_clip(result['video'], seg.trim_frames, [s.start_frame for s in seg.shots], borders)
        return dict(found, segment_id=segment_id, seed=seed, sha256=digest)

    def save():
        write_json(directory / 'quality.json', report)

    progress('Checking every passage for motion and framing', 76)
    for seg in plan.segments:
        attempt = inspect(seg, rendered[seg.segment_id], seg.segment_id, request['seed'] + seg.index)
        report[seg.segment_id] = {'attempts': [attempt],
                                  'retry_used': bool(saved.get(seg.segment_id, {}).get('retry_used'))}
        results[seg.segment_id] = [rendered[seg.segment_id]]
    save()

    def retry(candidates, label):
        for number, segment_id in enumerate(candidates):
            seg, entry = by_id[segment_id], report[segment_id]
            progress(f"Re-rendering passage {seg.index+1} of {total} once with a new seed ({label}; "
                     f"{number+1} of {len(candidates)})", 78)
            retry_id, retry_seed = segment_id + '-r1', entry['attempts'][0]['seed'] + RETRY_SEED_OFFSET
            entry['retry_used'] = True
            save()
            result = render_passage(seg, retry_id, retry_seed)
            entry['attempts'].append(inspect(seg, result, retry_id, retry_seed))
            results[segment_id].append(result)
            save()

    def best(segment_id):
        attempts = report[segment_id]['attempts']
        # The original wins ties; min returns the first of equal ranks.
        return min(range(len(attempts)), key=lambda i: _rank(attempts[i]))

    if free:
        # A crash after a retry was spent recovers it through its receipt instead of skipping it.
        recover = [s for s, e in report.items() if e['retry_used']]
        failing = [s for s, e in report.items() if e['attempts'][0]['status'] == 'fail' and not e['retry_used']]
        if recover:
            retry(recover, 'recovering an earlier retry')
        if failing:
            # Pixel failures are retried before any vision swap, while the renderer's models are loaded.
            retry(failing, 'motion/framing check')

    def judge(segment_ids, which):
        items = [(s, report[s]['attempts'][i], results[s][i]) for s in segment_ids for i in which(s)]
        pending = [item for item in items if not item[1].get('vision')]
        verdicts = vision.judge(pending) if pending else {}
        for segment_id, attempt, _ in pending:
            attempt['vision'] = verdicts.get(attempt['segment_id']) or {
                'status': 'error', 'problems': ['vision check returned no verdict'], 'retry': False}
        save()

    if vision is not None:
        progress('Vision check of every passage', 80)
        judge(list(report), lambda s: [best(s)])
        candidates = [s for s, e in report.items() if not e['retry_used'] and
                      (e['attempts'][best(s)].get('vision') or {}).get('retry')]
        if free and candidates:
            vision.prepare_render()
            retry(candidates, 'vision check')
            judge(candidates, lambda s: [len(report[s]['attempts']) - 1])

    chosen = {}
    for segment_id, entry in report.items():
        index, pick = by_id[segment_id].index, best(segment_id)
        used = entry['attempts'][pick]
        chosen[segment_id] = results[segment_id][pick]
        entry['used'] = used['segment_id']
        vision_verdict = used.get('vision') or {}
        details = ([] if used['status'] == 'pass' else list(used['problems']))
        details += [a['error'] for a in entry['attempts'] if a.get('error')]
        if vision_verdict.get('status') in ('warn', 'fail', 'error'):
            details += ['vision: ' + p for p in vision_verdict.get('problems', [])]
        clean = used['status'] == 'pass' and vision_verdict.get('status') not in ('fail', 'error')
        entry['status'] = ('ok' if clean and pick == 0 else 'retried_ok' if clean else
                           used['status'] if used['status'] != 'pass' else 'vision_' + vision_verdict['status'])
        entry.pop('warning', None)
        if details:
            entry['warning'] = (f"Passage {index+1}: {'; '.join(details)}"
                                + ('' if free or used['status'] == 'pass' else
                                   ' (not re-rendered automatically on this renderer)'))
    save()
    return chosen


def main():
    if sys.argv[1] == 'analyze':
        from .engine.analyze import analyze
        path=Path(sys.argv[3]); temp=path.with_suffix('.tmp')
        analyze(sys.argv[2],beats_per_bar=int(sys.argv[4])).to_json(temp)
        temp.replace(path)
    elif sys.argv[1] == 'drive':
        from .engine.analyze import ScoreMap
        from .stems import driven_score
        driven_score(ScoreMap.from_json(sys.argv[2]), sys.argv[3]).to_json(sys.argv[4])
    elif sys.argv[1] == 'voice':
        from .voice import estimate_voice
        Path(sys.argv[3]).write_text(json.dumps(estimate_voice(sys.argv[2])), encoding='utf-8')
    elif sys.argv[1] == 'produce':
        home,directory=Path(sys.argv[2]),Path(sys.argv[3])
        import signal
        from . import runtime
        def terminate(signum, frame): raise SystemExit(130)
        signal.signal(signal.SIGTERM,terminate)
        try:run(home,directory,resume=len(sys.argv)>4 and sys.argv[4]=='resume')
        except Exception as exc:
            message=str(exc)
            for value in Storage(home).secret_values():
                message=message.replace(value,'[redacted]')
            print(type(exc).__name__+': '+message,flush=True)
            raise SystemExit(1)
        finally:
            runtime.cleanup()
    else: raise SystemExit('Unknown worker phase')

if __name__=='__main__':main()
