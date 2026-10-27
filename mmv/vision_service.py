"""Start the local vision server for style harvests, world reading and storyboards when it is not already running.

A server that is already answering is used as is and never stopped. Only a server this job started is stopped
afterwards, so the GPU is free again. Only loopback URLs are ever launched; hosted or remote vision services must
already be running.
"""
from contextlib import contextmanager, nullcontext
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from . import gpu_memory, runtime
from .vision_check import vision_command

VISION_KINDS = ('harvest', 'world_harvest', 'storyboard')
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')
HARVEST_CONTEXT = 32768


def is_local(settings):
    parts = urlsplit(settings.get('vision_url') or '')
    return parts.hostname in LOCAL_HOSTS and bool(parts.port)


def is_up(settings):
    return runtime.http_ok(settings['vision_url'].rstrip('/') + '/models')


def launch_plan(settings):
    """The argv that would start the vision server, or ValueError saying why Mondo cannot start it."""
    if not is_local(settings):
        raise ValueError('the vision URL is not a local address with a port, so Mondo cannot start it')
    if not settings.get('vision_model'):
        raise ValueError('Configure your vision model in Settings')
    if configured := (settings.get('vision_launch') or '').strip():
        command = json.loads(configured)
    else:
        try:
            command = vision_command(settings.get('writer_launch') or '', urlsplit(settings['vision_url']).port,
                                     settings['vision_model'], HARVEST_CONTEXT)
        except ValueError as exc:
            raise ValueError(f'no vision launch command is saved (Vision launch command) and none can be derived '
                             f'from the writer launch: {exc}') from exc
    if not (Path(command[0]).expanduser().is_file() or shutil.which(command[0])):
        raise ValueError(f'the vision server program was not found: {command[0]}')
    return command


def require_room(command):
    if not (need := gpu_memory.gguf_need_bytes(command)):
        return
    enough, memory = gpu_memory.wait_for_room(need)
    if enough is False:
        raise ValueError(f'Not enough free GPU memory to start the vision model: {gpu_memory.gib(memory[0])} of '
                         f'{gpu_memory.gib(memory[1])} free, about {gpu_memory.gib(need)} needed. '
                         'Close other programs using the GPU, then try again')


@contextmanager
def running(settings, directory, progress):
    """Yield with a vision server answering at vision_url, starting (and afterwards stopping) one if needed."""
    process = None
    if not is_up(settings):
        command = launch_plan(settings)
        require_room(command)
        progress('Starting the local vision model', 2)
        process = runtime.start_service(json.dumps(command), settings.get('writer_cwd'),
                                        settings['vision_url'].rstrip('/') + '/models',
                                        directory / 'vision-service.log', name='Vision model',
                                        launch_setting='vision_launch')
    try:
        yield
    finally:
        runtime.stop_process(process)


def for_request(request, prepared, context):
    """running() for the vision job kinds, a no-op for everything else."""
    if request.get('kind') not in VISION_KINDS:
        return nullcontext()
    return running(prepared['settings'], context.log_path.parent, context.update)
