"""Browser smoke against temporary services when Chromium is already installed."""
import importlib.util
import os
import unittest
from pathlib import Path

from test_agent import LiveAppFixture


def _cached_chromium():
    roots = [Path.home() / '.cache/ms-playwright']
    if os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
        roots.insert(0, Path(os.environ['PLAYWRIGHT_BROWSERS_PATH']))
    if os.environ.get('LOCALAPPDATA'):
        roots.append(Path(os.environ['LOCALAPPDATA']) / 'ms-playwright')
    roots.append(Path.home() / 'Library/Caches/ms-playwright')
    patterns = (
        'chromium-*/chrome-linux*/chrome',
        'chromium-*/chrome-win*/chrome.exe',
        'chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium',
    )
    found = []
    for root in roots:
        if root.exists():
            for pattern in patterns:
                found.extend(root.glob(pattern))
    return found


@unittest.skipUnless(importlib.util.find_spec('playwright') and importlib.util.find_spec('comfy_sdk')
                     and _cached_chromium(),
                     'optional Playwright, cached Chromium and SDK required')
class BrowserTests(LiveAppFixture, unittest.TestCase):
    def test_delete_local_actor_and_style_with_confirmation(self):
        from mmv import actors
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect
        actors.create_actor(self.fixture.store, 'disposable', 'Disposable Actor', 'Overview', picture())
        self.fixture.client.post('/api/styles', json={'id': 'disposable', 'name': 'Disposable Style', 'direction': 'Daylight'}).raise_for_status()
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=actors]').click()
                card = page.locator('#actor-list article').filter(has_text='Disposable Actor')
                page.once('dialog', lambda dialog: dialog.dismiss())
                card.get_by_role('button', name='Delete actor', exact=True).click()
                expect(card).to_have_count(1)
                page.once('dialog', lambda dialog: dialog.accept())
                card.get_by_role('button', name='Delete actor', exact=True).click()
                expect(card).to_have_count(0)
                expect(page.locator('.actor-select option[value=disposable]')).to_have_count(0)
                page.locator('.nav[data-panel=styles]').click()
                card = page.locator('#style-list article').filter(has_text='Disposable Style')
                page.once('dialog', lambda dialog: dialog.accept())
                card.get_by_role('button', name='Delete style', exact=True).click()
                expect(card).to_have_count(0)
                expect(page.locator('.style-select option[value=disposable]')).to_have_count(0)
                page.reload()
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                self.assertFalse(self.fixture.store.actor('disposable'))
                self.assertFalse((self.home / 'styles/disposable.json').exists())
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_saved_api_profiles_switch_independently_without_network_generation(self):
        from mmv.api_profiles import save_profile
        from playwright.sync_api import sync_playwright, expect
        store = self.fixture.store
        original = store.settings()
        for name in ('account-a', 'account-b'):
            save_profile(store, name, 'writer', {'writer_url': f'https://{name}.example/v1',
                'writer_model': name, 'writer_mode': 'api', 'writer_call_estimate': .1}, f'private-{name}')
        save_profile(store, 'vision-account', 'vision', {'vision_url': 'https://vision.example/v1',
            'vision_model': 'vision-model'}, 'private-vision')
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=settings]').click()
                writer = page.locator('select[name=writer_api_profile]')
                expect(writer).to_have_value('')
                writer.select_option('account-a')
                page.locator('select[name=vision_api_profile]').select_option('vision-account')
                page.get_by_role('button', name='Save settings', exact=True).click()
                expect(page.locator('input[name=writer_model]')).to_have_value('account-a')
                expect(page.locator('input[name=vision_model]')).to_have_value('vision-model')
                page.locator('select[name=writer_api_profile]').select_option('account-b')
                page.get_by_role('button', name='Save settings', exact=True).click()
                expect(page.locator('input[name=writer_model]')).to_have_value('account-b')
                self.assertEqual(store.key('MMV_WRITER_API_KEY'), 'private-account-b')
                self.assertEqual(store.key('MMV_VISION_API_KEY'), 'private-vision')
                page.once('dialog', lambda dialog: dialog.accept('saved-copy'))
                page.get_by_role('button', name='Save configured writer API as a profile').click()
                expect(page.locator('select[name=writer_api_profile] option[value=saved-copy]')).to_have_count(1)
                page.locator('select[name=writer_api_profile]').select_option('')
                page.locator('select[name=vision_api_profile]').select_option('')
                page.get_by_role('button', name='Save settings', exact=True).click()
                expect(page.locator('input[name=writer_model]')).to_have_value(original['writer_model'])
                self.assertEqual(store.settings()['writer_url'], original['writer_url'])
                self.assertNotIn('private-account', page.locator('body').inner_text())
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_model_picker_and_oap_summary_preserve_operator_choices(self):
        import json
        from mmv import actors
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect
        self.fixture.install_test_h3_models()
        graph, mapping, map_path = self.fixture.custom_h3_workflow()
        settings = self.fixture.store.settings()
        settings['workflow_map_path'] = str(map_path)
        self.fixture.client.put('/api/settings', json=settings).raise_for_status()
        actors.create_actor(self.fixture.store, 'blue', 'Blue <b>Performer</b>', 'Blue jacket', picture())
        package = actors.export_actor(self.fixture.store, 'blue')
        manifest, _ = actors.package_info(package)
        source_bytes = Path(mapping['workflow']).read_bytes()
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=settings]').click()
                model = page.locator('select[name=h3_diffusion_model]')
                expect(model).to_have_value('my-current-model.safetensors')
                self.assertIn('test_diffusion.safetensors', model.locator('option').evaluate_all('(items) => items.map(o => o.value)'))
                model.select_option('test_diffusion.safetensors')
                page.locator('#settings-form > button').click()
                expect(page.locator('#notice')).to_have_text('Settings saved.')
                expect(page.locator('select[name=h3_diffusion_model]')).to_have_value('test_diffusion.safetensors')
                self.assertEqual(Path(mapping['workflow']).read_bytes(), source_bytes)
                # Choose another binding map through the file picker. Unchanged model
                # selectors must not override the newly chosen workflow.
                map_input = page.locator('input[name=workflow_map_path]')
                map_input.locator('..').locator('button').click()
                expect(page.locator('#folder-picker-dialog')).to_be_visible()
                expect(page.locator('#picker-confirm')).to_be_disabled()
                page.locator('#picker-breadcrumbs').get_by_role('button', name='Up').click()
                page.locator('#picker-filter').fill('operator-map.json')
                page.locator('#picker-entries .picker-entry').filter(has_text='operator-map.json').dblclick()
                expect(map_input).to_have_value(str(map_path))
                with page.expect_response('**/api/settings') as saved:
                    page.locator('#settings-form > button').click()
                self.assertEqual(saved.value.status, 200)
                expect(page.locator('select[name=h3_diffusion_model]')).to_have_value('my-current-model.safetensors')
                self.assertEqual(self.fixture.store.settings()['workflow_map_path'], str(map_path))
                # Folder selection and keyboard traversal use temporary directories only.
                folder_input = page.locator('input[name=comfy_input]')
                folder_input.locator('..').locator('button').click()
                expect(page.locator('#picker-selected-path')).to_have_value(str(self.home / 'comfy-input'))
                page.locator('#picker-confirm').click()
                expect(folder_input).to_have_value(str(self.home / 'comfy-input'))
                # OAP guide and signed package summary use the upstream schema.
                page.locator('.nav[data-panel=actors]').click()
                page.locator('#panel-actors .oap-help-btn').click()
                expect(page.locator('#oap-helper-dialog')).to_be_visible()
                page.locator('.oap-tab-btn[data-tab=riders]').click()
                expect(page.locator('#tab-riders')).to_be_visible()
                page.locator('.close-oap-dialog').click()
                page.locator('#oap-file').set_input_files(str(package))
                page.locator('#inspect-oap').click()
                card = page.locator('#oap-report-card')
                expect(card).to_contain_text('Blue <b>Performer</b>')
                expect(card).to_contain_text('nudity: none')
                expect(card).to_contain_text('signer not locally trusted')
                expect(card).to_contain_text(manifest['agent']['public_key'])
                expect(card).to_contain_text('political_ads')
                self.assertEqual(card.locator('b').count(), 0)
                self.assertNotIn('Non-commercial only', card.inner_text())
                page.locator('#toggle-raw-oap').click()
                expect(page.locator('#oap-report')).to_be_visible()
                page.set_viewport_size({'width': 390, 'height': 844})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390)
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                toggle = page.locator('#theme-toggle')
                expect(toggle).to_have_attribute('aria-pressed', 'true')
                toggle.click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.reload()
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.locator('#theme-toggle').click()
                page.reload()
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                page.set_viewport_size({'width': 360, 'height': 800})
                expect(page.locator('#theme-toggle')).to_be_in_viewport()
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
                page.set_viewport_size({'width': 1440, 'height': 1000})
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_song_preview_setup_guide_and_status_fallback(self):
        import json
        import threading
        from playwright.sync_api import sync_playwright, expect
        from mmv.storage import write_json
        settings = self.fixture.store.settings()
        command = json.dumps(['my-writer', '-m', "my-model's.gguf", '-c', '8192'])
        settings['writer_launch'] = command
        write_json(self.home / 'settings.json', settings)
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            done = threading.Event()
            try:
                page.goto(self.url)
                expect(page.locator('#version')).to_have_text('1.2.3')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('#video-form .song-input').set_input_files(str(self.song))
                expect(page.locator('.song-preview-wrap')).to_be_visible()
                expect(page.locator('.song-preview')).to_have_attribute('src', __import__('re').compile(r'^blob:'))
                expect(page.locator('#video-form .song-receipt')).to_contain_text('Uploaded:')
                page.wait_for_function('() => document.querySelector(".song-preview").readyState >= 1')
                page.evaluate('() => saveProject()')
                saved = self.fixture.client.get('/api/project').json()
                assert saved.get('files', {}).get('video-form', {}).get('song'), saved
                page.reload()
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                expect(page.locator('.song-preview')).to_have_attribute('src', __import__('re').compile(r'^/api/uploads/song/'))
                page.locator('.nav[data-panel=settings]').click()
                expect(page.locator('select[name=laya_device]')).to_have_value('cuda')
                page.locator('#panel-settings > .panel-header-row .llama-help-btn').click()
                expect(page.locator('#llama-helper-dialog')).to_be_visible()
                expect(page.locator('#llama-current-json')).to_have_text(command)
                page.locator('#writer-tuning-preset').select_option('hellonearthis')
                preview = json.loads(page.locator('#llama-current-json').inner_text())
                self.assertEqual(preview[preview.index('-m') + 1], "my-model's.gguf")
                self.assertEqual(preview[preview.index('-c') + 1], '16384')
                self.assertNotIn('--image-min-tokens', preview)
                expect(page.locator('input[name=writer_launch]')).to_have_value(command)
                page.locator('#apply-writer-tuning').click()
                self.assertEqual(json.loads(page.locator('input[name=writer_launch]').input_value()), preview)
                self.assertEqual(self.fixture.store.settings()['writer_launch'], command)
                page.wait_for_function('() => sseConnected')
                jobs = self.fixture.app.state.jobs
                def operation(context):
                    context.update('Live stream progress', 30)
                    done.wait(10)
                    return {'mock': True}
                jobs.start('test', operation)
                expect(page.locator('#status-message')).to_have_text('Live stream progress')
                # Simulate a failed stream after it was connected; watchdog polling must survive.
                page.evaluate('() => { sseSource.close(); sseSource.dispatchEvent(new Event("error")); }')
                jobs.active.update('Polling fallback progress', 60)
                expect(page.locator('#status-message')).to_have_text('Polling fallback progress', timeout=12000)
                done.set()
                expect(page.locator('#status-title')).to_have_text('COMPLETE', timeout=12000)
                page.set_viewport_size({'width': 360, 'height': 800})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 360)
            finally:
                done.set()
                browser.close()

    def test_update_notice_link_and_opt_in_setting(self):
        from mmv.storage import write_json
        from playwright.sync_api import sync_playwright, expect
        write_json(self.home / 'update-status.json', {
            'state': 'available', 'available': True, 'automatic': False,
            'message': 'An update is available. Automatic installation is turned off.',
            'available_version': '9.0.0', 'repository_url': 'https://github.com/example/mmv'})
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                expect(page.locator('#update-banner')).to_be_visible()
                expect(page.locator('#update-message')).to_contain_text('9.0.0')
                expect(page.locator('#update-repository')).to_have_attribute('href', 'https://github.com/example/mmv')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=settings]').click()
                choice = page.locator('input[name=auto_updates]')
                expect(choice).not_to_be_checked()
                choice.check()
                page.locator('#settings-form > button').click()
                expect(page.locator('#notice')).to_have_text('Settings saved.')
                expect(choice).to_be_checked()
                self.assertTrue(self.fixture.store.settings()['auto_updates'])
                choice.uncheck()
                page.locator('#settings-form > button').click()
                expect(page.locator('#notice')).to_have_text('Settings saved.')
                expect(choice).not_to_be_checked()
                self.assertFalse(self.fixture.store.settings()['auto_updates'])
            finally:
                browser.close()

    def test_sdk_selection_preview_recovery_and_playback(self):
        from playwright.sync_api import sync_playwright, expect
        self.fixture.configure_sdk()
        self.fixture.server.v2_download_fail = True
        with sync_playwright() as p:
            cached = _cached_chromium()
            kwargs = {'executable_path': str(cached[-1])} if cached else {}
            browser = p.chromium.launch(headless=True, **kwargs)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                expect(page.locator('#version')).to_have_text('1.2.3')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('#video-form select[name=backend]').select_option('comfy_sdk_h3')
                page.locator('#video-form .song-input').set_input_files(str(self.song))
                expect(page.locator('#video-form .song-receipt')).to_contain_text('Uploaded:')
                expect(page.locator('#video-form .song-preview')).to_be_visible()
                page.locator('#video-form textarea[name=direction]').fill('A sunlit coast with rhythmic waves.')
                page.locator('#video-form button[type=submit]').click()
                expect(page.locator('#preview-dialog')).to_be_visible()
                expect(page.locator('#quote-summary')).to_contain_text('$0.00')
                page.locator('#consent').check()
                page.locator('#start-production').click()
                expect(page.locator('#status-title')).to_have_text('FAILED', timeout=30000)
                self.fixture.server.v2_download_fail = False
                page.locator('#resume-production').click()
                expect(page.locator('#preview-dialog')).to_be_visible()
                expect(page.locator('#quote-summary')).to_contain_text('No writer calls')
                expect(page.locator('#consent')).not_to_be_checked()
                page.locator('#consent').check()
                page.locator('#start-production').click()
                expect(page.locator('#status-title')).to_have_text('COMPLETE', timeout=30000)
                page.locator('button[data-panel=outputs]').click()
                player = page.locator('#output-list video')
                expect(player).to_be_visible()
                player.evaluate('(v) => { v.preload = "auto"; v.load(); }')
                page.wait_for_function('() => document.querySelector("#output-list video").readyState >= 1')
                self.assertAlmostEqual(player.evaluate('(v) => v.duration'), 1.1, delta=.08)
                self.assertEqual(len(self.fixture.server.v2_submits), 1)
                page.set_viewport_size({'width': 390, 'height': 844})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390)
                self.assertEqual(errors, [])
            finally:
                browser.close()
