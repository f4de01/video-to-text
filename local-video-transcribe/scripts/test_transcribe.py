"""File protocol tests; ASR stub does not assert real speech accuracy."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import transcribe as app


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def job(self, key='a' * 64):
        job = self.root / '.work' / key
        job.mkdir(parents=True)
        destination = self.root / ('video-test-' + key[:16])
        original = [dict(id=0, start=0.2, end=1.9996, text='你好 word')]
        app.write(job / 'chunk-00000.json', dict(segments=original))
        app.write(job / 'repair-00000.json', dict(segments=[
            dict(id=0, text='你好 world。', reason='英文识别及标点修正', issues=[])]))
        app.write(job / 'job.json', dict(key=key, destination=str(destination), chunks=1, segments=1,
            chunk_hashes=[app.digest(job / 'chunk-00000.json')],
            identity=dict(source='sample.mp4', sha256='test', options=dict(repair=True))))
        return job, destination

    def test_publish_only_corrected_outputs_and_remove_raw(self):
        job, destination = self.job()
        app.finalize_job(job)
        self.assertFalse(job.exists())
        self.assertEqual((destination / 'transcript.md').read_text(encoding='utf-8'), '# sample\n\n你好 world。\n')
        self.assertFalse((destination / 'transcript.txt').exists())
        self.assertFalse((destination / 'subtitles.srt').exists())
        self.assertNotIn('你好 word', (destination / 'changes.json').read_text(encoding='utf-8'))
        self.assertTrue(app.completed(destination, 'a' * 64))
        (destination / 'transcript.md').write_text('user edit', encoding='utf-8')
        with self.assertRaises(ValueError):
            app.completed(destination, 'a' * 64)

    def test_invalid_repair_never_publishes(self):
        job, destination = self.job()
        app.write(job / 'repair-00000.json', dict(segments=[]))
        with self.assertRaises(ValueError):
            app.finalize_job(job)
        self.assertFalse(destination.exists())
        self.assertTrue((job / 'chunk-00000.json').exists())

    def test_modified_original_timeline_is_rejected(self):
        job, destination = self.job()
        chunk = app.read(job / 'chunk-00000.json')
        chunk['segments'][0]['start'] = 0.9
        app.write(job / 'chunk-00000.json', chunk)
        with self.assertRaises(ValueError):
            app.finalize_job(job)
        self.assertFalse(destination.exists())

    def test_repair_cannot_change_ids_or_timestamps(self):
        source = [dict(id=0, text='hello')]
        for row in [dict(id=1, text='hello', reason='', issues=[]),
                    dict(id=0, text='hello', reason='', issues=[], start=9),
                    dict(id=0, text='', reason='delete', issues=[]),
                    dict(id=0, text='hi', reason='', issues=[])]:
            with self.assertRaises(ValueError):
                app.validate_repair(source, dict(segments=[row]))

    def test_clean_rejects_non_job_and_external_destination(self):
        with self.assertRaises(ValueError):
            app.clean_job(self.root)
        job, _ = self.job()
        data = app.read(job / 'job.json')
        data['destination'] = str(self.root.parent / 'video-outside')
        app.write(job / 'job.json', data)
        with self.assertRaises(ValueError):
            app.clean_job(job)
        self.assertTrue(job.exists())

    def test_chunks_have_context_without_duplicate_target_ids(self):
        segments = [dict(id=i, text='a' * 50) for i in range(8)]
        chunks = list(app.chunks_for(segments, 100))
        self.assertEqual([s['id'] for c in chunks for s in c['segments']], list(range(8)))
        self.assertEqual([s['id'] for s in chunks[1]['context_before']], [0, 1])
        self.assertEqual([s['id'] for s in chunks[1]['context_after']], [4, 5])

    def test_silence_produces_empty_valid_outputs(self):
        job, destination = self.job()
        data = app.read(job / 'job.json')
        data.update(chunks=0, segments=0)
        app.write(job / 'job.json', data)
        app.finalize_job(job)
        self.assertIn('未检测到语音', (destination / 'transcript.md').read_text(encoding='utf-8'))
        self.assertFalse((destination / 'subtitles.srt').exists())
        self.assertTrue(app.read(destination / 'complete.json')['no_speech'])

    def test_batch_continues_after_failure_and_same_names_do_not_collide(self):
        inputs = self.root / 'input'
        for name in ['a/同名.mp4', 'b/同名.mp4', 'bad.mp4']:
            file = inputs / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(name.encode())
        models = self.root / 'model'
        models.mkdir()
        for name in ['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.json']:
            (models / name).write_text('{}', encoding='utf-8')

        class FakeModel:
            def __init__(self, *args, **kwargs):
                assert kwargs['local_files_only'] is True
                self.model = types.SimpleNamespace(is_multilingual=True)

            def transcribe(self, path, **kwargs):
                if Path(path).name == 'bad.mp4':
                    raise ValueError('bad video')
                return iter([types.SimpleNamespace(start=0, end=1, text='你好 hello')]), types.SimpleNamespace(language='zh')

        args = argparse.Namespace(config=str(app.ROOT / 'config.json'), input=str(inputs),
            output=str(self.root / 'output'), model_dir=str(models), device=None,
            compute_type=None, language=None, repair_model=None, repair_effort=None,
            no_repair=False, recursive=True)
        events = []
        def fake_recognize(model, video, language):
            generated, info = model.transcribe(str(video))
            return [dict(id=i, start=s.start, end=s.end, text=s.text)
                    for i, s in enumerate(generated)], [info.language]
        with patch.dict(sys.modules, {'faster_whisper': types.SimpleNamespace(WhisperModel=FakeModel)}), \
             patch.object(app, 'recognize', side_effect=fake_recognize), \
             patch.object(app, 'emit', side_effect=lambda status, **kw: events.append(dict(status=status, **kw))):
            self.assertEqual(app.transcribe(args), 1)
            jobs = [x['job'] for x in events if x['status'] == 'pending']
            self.assertEqual(len(set(jobs)), 2)
            for job in jobs:
                rows = app.read(Path(job) / 'chunk-00000.json')['segments']
                app.write(Path(job) / 'repair-00000.json', dict(segments=[
                    dict(id=x['id'], text=x['text'], reason='', issues=[]) for x in rows]))
                app.finalize_job(job)
            events.clear()
            self.assertEqual(app.transcribe(args), 1)
            self.assertEqual(sum(x['status'] == 'skipped' for x in events), 2)


if __name__ == '__main__':
    unittest.main()
