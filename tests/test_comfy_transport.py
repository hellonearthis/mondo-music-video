"""Official SDK and real official proxy, with a synthetic native ComfyUI only."""
import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from mmv.render import get_backend
from mmv.pipeline import ENGINE


@unittest.skipUnless(importlib.util.find_spec('comfy_api_proxy') and importlib.util.find_spec('comfy_sdk'),
                     'optional official SDK/proxy extras not installed')
class OfficialProxyTests(unittest.TestCase):
    def test_sdk_graph_media_and_recovery_through_real_proxy(self):
        from aiohttp import web
        from comfy_api_proxy.app import make_app
        from test_public_app import PublicAppTests, picture
        # Share only the synthetic FFmpeg media fixture; no models or GPU.
        PublicAppTests.setUpClass()
        try:
            video = PublicAppTests.server.RequestHandlerClass.video
            song = PublicAppTests.song
            asyncio.run(self.exercise(web, make_app, video, song, picture()))
        finally:
            PublicAppTests.tearDownClass()

    async def exercise(self, web, make_app, video, song, picture):
        uploads, graphs = {}, []
        job_id = None
        async def upload(request):
            reader = await request.multipart()
            while part := await reader.next():
                if part.filename:
                    uploads[part.filename] = await part.read()
                    name = part.filename
            return web.json_response({'name': name, 'subfolder': '', 'type': 'input'})
        async def submit(request):
            nonlocal job_id
            body = await request.json()
            job_id = body['prompt_id']
            graphs.append(body['prompt'])
            return web.json_response({'prompt_id': job_id, 'node_errors': {}})
        async def history(request):
            return web.json_response({job_id: {'status': {'status_str': 'success', 'completed': True},
                'outputs': {'92': {'videos': [{'filename': 'primary.mp4', 'subfolder': '', 'type': 'output'}]},
                            '148': {'gifs': [{'filename': 'fixture.mp4', 'subfolder': '', 'type': 'output'}]}}}})
        async def view(request):
            return web.Response(body=video, content_type='video/mp4')
        async def queue(request):
            return web.json_response({'queue_running': [], 'queue_pending': []})
        native = web.Application()
        native.add_routes([web.post('/upload/image', upload), web.post('/prompt', submit),
                           web.get('/history/{id}', history), web.get('/view', view), web.get('/queue', queue)])
        native_runner = web.AppRunner(native)
        await native_runner.setup()
        site = web.TCPSite(native_runner, '127.0.0.1', 0)
        await site.start()
        native_port = site._server.sockets[0].getsockname()[1]
        with tempfile.TemporaryDirectory() as tmp:
            proxy_runner = web.AppRunner(make_app(f'http://127.0.0.1:{native_port}', state_dir=Path(tmp) / 'proxy'))
            await proxy_runner.setup()
            proxy_site = web.TCPSite(proxy_runner, '127.0.0.1', 0)
            await proxy_site.start()
            proxy_port = proxy_site._server.sockets[0].getsockname()[1]
            root = Path(tmp)
            (root / 'song.wav').write_bytes(song)
            (root / 'blue.png').write_bytes(picture)
            backend = get_backend('comfy_sdk_h3')
            job = dict(segment_id='seg000', index=0, slug='sdk-proof', prompt='A blue subject follows <Audio 1>.',
                       gen_frames=39, duration_input=1.625, width=128, height=72, seed=7,
                       images=[('blue', str(root / 'blue.png'))], song=str(root / 'song.wav'),
                       audio_start_s=0, audio_end_s=1.1)
            try:
                backend.open_render(out_dir=root / 'renders', comfy_sdk_url=f'http://127.0.0.1:{proxy_port}',
                                    map_path=ENGINE / 'config/injection_map.json', root=ENGINE, timeout_s=10)
                result = await asyncio.to_thread(backend.render_segment, **job)
                self.assertEqual(Path(result['video']).read_bytes(), video)
                recovered = await asyncio.to_thread(backend.render_segment, **job)
                self.assertEqual(recovered['request_id'], result['request_id'])
                self.assertEqual(len(graphs), 1)
                self.assertEqual(len(uploads), 2)
                graph = graphs[0]
                for spec, field in [('image_refs', 'image'), ('audio_refs', 'audio')]:
                    prefix = backend.builder.map[spec]['socket_prefix'] + '0'
                    loader = graph[graph['136']['inputs'][prefix][0]]
                    self.assertIn(loader['inputs'][field], uploads)
                self.assertNotIn('core/ASSET', json.dumps(graph))
            finally:
                backend.close_render()
                await proxy_runner.cleanup()
                await native_runner.cleanup()
