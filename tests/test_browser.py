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
                expect(page.locator('#version')).to_have_text('1.8.13')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('#video-form .song-input').set_input_files(str(self.song))
                expect(page.locator('.song-preview-wrap')).to_be_visible()
                expect(page.locator('.song-preview')).to_have_attribute('src', __import__('re').compile(r'^blob:'))
                expect(page.locator('#video-form .song-receipt')).to_contain_text('Uploaded:')
                page.wait_for_function('() => document.querySelector(".song-preview").readyState >= 1')
                page.evaluate("() => import('/js/project.js').then(m => m.saveProject())")
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
                page.wait_for_function("() => import('/js/production.js').then(m => m.isSseConnected())")
                jobs = self.fixture.app.state.jobs
                def operation(context):
                    context.update('Live stream progress', 30)
                    done.wait(10)
                    return {'mock': True}
                jobs.start('test', operation)
                expect(page.locator('#status-message')).to_have_text('Live stream progress')
                # Simulate a failed stream after it was connected; watchdog polling must survive.
                page.evaluate("() => import('/js/production.js').then(m => { const s = m.getSseSource(); s.close(); s.dispatchEvent(new Event('error')); })")
                jobs.active.update('Polling fallback progress', 60)
                expect(page.locator('#status-message')).to_have_text('Polling fallback progress', timeout=12000)
                done.set()
                expect(page.locator('#status-title')).to_have_text('COMPLETE', timeout=12000)
                page.set_viewport_size({'width': 360, 'height': 800})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 360)
            finally:
                done.set()
                browser.close()

    def test_vocabulary_editor_does_not_restore_stale_text_after_reset_or_reopen(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.on('dialog', lambda dialog: dialog.accept())
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate('() => document.querySelector("#open-vocab-panel-btn").click()')
                expect(page.locator('#panel-vocab')).to_be_visible()
                textarea = page.locator('#vocab-custom-textarea')
                textarea.fill('stale entry that was never applied')
                page.locator('#vocab-reset-all-btn').click()
                expect(textarea).to_have_value('')
                textarea.fill('dismissed edit')
                page.locator('.nav[data-panel=video]').click()
                page.locator('.nav[data-panel=vocab]').click()
                expect(textarea).to_have_value('')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_vocabulary_workspace_restores_selection_and_independent_folds(self):
        from playwright.sync_api import sync_playwright, expect
        project = {
            'panel': 'vocab',
            'forms': {'video-form': {'vocabulary_profile': 'full'}},
            'custom_vocabulary': {'settings': {'mode': 'replace', 'add': ['Workspace fixture', 'Remaining fixture'], 'exclude': []}},
            'details_sections': {'director-pacing': False, 'director-camera': True, 'director-render': False},
        }
        self.fixture.client.put('/api/project', json=project).raise_for_status()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                expect(page.locator('#panel-vocab')).to_be_visible()
                card = page.locator('.vocab-summary-cat-card[data-category=settings]')
                expect(card).to_contain_text('Workspace fixture')
                # Edits to one card preserve the other cards and remain stable after opening.
                page.evaluate('window.otherCard = document.querySelector(".vocab-summary-cat-card[data-category=lighting]")')
                page.locator('#vocab-random-summary-details').evaluate('(el) => el.open = true')
                card.locator('.vocab-chip-remove').first.click()
                expect(card).not_to_contain_text('Workspace fixture')
                expect(card).to_contain_text('Remaining fixture')
                self.assertTrue(page.evaluate('window.otherCard === document.querySelector(".vocab-summary-cat-card[data-category=lighting]")'))
                page.locator('#vocab-apply-btn').click()
                expect(page.locator('#panel-video')).to_be_visible()
                self.assertEqual(page.locator('#video-form details').evaluate_all('(els) => els.map(el => el.open)'), [False, True, False])
                page.wait_for_function('() => JSON.parse(localStorage.getItem("mmv_project_draft") || "{}").panel === "video"')
                page.reload()
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                self.assertEqual(page.locator('#video-form details').evaluate_all('(els) => els.map(el => el.open)'), [False, True, False])
                page.locator('.nav[data-panel=vocab]').click()
                expect(page.locator('.vocab-summary-cat-card[data-category=settings]')).to_contain_text('Remaining fixture')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_vocabulary_guide_navigation_and_dark_overflow_contrast(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.locator('#video-form .vocab-help-btn').click()
                expect(page.locator('#vocab-helper-dialog')).to_be_visible()
                expect(page.locator('#vocab-guide-raw')).to_contain_text('Visual vocabulary')
                page.locator('.nav-to-vocab-btn').click()
                expect(page.locator('#vocab-helper-dialog')).not_to_be_visible()
                expect(page.locator('#panel-vocab')).to_be_visible()
                page.locator('#vocab-random-summary-details').evaluate('(el) => el.open = true')
                page.evaluate('document.documentElement.dataset.theme = "dark"')
                more = page.locator('.vocab-chip-more').first
                expect(more).to_have_attribute('aria-label', __import__('re').compile('Show all entries in .+'))
                more.hover()
                colors = more.evaluate('(el) => { const s = getComputedStyle(el); return [s.color, s.backgroundColor]; }')
                def luminance(rgb):
                    channels = [int(n) / 255 for n in __import__('re').findall(r'\d+', rgb)[:3]]
                    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
                    return sum(c * w for c, w in zip(linear, [.2126, .7152, .0722]))
                light, dark = sorted(map(luminance, colors), reverse=True)
                self.assertGreaterEqual((light + .05) / (dark + .05), 4.5)
                more.click()
                expect(page.locator('#vocab-editor-pane')).to_be_visible()
                page.locator('#panel-vocab .vocab-help-btn').click()
                expect(page.locator('#vocab-helper-dialog')).to_be_visible()
            finally:
                browser.close()

    def test_score_editor_edits_beats_and_sections_and_gates_start(self):
        import json
        from playwright.sync_api import sync_playwright, expect
        name = self.fixture.client.post('/api/upload/song', files={'file': ('test.wav', self.song.read_bytes(), 'audio/wav')}).json()['file']
        beats = [{'time': round(0.5 * i, 3), 'downbeat': i % 4 == 1} for i in range(1, 17)]
        detected = {'duration': 8.5, 'tempo_bpm': 120, 'beats_per_bar': 4, 'beats': beats,
                    'sections': [{'start': 0, 'end': 4, 'label': 'low', 'energy': .2}, {'start': 4, 'end': 8.5, 'label': 'high', 'energy': .8}]}
        score = {'beats': [{'time': b['time'], 'energy': .5} for b in beats],
                 'passages': [{'start': 0, 'end': 4, 'shots': [{'start': 0}, {'start': 2}]}, {'start': 4, 'end': 8.5, 'shots': [{'start': 4}]}]}
        quote = {'detected': detected, 'score': score}
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.route('**/api/stems', lambda route: route.fulfill(json={'installed': False, 'install_command': 'pip install demucs', 'models': {}}))
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate("""([name, quote]) => import('/js/score_editor.js').then(m => {
                    window.__dirty = []; window.__replans = []; window.__drivers = [];
                    const host = document.createElement('div'); host.id = 'test-editor'; document.body.append(host);
                    return m.mountScoreEditor(host, {kind: 'video', song: name}, quote, {
                        onDirty: d => window.__dirty.push(d), onReplan: async (e, d) => { window.__replans.push(e); window.__drivers.push(d); }});
                })""", [name, quote])
                strip = page.locator('#test-editor .se-strip')
                expect(strip).to_be_visible()
                expect(page.locator('#test-editor .se-status')).to_contain_text('matches what you see')
                expect(page.locator('#test-editor .se-section-row')).to_have_count(2)
                strip.focus()
                page.keyboard.press('ArrowRight')
                page.keyboard.press('ArrowRight')
                page.keyboard.press('m')
                page.keyboard.press('b')
                page.locator('#test-editor input[type=range]').fill('50')
                expect(page.locator('#test-editor .se-status')).to_contain_text('not planned yet')
                self.assertTrue(page.evaluate('window.__dirty.at(-1)'))
                page.locator('#test-editor .se-section-row select').first.select_option('peak')
                expect(page.locator('#test-editor .se-driver-note')).to_contain_text('pip install demucs')
                self.assertTrue(page.evaluate('document.querySelector("#test-editor .se-driver option[value=drums]").disabled'))
                self.assertFalse(page.evaluate('document.querySelector("#test-editor .se-driver option[value=mix]").disabled'))
                page.locator('#test-editor button.primary').click()
                page.wait_for_function('window.__replans.length === 1')
                edits = page.evaluate('window.__replans[0]')
                self.assertEqual(page.evaluate('window.__drivers[0]'), 'mix')
                self.assertEqual(edits['muted_beats'], [1])
                self.assertEqual(edits['bar_one_beat'], 1)
                self.assertEqual(edits['beat_nudge_ms'], 50)
                self.assertEqual(edits['sections'], [{'start': 0, 'label': 'peak'}, {'start': 4, 'label': 'high'}])
                page.locator('#test-editor button:has-text("Reset edits")').click()
                expect(page.locator('#test-editor .se-status')).to_contain_text('matches what you see')
                self.assertFalse(page.evaluate('window.__dirty.at(-1)'))
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_stem_quality_choice_needs_its_own_model_and_passes_through_replan(self):
        from playwright.sync_api import sync_playwright, expect
        name = self.fixture.client.post('/api/upload/song', files={'file': ('test.wav', self.song.read_bytes(), 'audio/wav')}).json()['file']
        beats = [{'time': round(0.5 * i, 3), 'downbeat': i % 4 == 1} for i in range(1, 17)]
        quote = {'detected': {'duration': 8.5, 'tempo_bpm': 120, 'beats_per_bar': 4, 'beats': beats,
                              'sections': [{'start': 0, 'end': 8.5, 'label': 'mid', 'energy': .5}]},
                 'score': {'beats': [{'time': b['time'], 'energy': .5} for b in beats],
                           'passages': [{'start': 0, 'end': 8.5, 'shots': [{'start': 0}]}]}}
        models = {'htdemucs': {'ready': True}, 'htdemucs_ft': {'ready': False}, 'htdemucs_6s': {'ready': False}}
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.route('**/api/stems', lambda route: route.fulfill(json={'installed': True, 'install_command': 'pip install demucs', 'models': models}))
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate("""([name, quote]) => import('/js/score_editor.js').then(m => {
                    window.__calls = [];
                    const host = document.createElement('div'); host.id = 'test-editor'; document.body.append(host);
                    return m.mountScoreEditor(host, {kind: 'video', song: name}, quote, {
                        onDirty: () => {}, onReplan: async (e, d, q) => { window.__calls.push([d, q]); }});
                })""", [name, quote])
                disabled = lambda sel: page.evaluate('s => document.querySelector(s).disabled', sel)
                expect(page.locator('#test-editor .se-driver select').first).to_be_visible()
                self.assertFalse(disabled('#test-editor .se-driver option[value=drums]'))
                self.assertTrue(disabled('#test-editor .se-driver option[value=guitar]'))
                self.assertEqual(page.locator('#test-editor .se-setup-row').count(), 2)      # high-quality and 6-stem still missing
                expect(page.locator('#test-editor .se-driver-setup')).to_contain_text('about 324 MB')
                self.assertTrue(page.locator('#test-editor .se-driver-label:has-text("Stem quality")').is_hidden())
                page.locator('#test-editor .se-driver select').first.select_option('drums')
                self.assertTrue(page.locator('#test-editor .se-driver-label:has-text("Stem quality")').is_visible())
                self.assertTrue(disabled('#test-editor select option[value=high]'))
                models['htdemucs_ft']['ready'] = True
                page.locator('#test-editor button:has-text("Reset edits")').click()
                page.locator('#test-editor .se-driver select').first.select_option('drums')
                page.locator('#test-editor button.primary:has-text("Re-plan")').click()
                page.wait_for_function('window.__calls.length === 1')
                self.assertEqual(page.evaluate('window.__calls[0]'), ['drums', 'standard'])
            finally:
                browser.close()

    def test_lip_sync_editor_edits_lyric_lines_and_singer_and_gates_replan(self):
        from playwright.sync_api import sync_playwright, expect
        name = self.fixture.client.post('/api/upload/song', files={'file': ('test.wav', self.song.read_bytes(), 'audio/wav')}).json()['file']
        beats = [{'time': round(0.5 * i, 3), 'downbeat': i % 4 == 1} for i in range(1, 17)]
        quote = {'detected': {'duration': 8.5, 'tempo_bpm': 120, 'beats_per_bar': 4, 'beats': beats,
                              'sections': [{'start': 0, 'end': 8.5, 'label': 'mid', 'energy': .5}]},
                 'score': {'beats': [{'time': b['time'], 'energy': .5} for b in beats],
                           'passages': [{'index': 0, 'start': 0, 'end': 4, 'shots': [{'start': 0}]}, {'index': 1, 'start': 4, 'end': 8.5, 'shots': [{'start': 4}]}]},
                 'lipsync': {'singer': 'pig', 'actors': {'pig': 'Hambo', 'goon': 'Henchman'},
                             'passages': {'seg000': {'singing': True, 'reason': 'main singer', 'actor_id': 'pig'},
                                          'seg001': {'singing': False, 'reason': 'no sung lines in this passage', 'actor_id': None}}}}
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.route('**/api/stems', lambda route: route.fulfill(json={'installed': False, 'install_command': 'pip install demucs', 'models': {}}))
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate("""([name, quote]) => import('/js/score_editor.js').then(m => {
                    window.__calls = [];
                    const host = document.createElement('div'); host.id = 'test-editor'; document.body.append(host);
                    return m.mountScoreEditor(host, {kind: 'video', song: name, mouth_mode: 'lip_sync', actors: ['pig', 'goon'],
                        lyric_lines: [{start: 0.5, end: 3.5, text: 'Interdimensional lover'}], singers: []}, quote, {
                        onDirty: () => {}, onReplan: async (e, d, q, lip) => { window.__calls.push(lip); }});
                })""", [name, quote])
                expect(page.locator('#test-editor .se-lip')).to_be_visible()
                expect(page.locator('#test-editor .se-lip-summary')).to_contain_text('Hambo sings (main singer)')
                expect(page.locator('#test-editor .se-lip-summary')).to_contain_text('sealed (no sung lines in this passage)')
                expect(page.locator('#test-editor .se-line-row')).to_have_count(1)
                self.assertEqual(page.get_by_label('Main singer').locator('option').all_inner_texts(), ['Choose for me (seeded)', 'Hambo', 'Henchman'])
                expect(page.locator('#test-editor .se-status')).to_contain_text('matches what you see')
                page.get_by_label('Main singer').select_option('goon')
                expect(page.locator('#test-editor .se-status')).to_contain_text('not planned yet')
                page.locator('#test-editor button:has-text("Add line at cursor")').click()
                expect(page.locator('#test-editor .se-line-row')).to_have_count(2)
                expect(page.locator('#test-editor .se-status')).to_contain_text('Each lyric line needs words')
                self.assertTrue(page.evaluate('document.querySelector("#test-editor button.primary").disabled'))
                page.locator('#test-editor .se-line-row input[type=text]').nth(0).fill('I dated you')
                page.locator('#test-editor button.primary:has-text("Re-plan")').click()
                page.wait_for_function('window.__calls.length === 1')
                lip = page.evaluate('window.__calls[0]')
                self.assertEqual(lip['singers'], ['goon'])
                self.assertEqual([line['text'] for line in lip['lyric_lines']], ['I dated you', 'Interdimensional lover'])   # kept in time order
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_lyrics_detection_and_pasted_lyrics_fill_the_lines_in_the_editor(self):
        from playwright.sync_api import sync_playwright, expect
        name = self.fixture.client.post('/api/upload/song', files={'file': ('test.wav', self.song.read_bytes(), 'audio/wav')}).json()['file']
        beats = [{'time': round(0.5 * i, 3), 'downbeat': i % 4 == 1} for i in range(1, 17)]
        quote = {'detected': {'duration': 8.5, 'tempo_bpm': 120, 'beats_per_bar': 4, 'beats': beats,
                              'sections': [{'start': 0, 'end': 8.5, 'label': 'mid', 'energy': .5}]},
                 'score': {'beats': [{'time': b['time'], 'energy': .5} for b in beats],
                           'passages': [{'index': 0, 'start': 0, 'end': 8.5, 'shots': [{'start': 0}]}]},
                 'lipsync': {'singer': 'pig', 'actors': {'pig': 'Hambo'}, 'passages': {'seg000': {'singing': False, 'reason': 'no sung lines in this passage'}}}}
        models = {name_: {'cached': name_ == 'large-v3', 'download': 'about 1 GB'} for name_ in ('tiny', 'base', 'small', 'medium', 'large-v3')}
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors, posts = [], []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.route('**/api/stems', lambda route: route.fulfill(json={'installed': False, 'install_command': 'pip install demucs', 'models': {}}))
                page.route('**/api/lyrics', lambda route: route.fulfill(json={'available': True, 'install_command': 'pip install openai-whisper', 'models': models}))
                def post(route):
                    posts.append((route.request.url.rsplit('/', 1)[1], route.request.post_data_json))
                    if route.request.url.endswith('/detect'):
                        route.fulfill(json={'id': 'j1', 'state': 'running'})
                    else:
                        route.fulfill(json={'lines': [{'start': 1.0, 'end': 3.0, 'text': 'Interdimensional lover', 'timing': 'matched'},
                                                      {'start': 3.0, 'end': 5.0, 'text': 'I dated you', 'timing': 'interpolated'}], 'source': 'vocals stem'})
                page.route('**/api/lyrics/detect', post)
                page.route('**/api/lyrics/align', post)
                page.route('**/api/status', lambda route: route.fulfill(json={'state': 'complete', 'message': 'Complete', 'result': {
                    'lines': [{'start': 9.9, 'end': 12.1, 'text': 'Interdimensional lover'}], 'source': 'vocals stem', 'language': 'en', 'model': 'large-v3'}}))
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate("""([name, quote]) => import('/js/score_editor.js').then(m => {
                    const host = document.createElement('div'); host.id = 'test-editor'; document.body.append(host);
                    return m.mountScoreEditor(host, {kind: 'video', song: name, mouth_mode: 'lip_sync', actors: ['pig'], lyric_lines: [], singers: []}, quote,
                        {onDirty: () => {}, onReplan: async () => {}});
                })""", [name, quote])
                expect(page.locator('#test-editor .se-lip-summary')).to_contain_text('No lyric lines yet')
                expect(page.get_by_label('Speech model for lyrics detection')).to_have_value('large-v3')
                self.assertFalse(page.evaluate('document.querySelector("#test-editor .se-lip button[title^=\'Listen\']").disabled'))
                page.locator('#test-editor button:has-text("Detect lyrics")').click()
                expect(page.locator('#test-editor .se-line-row')).to_have_count(1, timeout=15000)
                expect(page.locator('#test-editor .se-status')).to_contain_text('Detected 1 lines from the vocals stem')
                self.assertEqual(posts[0][1]['model'], 'large-v3')
                page.locator('#test-editor textarea').fill('Interdimensional lover\nI dated you')
                page.locator('#test-editor button:has-text("Time pasted lyrics")').click()
                expect(page.locator('#test-editor .se-line-row')).to_have_count(2)
                expect(page.locator('#test-editor .se-status')).to_contain_text('1 line(s) could not be matched well')
                expect(page.locator('#test-editor .se-lip-summary')).to_contain_text('not used for singing until you confirm')
                page.locator('#test-editor button:has-text("Confirm timing")').click()
                expect(page.locator('#test-editor .se-lip-summary')).not_to_contain_text('guessed timing')
                self.assertEqual(posts[1][1]['text'], 'Interdimensional lover\nI dated you')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_a_modified_prompting_scheme_shows_a_warning_banner_and_an_intact_one_shows_nothing(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                expect(page.locator('#scheme-notice')).to_be_hidden()
                page.route('**/api/integrity', lambda route: route.fulfill(json={
                    'intact': False, 'changed': ['the writer prompt'], 'notice': 'This installation has changed Mondo\'s protected prompting scheme (the writer prompt). Videos made with it may not meet the Mondo standard.'}))
                page.reload()
                expect(page.locator('#scheme-notice')).to_be_visible()
                expect(page.locator('#scheme-notice')).to_contain_text('may not meet the Mondo standard')
            finally:
                browser.close()

    def test_subliminal_controls_show_the_right_fields_and_build_one_nested_request_object(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                fields = page.locator('#video-form .subliminal-fields')
                expect(fields).to_be_hidden()
                page.locator('#video-form select[name=subliminal_mode]').select_option('text')
                expect(fields).to_be_visible()
                expect(page.locator('#video-form input[name=subliminal_text]')).to_be_visible()
                expect(page.locator('#video-form input[name=subliminal_file]')).to_be_hidden()
                expect(page.locator('#video-form input[name=subliminal_times]')).to_be_visible()
                page.locator('#video-form select[name=subliminal_mode]').select_option('image')
                expect(page.locator('#video-form input[name=subliminal_file]')).to_be_visible()
                expect(page.locator('#video-form input[name=subliminal_text]')).to_be_hidden()
                page.locator('#video-form select[name=subliminal_placement]').select_option('downbeats')
                expect(page.locator('#video-form input[name=subliminal_count]')).to_be_visible()
                expect(page.locator('#video-form input[name=subliminal_times]')).to_be_hidden()
                nested = page.evaluate("""() => import('/js/production.js').then(m => {
                    const request = {title: 'x', subliminal_mode: 'text', subliminal_text: 'HONK', subliminal_frames: '3', subliminal_placement: 'manual',
                                     subliminal_times: '12.5, 40 55.2', subliminal_count: '4', subliminal_file: {}, subliminal_image: ''};
                    m.subliminalFromForm(request);
                    let message = '';
                    try { m.subliminalFromForm({subliminal_mode: 'text', subliminal_times: 'soon'}); } catch (error) { message = error.message; }
                    return {request, message};
                })""")
                self.assertEqual(nested['request'], {'title': 'x', 'subliminal': {'mode': 'text', 'image': '', 'text': 'HONK', 'frames': 3,
                                 'placement': 'manual', 'times': [12.5, 40, 55.2], 'count': 4}})
                self.assertIn('seconds', nested['message'])
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_the_flash_picture_upload_cannot_race_fail_silently_or_go_stale(self):
        from playwright.sync_api import sync_playwright, expect
        png = self.home / 'flash.png'
        png.write_bytes(b'\x89PNG\r\n\x1a\n')
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                page.locator('#video-form select[name=subliminal_mode]').select_option('image')
                counter = {'n': 0}

                def upload(route):
                    counter['n'] += 1
                    route.fulfill(json={'file': f'picture-{counter["n"]}.png'})
                page.route('**/api/upload/reference', upload)
                picture = page.locator('#video-form input[name=subliminal_file]')
                image = lambda: page.evaluate('document.querySelector("#video-form input[name=subliminal_image]").value')
                picture.set_input_files(str(png))
                page.wait_for_function('() => document.querySelector("#video-form input[name=subliminal_image]").value === "picture-1.png"')
                picture.set_input_files([])                                    # clearing the choice clears the stored picture
                page.wait_for_function('() => document.querySelector("#video-form input[name=subliminal_image]").value === ""')
                self.assertIsNone(page.evaluate('document.querySelector("#video-form").dataset.subliminalPending || null'))
                # a failed upload leaves nothing selected and nothing pending
                page.unroute('**/api/upload/reference')
                page.route('**/api/upload/reference', lambda route: route.abort())
                picture.set_input_files(str(png))
                page.wait_for_function('() => !document.querySelector("#video-form").dataset.subliminalPending')
                self.assertEqual(image(), '')
                # the helper makes older selections lose to the newest, whatever order they finish in
                result = page.evaluate("""() => import('/js/production.js').then(m => {
                    const selection = m.latestSelection();
                    const first = selection.begin(), second = selection.begin();
                    return [selection.isCurrent(first), selection.isCurrent(second)];
                })""")
                self.assertEqual(result, [False, True])
                # previewing while a picture is still uploading, or in picture mode with none chosen, is refused
                message = page.evaluate("""() => import('/js/production.js').then(m => {
                    const form = document.querySelector('#video-form');
                    form.dataset.subliminalPending = '1';
                    return m.preview(form).then(() => 'no error', error => error.message);
                })""")
                self.assertIn('Wait for the flash picture', message)
                page.evaluate('() => { delete document.querySelector("#video-form").dataset.subliminalPending; }')
                message = page.evaluate("""() => import('/js/production.js').then(m => {
                    try { m.subliminalFromForm({subliminal_mode: 'image', subliminal_image: '', subliminal_times: '5'}); return 'no error'; } catch (error) { return error.message; }
                })""")
                self.assertIn('Choose the picture', message)
                self.assertEqual([e for e in errors if 'Failed to' not in e], [])
            finally:
                browser.close()

    def test_saved_custom_vocabulary_preset_survives_reload(self):
        from playwright.sync_api import sync_playwright, expect
        self.fixture.client.post('/api/vocabularies', json={
            'id': 'mine', 'name': 'Mine', 'base_profile': 'full', 'tables': {}}).raise_for_status()
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#vocab-profile-select option[value=mine]") !== null')
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                page.locator('#vocab-profile-select').select_option('mine')
                page.evaluate("() => import('/js/project.js').then(m => m.saveProject())")
                page.reload()
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                expect(page.locator('#vocab-profile-select')).to_have_value('mine')
            finally:
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
                expect(page.locator('#version')).to_have_text('1.8.13')
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
