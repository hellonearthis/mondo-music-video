"""Browser smoke against temporary services when Chromium is already installed."""
import importlib.util
import unittest
from pathlib import Path

from test_agent import LiveAppFixture


@unittest.skipUnless(importlib.util.find_spec('playwright') and importlib.util.find_spec('comfy_sdk')
                     and list((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux*/chrome')),
                     'optional Playwright, cached Chromium and SDK required')
class BrowserTests(LiveAppFixture, unittest.TestCase):
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
            cached = list((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux*/chrome'))
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

    def test_sdk_selection_preview_recovery_and_playback(self):
        from playwright.sync_api import sync_playwright, expect
        self.fixture.configure_sdk()
        self.fixture.server.v2_download_fail = True
        with sync_playwright() as p:
            cached = list((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux*/chrome'))
            kwargs = {'executable_path': str(cached[-1])} if cached else {}
            browser = p.chromium.launch(headless=True, **kwargs)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                expect(page.locator('#version')).to_have_text('1.0.15')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('#video-form select[name=backend]').select_option('comfy_sdk_h3')
                page.locator('#video-form .song-input').set_input_files(str(self.song))
                expect(page.locator('#video-form .song-receipt')).to_contain_text('Uploaded:')
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
