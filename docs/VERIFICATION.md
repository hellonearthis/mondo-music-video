# Verification — 1.0.10

Run from a checkout:

```sh
python -m pip install '.[mcp,test]'
python -m unittest discover -s tests -v
node --check webapp/app.js
bash -n install.sh
```

The automated suite uses temporary data, synthetic media and local mock AI
services. It runs the actual analyzer, planner, writer contract, Laya adapter,
renderer adapters and FFmpeg assembly. Learned Laya decisions are mocked in
that suite; no model download or paid generation is triggered by running tests.

Coverage includes source hashes and original golden plans; backend phrase/frame
limits; reference-slot contracts; OAP signatures, riders and package integrity;
hosted consent and request receipts; failed-writer render prevention; cancellation
of the app's own local job; single-operation enforcement; agent CLI and real MCP
transports; credentials; local HTTP boundaries; downloader integrity; and Topaz
command construction with preservation of the source video.

## Original-engine parity

On the development machine, the original and extracted analyzers processed the
same generated 40-second click track and returned exactly equal scores: 80 beats
and 20 downbeats. Twelve planner/casting/writer-job comparisons matched exactly
across four renderer backends and three seeds. The repository includes portable
score/plan golden fixtures, not private media or actors.

The source extraction manifest records source hashes and adaptations. One
planner correction handles hosted adapters that raise on oversized durations:
the existing phrase-shrinking loop now shrinks those phrases along the same
musical edges. Golden parity is checked on inputs within the original contract.

## 1.0.10 integration checks

All 45 automated tests passed. The integration suite covers
matching-instruction prompt recovery and public
actor descriptions reaching the writer. The original bundled H3 workflow is
retained byte for byte. JavaScript and shell syntax checks passed.
Windows launch, real GPU generation and browser interaction have not been
reverified for this integration.

## Historical 1.0.0 release checks

All 37 automated checks passed. Headless Chromium passed the complete upload,
analysis preview, production and playback-metadata flow at desktop and mobile
widths, including absence of manual timing controls and no mobile overflow.

A separate real local GPU production used the supplied 11.52-second song at
0.3 MP: 736 × 416, 19 detected beats, 5 downbeats, 2 sections and 9 planned shots.
The local LLM wrote the prompts, GPU Laya reviewed them (including a corrective
writer pass), and the standard H3 workflow rendered both passages. The original
assembler produced 276 frames at 24 fps, an 11.5-second H.264/AAC video. Full
FFmpeg decoding passed. No API generation credits were used. The test media,
model files and private run records are not distributed with the source.

The installed release environment was checked independently with Torch 2.14.1,
Transformers 5.20.0 and GPU Laya: the saved production prompt passed review on
CUDA in 492 ms after model loading. The live app version was verified as 1.0.0.

## External systems

GPU Laya inference and the real local song-to-video workflow are checked
separately from the automated mocks. Paid-provider service availability, model
quality and spelling in generated idents depend on the selected models/services.
Hosted adapter tests do not spend API credits. Topaz tests verify invocation;
they do not establish compatibility with every Topaz installation.

See PLATFORMS.md for the OS coverage. No test on one machine establishes that
all GPU drivers, custom-node versions, model files or operating systems work.
