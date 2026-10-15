# Verification — 0.1.1

Run from a checkout after installing the test extra:

```sh
python -m pip install '.[mcp,test]'
python -m unittest discover -s tests -v
node --check webapp/app.js
bash -n install.sh
```

Node is needed only for the JavaScript syntax check, not to run the application.
The tests use isolated temporary application data and a local mock HTTP service.
They create small synthetic media fixtures and use real FFmpeg/ffprobe to
exercise complete music-video and attached-ident assembly. No AI weights, API
credits or user productions are used.

Coverage includes upstream OAP signing/verification/round trip, tampering and
unsafe archive rejection, actor riders, hosted consent and request recording,
preview invalidation, cancellation, concurrent-operation rejection, credential
visibility, local-only request boundaries, interrupted-state recovery and
consent/integrity checks for the model downloader.

The version handler is freshly imported and compared against pyproject.toml,
README and API output. There is no requirement to start a server on the private
studio's port or import any private studio code.

All 32 integration/unit checks passed in a fresh Linux Python 3.12 virtual
environment with dependencies installed from their public sources. This includes
the pinned upstream OAP dependency. This is not an all-platform install claim.

Agent checks exercise streamed media upload, actor/OAP round trips, CLI JSON
output, preserved existing download files, preview/consent, local URL restrictions
and proxy bypass. MCP checks use the real stdio transport for tool discovery and
app calls, plus an in-memory MCP connection for a complete mock-rendered music
video. Installing only `.[test]` skips the two optional MCP protocol tests.

The installed wheel was also checked in headless Chromium at desktop (1440px)
and mobile (390px) widths: navigation, initialized backend/resolution menus and
live version output worked, and the mobile page had no horizontal overflow.

Real GPU inference, paid provider generation, Topaz execution, PowerShell setup
and clean-machine installation on all target platforms remain operator checks.
Do not treat mocked service tests as proof that these external systems work.
