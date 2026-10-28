"""The delicate prompting scheme: what is protected, and a check that says whether this installation still has it as released.

The writer and ident prompts, the sealed-lips scheme (rule text, rigging tail and validators), the owner-approved singing wording and
the plan/schema code were tuned over months of real renders. Changing them can quietly make videos worse. This module pins them so a
fork (or an agent working in one) cannot change them unnoticed: the app shows a banner and every production package says so.
Read docs/PROMPT_SCHEME_PROTECTION.md before touching any of it. Do not update these pins to make a check pass; see that document.
"""
from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# BEGIN PINS (regenerate only with the owner's approval: tools/update_protected_pins.py)
FILES = {
    'mmv/engine/actor.py': 'f8abcfb96345fd04939d96c5a50515969c31138010a8535df8b659db514c3ae9',
    'mmv/engine/analyze.py': '0b39d2b1fa2934e9d6d5fcfcf9ae0fd6c49c445a61b2f0512d814643b75717a8',
    'mmv/engine/atomic_io.py': '8438071d7ed7f44111ab89a78e76f5d5bc80da3a14ab9eb100a7ac3092eb55b1',
    'mmv/engine/backends/__init__.py': 'da72d9df1e0c3bb356948b51075a7613601b2cf9ee0ce37266d825eda1d2ce9f',
    'mmv/engine/backends/base.py': 'ca1bd3bc83c848addccd3bd7bae316427f1ee8e7fa2028edbbcaefcdf5845c5b',
    'mmv/engine/backends/wavespeed.py': 'e1ab4ad651edddd5ec03eb0cec7d793c846febd7fbfeaa6165dcfa50aa34ed08',
    'mmv/engine/casting.py': '248475a279a133cb0bccb852a99741d217790604cb49bf6ae8be1349d24513a6',
    'mmv/engine/comfy.py': '1bfa06ffab5b50af303f84e901db33a801034da388a0afed47dd529085b55181',
    'mmv/engine/config/injection_map.json': 'd0ebfb3b43d66011b5a0ab39a6b7c4d09abf92268f883bced7c10d31d5a12f88',
    'mmv/engine/config/seedance_rate_card.json': '1bb59cee0ee738d3fb215466658330d7481935c27c16b1deebc590576edeffdb',
    'mmv/engine/grid.py': '6dcee9e9908169570ffa3d23f22a1cd6f5e886cdaf253483b5dcb7d8d961a302',
    'mmv/engine/plan.py': 'd364cb19c0f71471c81c114a1b102ab3289bd5f8dbe7fe77209a1ca75431ef4e',
    'mmv/engine/prompts/ident_base.md': '48af7f534bf41de6fc97b9de7a99b28d3080ef1e578772f07a5c03bbcdd4c8f8',
    'mmv/engine/prompts/writer_base.md': '6e9014a80ad8f34382646ff85ea23a9e36fd883e1b7aa413c2b132740c18932b',
    'mmv/engine/schema.py': '2e3a31c62bbf32578eed863f26b03eee54b0592b66ee2fa85ac721fa1f579433',
    'mmv/engine/style.py': 'cc593970ff8425fb941f403450fb8b579939cd9e8b59080d92d05425c1dc5fde',
    'mmv/engine/validators/base.py': '187d125f476ea9360c58d189cb69f1464b043e4bebe2b66ed3ddfe79865e471c',
    'mmv/engine/validators/laya/VENDOR.md': '6a9074f1533a3450fbb05ea3b760d826337b7bf8d483189e22608465287e83bb',
    'mmv/engine/validators/laya/rl_agent_api.py': 'be3b46819c9999c3ef88e0f2ecf6d3ab1cdfed1d9a8b466fc89811e34d44031b',
    'mmv/engine/validators/laya/rl_common.py': '8d83611d480c971d640a7b7d3aa2f2219c5e8455e9cc2329fd073681bd8be23e',
    'mmv/engine/validators/laya_semantic.py': 'f0286df48cb7307288a789f631f9b31d603d618d94fe5c78ca20c11d11d25a89',
    'mmv/engine/workflows/h3_ref2video_audionodeadded.json': '183464728c108a17f0205519cf3340d76118c6a8e9d58313ceb47664e16acc88',
    'mmv/engine/writer.py': '74a5be66b04df8fff9f73a978514c7c76f7b97da4e893086aa392957b9922a35',
}
TEXTS = {
    'mmv.lipsync.SINGING_RULES': 'a7c7a803b6351c343bff026f2f22d1aae0c11cb5c850cf7618d3e65a782c1089',
    'mmv.lipsync.SINGING_AUDIO_SENTENCE': '2782c8257fadde58a12aab915154dc986a48fb0e4ab832f10116f182364bfc73',
    'mmv.lipsync.SINGER_DIRECTION': '75943205e897298aee4b7d3afcab75517d83d309f108a27b7a460781b312b15c',
    'mmv.engine.style.SILENT_MOUTHS_RULE_V013': '2904796f77225092b5bb10b6c292ab5324ed1897d317725d146cbb57809851a2',
    'mmv.engine.style.NATURAL_MOUTHS_RULE': 'dac52afa6f0e5e851b10d2199d5749618fd4df336a2ac789a1375e5c2051ca8c',
    'mmv.engine.schema.RIGGING_TAIL': '36a5bb24d64cac5ed41f0bf8992d3e869ae9961d00e697df89e39572136f174a',
    'mmv.quality.WRITER_RULES': '1f852a348cd514205b218ad64145458295f3833f39147b8922f7e7334ff8be00',
}
BEHAVIORS = {
    'composed writer prompt (sealed mouths)': '9e452f30fc1b8eff395cb9532f62a8a602098ad5922cee1cbeeae3760293a3f4',
    'composed writer prompt (natural mouths)': '8a08f1f59e438e452e54cc18bc36d57971037830f41e0575ac97e0f9ac68f4e7',
    'composed ident prompt': '48af7f534bf41de6fc97b9de7a99b28d3080ef1e578772f07a5c03bbcdd4c8f8',
}
# END PINS

