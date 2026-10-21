"""Topaz cloud model catalog (from developer.topazlabs.com). Topaz's own /video/status list is authoritative:
`merge_live` adds models newer than this table and flags ones Topaz no longer accepts."""

UPSCALE = (
    ("Precision (Proteus family)", (
        ("prob-4", "Proteus", "General purpose; the usual choice for low to medium quality footage"),
        ("pnat-1", "Proteus Natural", "Natural-looking enhancement"),
        ("rhea-1", "Rhea", "High-fidelity 4× upscaling of fine detail"),
        ("ahq-12", "Artemis High Quality", "Balanced denoise and sharpening for good sources"),
        ("amq-13", "Artemis Strong Halo", "Artemis for footage with strong halos"),
        ("amqs-2", "Artemis Medium Halo", "Artemis for footage with medium halos"),
        ("alq-13", "Artemis Low Quality", "Artemis for poor sources"),
        ("alqs-2", "Artemis Medium Quality", "Artemis for medium sources"),
        ("aaa-9", "Artemis Aliasing / Moire", "Reduces aliasing and moire patterns"),
        ("ghq-5", "Gaia High Quality", "Refinement for high-quality CGI and animation"),
        ("gcg-5", "Gaia CG", "Refinement for computer graphics"),
        ("iris-2", "Iris Medium Quality", "Face recovery for degraded footage"),
        ("iris-3", "Iris Low Quality", "Face recovery for badly degraded footage"),
        ("thd-3", "Theia Fine Tune Detail", "Manual clarity and detail control"),
        ("thf-4", "Theia Fine Tune Fidelity", "Manual fidelity control"),
        ("dtv-4", "Dione TV", "Deinterlacing and legacy video conversion"),
        ("ddv-3", "Dione DV", "Deinterlacing of DV footage"),
        ("dtd-4", "Dione Robust", "Robust deinterlacing"),
        ("dtvs-2", "Dione Dehalo", "Deinterlacing with halo removal"),
        ("dtds-2", "Dione Robust Dehalo", "Robust deinterlacing with halo removal"),
    )),
    ("Generative (Starlight)", (
        ("slp-2.6", "Starlight Precise 2.6", "Realistic faces, textures and text for GenAI and archival video"),
        ("slf-3", "Starlight Fast 3", "Fastest Starlight; about 4× faster than Precise 2.6"),
        ("slf-2", "Starlight Fast 2", "Twice as fast as Precise with higher fidelity"),
        ("slhq-1", "Starlight HQ", "Maximum quality for modern high-resolution video"),
        ("slm-1", "Starlight Mini", "Restoration of archival and interlaced footage"),
    )),
    ("Creative (Astra)", (
        ("ast-2", "Astra 2", "Creative upscaling of GenAI video with detail and style control"),
    )),
    ("Denoise and utilities (use scale 1×)", (
        ("nyx-3", "Nyx", "Denoise"),
        ("nxf-1", "Nyx Fast", "Fast denoise"),
        ("nxl-1", "Nyx XL", "Denoise for heavy noise"),
        ("nxhf-1", "Nyx High Fidelity", "Highest-fidelity denoise"),
        ("thm-2", "Themis 2", "Motion deblur"),
        ("stab-1", "Stabilization", "Video stabilization"),
        ("hyp-1", "Hyperion", "SDR to HDR"),
    )),
)

INTERPOLATION = (
    ("apo-8", "Apollo", "General purpose frame interpolation and slow motion"),
    ("apf-2", "Apollo Fast", "Faster Apollo"),
    ("chr-2", "Chronos", "Natural slow motion for real-world motion"),
    ("chf-3", "Chronos Fast", "Faster Chronos"),
    ("aion-1", "Aion", "Interpolation for demanding footage"),
)

# Optional tuning for the Precision family (Topaz parameter names, with their documented ranges).
TUNING = (
    ("compression", "Compression recovery", -1, 1),
    ("details", "Detail reconstruction", -1, 1),
    ("noise", "Noise reduction", -1, 1),
    ("halo", "Halo reduction", -1, 1),
    ("preblur", "Anti-aliasing / deblur", -1, 1),
    ("blur", "Sharpness", -1, 1),
    ("recoverOriginalDetailValue", "Recover original detail", 0, 1),
    ("grain", "Added grain", 0, 0.1),
)
TUNING_RANGE = {key: (low, high) for key, _, low, high in TUNING}
MODES = ("Auto", "Relative", "Manual")


def catalog(live=None):
    groups = [{"group": name, "models": [{"id": i, "name": n, "note": d} for i, n, d in rows]} for name, rows in UPSCALE]
    known = {i for _, rows in UPSCALE for i, _, _ in rows} | {i for i, _, _ in INTERPOLATION}
    if live is not None:
        for group in groups:
            group["models"] = [m for m in group["models"] if m["id"] in live]
        extra = [{"id": i, "name": i, "note": "Offered by Topaz; not described here"} for i in sorted(set(live) - known)]
        if extra:
            groups.append({"group": "Other models offered by Topaz", "models": extra})
    return {"upscale": [g for g in groups if g["models"]],
            "interpolation": [{"id": i, "name": n, "note": d} for i, n, d in INTERPOLATION if live is None or i in live],
            "tuning": [{"key": k, "label": label, "min": low, "max": high} for k, label, low, high in TUNING],
            "modes": list(MODES), "live": live is not None}
