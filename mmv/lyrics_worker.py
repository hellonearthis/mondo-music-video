"""Standalone Whisper transcription worker: python lyrics_worker.py AUDIO OUT.json MODEL [DOWNLOAD_ROOT].

Runs in whichever Python has openai-whisper installed (it imports nothing from this project), writes
word timings as JSON, and never downloads a model unless the caller already approved that.
"""
import json
import os
import sys


def main(audio, out, model_name, root=None, device=None):
    import torch
    import whisper
    device = device if device in ('cuda', 'cpu') and (device == 'cpu' or torch.cuda.is_available()) else (
        'cuda' if torch.cuda.is_available() else 'cpu')
    model = whisper.load_model(model_name, device=device, download_root=root or None)
    result = model.transcribe(audio, word_timestamps=True, condition_on_previous_text=False, fp16=device == 'cuda')
    words = [{'word': w['word'].strip(), 'start': round(float(w['start']), 3), 'end': round(float(w['end']), 3)}
             for segment in result['segments'] for w in segment.get('words', []) if w['word'].strip()]
    temp = out + '.tmp'
    with open(temp, 'w', encoding='utf-8') as stream:
        json.dump({'language': result.get('language'), 'model': model_name, 'device': device, 'words': words}, stream)
    os.replace(temp, out)


if __name__ == '__main__':
    main(*sys.argv[1:6])