LABELS = {
    'mmv/engine/prompts/writer_base.md': 'the writer prompt',
    'mmv/engine/prompts/ident_base.md': 'the ident prompt',
    'mmv/engine/schema.py': 'the prompt schema and validators',
    'mmv/engine/style.py': 'the writer prompt composer and sealed-lips rules',
    'mmv/engine/plan.py': 'the shot and montage planner',
    'mmv/engine/actor.py': 'the cast rules',
    'mmv/engine/workflows/h3_ref2video_audionodeadded.json': 'the shipped H3 workflow',
    'mmv/engine/validators/base.py': 'the prompt validators',
    'mmv.engine.style.SILENT_MOUTHS_RULE_V013': 'the sealed-lips writer rule',
    'mmv.engine.schema.RIGGING_TAIL': 'the sealed-lips closing phrase',
    'mmv.lipsync.SINGING_RULES': 'the singing wording',
}


def _digest(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def composed():
    """The writer and ident system prompts as the code actually builds them from fixed inputs. This protects the composition
    logic itself (for example that the sealed-lips rule is inserted), not only the text constants."""
    import tempfile
    from .engine import style
    with tempfile.TemporaryDirectory() as directory:
        (Path(directory) / 'aesthetic.md').write_text('AESTHETIC FIXTURE', encoding='utf-8')
        (Path(directory) / 'style_card.md').write_text('STYLE CARD FIXTURE', encoding='utf-8')
        sealed = style.compose_writer_prompt(directory, actor_block='CAST FIXTURE', restrictions=['nudity', 'blood'], silent_mouths=True)
        natural = style.compose_writer_prompt(directory, actor_block='CAST FIXTURE', restrictions=['nudity', 'blood'], silent_mouths=False,
                                              lyrics='LYRICS FIXTURE', direction='DIRECTION FIXTURE')
    return {'composed writer prompt (sealed mouths)': sealed, 'composed writer prompt (natural mouths)': natural,
            'composed ident prompt': style.compose_ident_prompt()}


def check():
    """Names of the protected items that differ from the released scheme (empty when intact). Line endings are ignored."""
    changed = []
    for path, pinned in FILES.items():
        target = ROOT / path
        if not target.is_file() or _digest(target.read_bytes()) != pinned:
            changed.append(path)
    for name, pinned in TEXTS.items():
        module, _, attribute = name.rpartition(".")
        try:
            value = getattr(importlib.import_module(module), attribute)
        except (ImportError, AttributeError):
            changed.append(name)
            continue
        if _digest(value.encode()) != pinned:
            changed.append(name)
    try:
        for name, text in composed().items():
            if _digest(text.encode()) != BEHAVIORS.get(name):
                changed.append(name)
    except Exception:                 # a broken composer is itself a change
        changed.append('prompt composition')
    return changed


def describe(changed):
    return [LABELS.get(item, item) for item in changed]


def notice():
    """A plain-language warning for the app and for exports, or None when the scheme is intact."""
    changed = check()
    if not changed:
        return None
    return ("This installation has changed Mondo's protected prompting scheme (" + ", ".join(describe(changed)) + "). "
            "Videos made with it may not meet the Mondo standard: the sealed-lips scheme, the prompt writer and its checks were tuned "
            "over many real renders. See docs/PROMPT_SCHEME_PROTECTION.md.")
