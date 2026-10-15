# Dependencies and external services

The public application is licensed under Apache-2.0. Its dependencies remain
under their respective licenses; this project does not relicense them.

| Component | Role | License / provenance |
| --- | --- | --- |
| Open Actor Protocol 0.2.0 | Required actor protocol, signing, package verification and riders | MIT; pinned source commit in pyproject.toml; https://github.com/hodgemann/oap |
| cryptography (OAP dependency) | Ed25519 identities and signatures | See upstream distribution notices; https://github.com/pyca/cryptography |
| FastAPI / Starlette / Pydantic | Local web application | See installed dependency licenses |
| Uvicorn | Local HTTP server | See installed dependency license |
| python-multipart | Media upload parsing | See installed dependency license |
| Pillow | Reference-image decoding and metadata removal | See installed dependency license |
| FFmpeg / ffprobe | External, user-installed media tools | Licenses depend on the user's build; no binary is bundled |
| ComfyUI, custom nodes and model files | Optional, user-installed local generation | Separate upstream terms; no copies bundled |
| Topaz | Optional, user-owned export tool | Separate vendor license; no copy bundled |

Provider API documentation used to implement the hosted adapters and estimate
card, checked 2026-10-15:

- https://wavespeed.ai/docs/docs-api/minimax/minimax-h3-reference-to-video
- https://wavespeed.ai/docs/docs-api/bytedance/bytedance-seedance-2.0-text-to-video
- https://wavespeed.ai/docs/docs-api/bytedance/bytedance-seedance-2.5-text-to-video

Prices are estimates based on those dated pages and can change. The app does not
retry paid submissions automatically. Remote request IDs are saved with each
production. Always check the provider dashboard after an interrupted submission.

Before a broadly distributed release, inventory the resolved dependency wheels
and preserve all required notices. The development preview uses bounded direct
dependencies rather than a claim of a fully audited cross-platform lockfile.
