"""Suite-wide guards: no test reads a real GPU, and a worker's Laya device override never leaks between tests."""
import pytest

from mmv import gpu_memory

REAL_GPU_MEMORY = gpu_memory.gpu_memory  # for tests of the reader itself, which inject a fake nvidia-smi


@pytest.fixture(autouse=True)
def no_real_gpu_and_no_leaked_override(monkeypatch):
    monkeypatch.setenv('MMV_LAYA_DEVICE_OVERRIDE', '')  # undone after each test; '' is not an override
    monkeypatch.setattr('mmv.gpu_memory.gpu_memory', lambda *a, **k: None)
