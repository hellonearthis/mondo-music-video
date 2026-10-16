🪿 MGL VENDORED — Laya inference modules

Source: https://huggingface.co/convaiinnovations/laya — Apache 2.0,
Convai Innovations. Vendored from the devtools/laya checkout at commit
c5d7873 ("Add the Laya logo and use the lockup in the model card").

Files — BYTE-IDENTICAL to upstream, sha256-verified at vendor time:

  rl_common.py     8d83611d480c971d640a7b7d3aa2f2219c5e8455e9cc2329fd073681bd8be23e
  rl_agent_api.py  be3b46819c9999c3ef88e0f2ecf6d3ab1cdfed1d9a8b466fc89811e34d44031b

These modules are loaded flat (sys.path insert) INSIDE the laya_semantic
seam and are never edited. Upgrade path: re-copy from the checkout, re-
verify these hashes, update this receipt.

The weights are NOT vendored — they stage into models/laya/ (gitignored).