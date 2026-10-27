# Open Prop Protocol (OPP)

Open Prop Protocol (OPP) is an open specification for portable, consent-driven, verifiable prop and object reference packages in generative AI productions.

## Overview

While **Open Actor Protocol (OAP)** provides portable visual identities, content riders, and consent boundaries for characters and actors, **Open Prop Protocol (OPP)** provides verifiable, multi-view visual reference sheets and interaction composites for objects, instruments, vehicles, tools, and scene assets.

- **Props vs. Actors:** Props stay in your studio's prop library. They do not become actors, consume actor cast slots, or alter actor safety rider checks.
- **Verification & Provenance:** Packages (`.opp`) are bounded ZIP archives holding manifest metadata, multi-angle reference sheets, licenses, and optional Ed25519 digital signatures.
- **Cleaned Media:** Renderable images are verified, bounded, and normalized to metadata-free RGB PNGs, preventing EXIF/metadata leakage or injection attacks.
- **Interaction Selection:** An OPP package supports interaction composites (e.g. detailed closeups, alternative hand/play positions) matched by semantic tags and use descriptions, falling back to the base reference sheet.

## Package Architecture (.opp)

An `.opp` package is a self-contained ZIP bundle adhering to OPP v0.1 or v0.2:

```
package.opp
├── manifest.json       # Metadata, identity, licensing, clearance, and asset declarations
├── references/         # Multi-view composite sheets and textures
│   └── public/
│       └── base.png    # Primary multi-angle reference sheet
└── (signature)         # Optional Ed25519 signature verifying archive integrity
```

### Safety & Sandboxing Boundaries

- **Strict Path Limits:** Path traversal (`..`), absolute paths, and symlinks inside packages are strictly prohibited.
- **Resource Limits:** Archives are capped at 128 MB on disk and 256 MB expanded; individual image sheets are capped at 25 MB.
- **Zero Script Execution:** External executable scripts or foreign code inside packages are never executed. Original bundles are preserved intact in the private studio data store.

## How Mondo Music Video Uses OPP

1. **Musical Instruments:** Mondo bundles starter OPP props (e.g. `mmv-guitar`, `mmv-keyboards`) for instrument-playing roles in music videos.
2. **Custom Props:** You can inspect and import any valid `.opp` package into **03 / Actors & OAP → Open Prop Protocol library**.
3. **Prompt Integration:** During video generation, Mondo references the verified visual sheet hashes and physical object traits, ensuring visual consistency across cuts while keeping package-authored prompt modifiers from overriding studio direction.

## Digital Signatures & Trust

- **Verified Signatures:** A valid cryptographic signature proves the package has not been tampered with since creation and verifies the creator's key control.
- **Explicit Operator Acceptance:** You explicitly confirm acceptance of the verified signer upon import. Unsigned local drafts can also be imported when explicitly permitted.
