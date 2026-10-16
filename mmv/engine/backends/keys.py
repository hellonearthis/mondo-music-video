"""Credential adapter for the extracted renderers; no studio key cabinet."""
import re
from ...storage import Storage
_SECRETS = set()
class KeyNotFound(ValueError): pass
def register_secret(provider, key):
    if key: _SECRETS.add(key)
def get_api_key(provider, **kwargs):
    name = "WAVESPEED_API_KEY" if provider == "wavespeed" else "MMV_WRITER_API_KEY"
    key = Storage().key(name)
    if not key: raise KeyNotFound("Configure " + name + " in Settings")
    register_secret(provider, key)
    return key, "public app settings/environment"
def redact(text):
    text = str(text)
    for key in _SECRETS: text = text.replace(key, "[redacted]")
    return re.sub(r"(Bearer\s+)\S+", r"\1[redacted]", text)
