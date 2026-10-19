"""Minimal Comfy API v2 wire fixture, used by the real official SDK."""
import json
import socket
import uuid
from email.parser import BytesParser
from email.policy import default

NOW = '2026-10-16T12:00:00Z'
EXPIRES = '2099-01-01T00:00:00Z'


class ComfyV2Mixin:
    def v2_reply(self, value, status=200, **headers):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(data)

    def v2_job(self, job_id):
        status = self.server.v2_status.get(job_id, 'running' if self.server.v2_hold else 'succeeded')
        base = f'http://127.0.0.1:{self.server.server_port}/api/v2'
        return {'id': job_id, 'status': status, 'created_at': NOW, 'started_at': NOW,
                'completed_at': NOW if status == 'succeeded' else None, 'expires_at': EXPIRES,
                'queue_position': None, 'progress': None, 'error': None,
                'outputs': ([{'id': 'output-video-' + job_id, 'node_id': '92', 'name': '../../untrusted.mp4',
                    'type': 'video', 'content_type': 'video/mp4', 'size_bytes': len(self.v2_video(job_id)),
                    'hash': None, 'url': base + '/assets/output-video-' + job_id + '/content', 'url_expires_at': EXPIRES}]
                    + self.v2_studio_outputs(job_id, base)) if status == 'succeeded' else [],
                'urls': {name: base + '/jobs/' + job_id + suffix for name, suffix in
                         [('self', ''), ('events', '/events'), ('cancel', '/cancel')]}}

    def v2_studio_outputs(self, job_id, base):
        """The VideoHelperSuite file the workflow's studio node writes, when the submitted graph asked for one."""
        fmt = getattr(self.server, 'v2_studio', {}).get(job_id)
        if not fmt or getattr(self.server, 'v2_no_studio', False):
            return []
        content_type, name = ('video/quicktime', 'ProRes_00001.mov') if fmt == 'video/ProRes' else ('video/x-matroska', 'ffv1-mkv_00001.mkv')
        return [{'id': 'output-studio-' + job_id, 'node_id': '148', 'name': name, 'type': 'video', 'content_type': content_type,
                 'size_bytes': len(self.v2_video(job_id)), 'hash': None,
                 'url': base + '/assets/output-studio-' + job_id + '/content', 'url_expires_at': EXPIRES}]

    def v2_post(self, data):
        if not self.path.startswith('/api/v2/'):
            return False
        if self.path == '/api/v2/assets':
            msg = BytesParser(policy=default).parsebytes(
                ('Content-Type: ' + self.headers['Content-Type'] + '\r\n\r\n').encode() + data)
            parts = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True)
                     for part in msg.iter_parts()}
            asset_id = str(uuid.uuid4())
            self.server.v2_assets[asset_id] = parts
            self.v2_reply({'id': asset_id, 'hash': parts['expected_hash'].decode(),
                'size_bytes': len(parts['file']), 'content_type': parts['content_type'].decode(),
                'file_path': parts['file_path'].decode(), 'created_at': NOW, 'created_new': True,
                'url': f'http://127.0.0.1:{self.server.server_port}/api/v2/assets/{asset_id}/content',
                'url_expires_at': EXPIRES}, 201)
        elif self.path == '/api/v2/jobs':
            body = json.loads(data)
            self.server.v2_submits.append((dict(self.headers), body))
            if self.server.v2_reject:
                self.v2_reply({'error': {'code': 'queue_full', 'message': 'Fixture queue full'}}, 429,
                              **{'Retry-After': '1'})
            elif self.server.v2_drop:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
            else:
                job_id = str(uuid.uuid4())
                self.server.v2_ids.append(job_id)
                # Each job keeps its own clip, so a test can stage a failing first render.
                queued = getattr(type(self), 'queued_videos', None)
                self.server.v2_videos[job_id] = queued.pop(0) if queued else self.video
                fmt = ((body.get('workflow') or {}).get('148') or {}).get('inputs', {}).get('format')
                if fmt in ('video/ProRes', 'video/ffv1-mkv'):
                    if not hasattr(self.server, 'v2_studio'):
                        self.server.v2_studio = {}
                    self.server.v2_studio[job_id] = fmt
                self.v2_reply(self.v2_job(job_id), 201)
        elif self.path.endswith('/cancel'):
            job_id = self.path.split('/')[-2]
            self.server.v2_status[job_id] = 'canceled'
            self.server.v2_cancels.append(job_id)
            self.v2_reply(self.v2_job(job_id))
        else:
            self.v2_reply({'error': {'code': 'not_found', 'message': 'Unknown fixture route'}}, 404)
        return True

    def v2_video(self, job_id):
        return self.server.v2_videos.get(job_id, self.video)

    def v2_get(self):
        if self.path == '/api/v2/health':
            self.v2_reply({'status': 'healthy'})
        elif self.path.startswith('/api/v2/jobs/'):
            self.v2_reply(self.v2_job(self.path.split('/')[-1]))
        elif (self.path.startswith('/api/v2/assets/output-video-') or self.path.startswith('/api/v2/assets/output-studio-')) \
                and self.path.endswith('/content'):
            video = self.v2_video(self.path.rsplit('output-', 1)[1].split('-', 1)[1][:-len('/content')])
            if self.server.v2_download_fail:
                self.v2_reply({'error': {'code': 'not_found', 'message': 'Fixture download failure'}}, 503)
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'video/mp4')
                self.send_header('Content-Length', str(len(video)))
                self.end_headers()
                self.wfile.write(video)
        else:
            return False
        return True

    def do_HEAD(self):
        self.send_response(404)
        self.send_header('Content-Length', '0')
        self.end_headers()


def reset_v2(server):
    server.v2_assets = {}
    server.v2_submits = []
    server.v2_status = {}
    server.v2_ids = []
    server.v2_videos = {}
    server.v2_cancels = []
    server.v2_studio = {}
    server.v2_no_studio = False
    server.v2_hold = False
    server.v2_drop = False
    server.v2_reject = False
    server.v2_download_fail = False
