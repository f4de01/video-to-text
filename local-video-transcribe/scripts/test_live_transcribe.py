"""Opt-in real model regression: set TEST_MODEL_DIR and TEST_MIXED_VIDEO.

Fixture must contain Chinese '大家好', English 'local video transcription',
and English speech after 25 seconds, as in the recorded synthetic smoke test.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import transcribe as app


@unittest.skipUnless(os.environ.get('TEST_MODEL_DIR') and os.environ.get('TEST_MIXED_VIDEO'),
                     'Real model and mixed-language video not provided')
class LiveTranscription(unittest.TestCase):
    def test_both_languages_and_bounded_timestamps(self):
        import av
        with av.open(os.environ['TEST_MIXED_VIDEO']) as video:
            duration = video.duration / av.time_base
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('transcribe.py')),
                'transcribe', os.environ['TEST_MIXED_VIDEO'], '--model-dir', os.environ['TEST_MODEL_DIR'],
                '--output', output, '--no-repair'], capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = next(Path(output).glob('video-*/transcript.md')).read_text(encoding='utf-8')
            self.assertIn('大家好', text)
            self.assertIn('local video transcription', text.lower())
            self.assertIn('original english words', text.lower())
            self.assertFalse(list(Path(output).glob('video-*/*.srt')))
            self.assertFalse(list(Path(output).glob('video-*/*.txt')))
        from faster_whisper import WhisperModel
        model = WhisperModel(os.environ['TEST_MODEL_DIR'], device='cpu', compute_type='int8', local_files_only=True)
        segments, _ = app.recognize(model, os.environ['TEST_MIXED_VIDEO'], 'auto')
        self.assertTrue(all(0 <= s['start'] <= s['end'] <= duration + 0.05 for s in segments))
        self.assertGreater(segments[-1]['end'], 25)


if __name__ == '__main__':
    unittest.main()
