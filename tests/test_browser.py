"""Browser smoke against temporary services when Chromium is already installed."""
import importlib.util
import unittest
from pathlib import Path

from test_agent import LiveAppFixture


@unittest.skipUnless(importlib.util.find_spec('playwright') and importlib.util.find_spec('comfy_sdk')
                     and list((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux*/chrome')),
                     'optional Playwright, cached Chromium and SDK required')
class BrowserTests(LiveAppFixture, unittest.TestCase):
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
                expect(page.locator('#version')).to_have_text('1.0.11')
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
