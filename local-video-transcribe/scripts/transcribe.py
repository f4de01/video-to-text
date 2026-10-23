"""Local ASR and file protocol for Codex-agent repair (Python 3.9+)."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.mpeg', '.mpg', '.wmv', '.ts'}
OUTPUTS = ('transcript.md', 'changes.json')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def emit(status, **kwargs):
    print(json.dumps(dict(status=status, **kwargs), ensure_ascii=False), flush=True)


def check_model(path):
    path = Path(path).resolve()
    required = ('model.bin', 'config.json', 'tokenizer.json')
    missing = [name for name in required if not (path / name).is_file()]
    if not list(path.glob('vocabulary.*')):
        missing.append('vocabulary.*')
    if missing:
        raise ValueError('Incomplete local model: ' + ', '.join(missing))
    return path


def prepare(args):
    if args.model.endswith('.en'):
        raise ValueError('Use a multilingual model for Chinese and English.')
    from faster_whisper.utils import download_model
    path = download_model(args.model, output_dir=str(Path(args.model_dir).resolve()))
    check_model(path)
    emit('prepared', model_dir=path)


def within(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def completed(destination, key):
    if not destination.exists():
        return False
    marker = destination / 'complete.json'
    if marker.is_file():
        data = read(marker)
        if data.get('key') == key and all(
            (destination / name).is_file()
            and digest(destination / name) == data.get('hashes', {}).get(name)
            for name in OUTPUTS
        ):
            return True
    raise ValueError('Output exists but is incomplete or edited; choose another output directory: ' + str(destination))


def chunks_for(segments, limit):
    groups, group, size = [], [], 0
    for segment in segments:
        length = len(segment['text'])
        if group and size + length > limit:
            groups.append(group)
            group, size = [], 0
        group.append(segment)
        size += length
    if group:
        groups.append(group)
    offset = 0
    for group in groups:
        yield dict(segments=group, context_before=segments[max(0, offset - 2):offset],
                   context_after=segments[offset + len(group):offset + len(group) + 2])
        offset += len(group)


def recognize(model, video, language):
    """Keep pauses as recognition boundaries instead of concatenating languages."""
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    sample_rate = 16000
    audio = decode_audio(str(video), sampling_rate=sample_rate)
    regions = get_speech_timestamps(audio, VadOptions(
        min_silence_duration_ms=1200, max_speech_duration_s=20, speech_pad_ms=200))
    segments, languages = [], []
    for region in regions:
        offset = region['start'] / sample_rate
        end_limit = region['end'] / sample_rate
        generated, info = model.transcribe(
            audio[region['start']:region['end']], task='transcribe',
            language=None if language == 'auto' else language, multilingual=language == 'auto',
            beam_size=1, best_of=1, temperature=0, vad_filter=False,
            condition_on_previous_text=False)
        if info.language not in languages:
            languages.append(info.language)
        for segment in generated:
            start, end = float(segment.start), float(segment.end)
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                raise ValueError('ASR returned invalid timestamps')
            start = max(offset + start, segments[-1]['end'] if segments else 0)
            end = min(offset + end, end_limit)
            if start >= end:
                raise ValueError('ASR returned a segment outside its audio region; retry with a larger model')
            segments.append(dict(id=len(segments), start=start, end=end, text=segment.text.strip()))
    return segments, languages


def transcribe(args):
    cfg = read(args.config)
    source = Path(args.input).resolve()
    output = Path(args.output).resolve()
    if not source.exists():
        raise ValueError('Input does not exist: ' + str(source))
    if source.is_dir() and within(source, output):
        raise ValueError('Output must not equal or contain the input directory.')
    model_dir = check_model(args.model_dir)
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    device = args.device or cfg['device']
    compute = args.compute_type or cfg['compute_type']
    language = args.language or cfg['language']
    repair_model = args.repair_model or cfg['repair_model']
    effort = args.repair_effort or cfg['repair_reasoning_effort']
    chunk_chars = int(cfg['chunk_chars'])
    if chunk_chars < 100:
        raise ValueError('chunk_chars must be at least 100')
    options = dict(model_dir=str(model_dir), device=device, compute_type=compute,
                   language=language, repair_model=repair_model, repair_effort=effort,
                   repair=not args.no_repair, chunk_chars=chunk_chars, protocol=3,
                   model_hashes={p.name: digest(p) for p in sorted(model_dir.iterdir())
                                 if p.is_file() and (p.name in {'model.bin', 'config.json', 'tokenizer.json'}
                                                     or p.name.startswith('vocabulary.'))})
    if source.is_file():
        files = [source] if source.suffix.lower() in EXTENSIONS else []
    else:
        iterator = source.rglob('*') if args.recursive else source.iterdir()
        files = sorted(p for p in iterator if p.is_file() and p.suffix.lower() in EXTENSIONS
                       and not within(p, output))
    if not files:
        raise ValueError('No supported video files found.')
    output.mkdir(parents=True, exist_ok=True)
    model = None
    failures = 0
    for video in files:
        try:
            identity = dict(source=str(video), sha256=digest(video), options=options)
            key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            stem = re.sub(r'[^\w.-]', '_', video.stem, flags=re.UNICODE)[:50]
            destination = output / ('video-' + stem + '-' + key[:16])
            job = output / '.work' / key
            if completed(destination, key):
                if (job / 'job.json').is_file():
                    clean_job(job)
                emit('skipped', source=str(video), output=str(destination))
                continue
            if (job / 'job.json').is_file():
                if args.no_repair:
                    finalize_job(job, unreviewed=True)
                    emit('completed_unreviewed', source=str(video), output=str(destination))
                else:
                    emit('pending', source=str(video), job=str(job), resumed=True)
                continue
            if model is None:
                from faster_whisper import WhisperModel
                model = WhisperModel(str(model_dir), device=device, compute_type=compute,
                                     local_files_only=True)
                if not model.model.is_multilingual:
                    raise ValueError('English-only model cannot support Chinese.')
            segments, languages = recognize(model, video, language)
            if digest(video) != identity['sha256']:
                raise ValueError('Source changed during transcription; retry when stable.')
            job.mkdir(parents=True, exist_ok=True)
            groups = list(chunks_for(segments, chunk_chars))
            for index, group in enumerate(groups):
                write(job / ('chunk-%05d.json' % index), group)
            write(job / 'job.json', dict(key=key, identity=identity, destination=str(destination),
                                        chunks=len(groups), segments=len(segments),
                                        chunk_hashes=[digest(job / ('chunk-%05d.json' % i))
                                                      for i in range(len(groups))],
                                        detected_languages=languages))
            if args.no_repair:
                finalize_job(job, unreviewed=True)
                emit('completed_unreviewed', source=str(video), output=str(destination))
            else:
                emit('pending', source=str(video), job=str(job), chunks=len(groups))
        except Exception as exc:
            failures += 1
            emit('error', source=str(video), error=str(exc))
    return 1 if failures else 0


def render_markdown(source, texts):
    title = Path(source).stem.replace('\n', ' ').replace('\r', ' ')
    paragraphs = '\n\n'.join(text for text in texts if text.strip())
    return '# ' + title + '\n\n' + (paragraphs + '\n' if paragraphs else '（未检测到语音）\n')


def validate_repair(original, repaired):
    if not isinstance(repaired, dict) or set(repaired) != {'segments'}:
        raise ValueError('Repair must contain only segments')
    rows = repaired['segments']
    if not isinstance(rows, list) or len(rows) != len(original):
        raise ValueError('Repair segment count changed')
    for src, row in zip(original, rows):
        if not isinstance(row, dict) or set(row) != {'id', 'text', 'reason', 'issues'}:
            raise ValueError('Repair fields must be id/text/reason/issues')
        if type(row['id']) is not int or row['id'] != src['id']:
            raise ValueError('Repair IDs changed or reordered')
        if not isinstance(row['text'], str) or not isinstance(row['reason'], str):
            raise ValueError('Text and reason must be strings')
        if src['text'].strip() and not row['text'].strip():
            raise ValueError('Repair removed nonempty text')
        if not src['text'].strip() and row['text'].strip():
            raise ValueError('Repair invented text for empty segment')
        if '\n' in row['text'] or '\r' in row['text'] or '\x00' in row['text']:
            raise ValueError('Each repaired segment must be one text line')
        if not isinstance(row['issues'], list) or not all(isinstance(x, str) for x in row['issues']):
            raise ValueError('Issues must be a list of strings')
        if row['text'] != src['text'] and not row['reason'].strip():
            raise ValueError('Changed segment needs a reason')
    return rows


def load_job(path):
    path = Path(path).resolve()
    if path.parent.name != '.work' or not re.fullmatch(r'[0-9a-f]{64}', path.name):
        raise ValueError('Expected an owned .work/<job hash> directory')
    data = read(path / 'job.json')
    if data['key'] != path.name:
        raise ValueError('Job identity mismatch')
    destination = Path(data['destination']).resolve()
    if destination.parent != path.parent.parent or not destination.name.startswith('video-'):
        raise ValueError('Job destination must be a result folder beside .work')
    return path, data, destination


def clean_job(path):
    path, _, _ = load_job(path)
    # load_job resolves and verifies the exact owned directory before recursive deletion.
    shutil.rmtree(path)


def finalize_job(path, unreviewed=False):
    path, data, destination = load_job(path)
    if completed(destination, data['key']):
        clean_job(path)
        return destination
    if unreviewed and data['identity']['options']['repair']:
        raise ValueError('This job requires agent repair')
    all_segments, changes = [], []
    for index in range(data['chunks']):
        chunk_path = path / ('chunk-%05d.json' % index)
        if digest(chunk_path) != data['chunk_hashes'][index]:
            raise ValueError('Original chunk modified; regenerate the job before repair')
        original = read(chunk_path)['segments']
        if unreviewed:
            repaired = [dict(id=x['id'], text=x['text'], reason='', issues=[]) for x in original]
        else:
            repaired = validate_repair(original, read(path / ('repair-%05d.json' % index)))
        for src, row in zip(original, repaired):
            if src['id'] != len(all_segments):
                raise ValueError('Original segment IDs are not contiguous')
            if not (math.isfinite(src['start']) and math.isfinite(src['end'])
                    and 0 <= src['start'] <= src['end']):
                raise ValueError('Invalid source timestamp')
            all_segments.append(dict(src, text=row['text']))
            if row['text'] != src['text'] or row['issues']:
                changes.append(dict(id=src['id'], start=src['start'], end=src['end'],
                                    reason=row['reason'], issues=row['issues']))
    if len(all_segments) != data['segments']:
        raise ValueError('Total segment count mismatch')
    stage = path / 'publish'
    stage.mkdir(exist_ok=True)
    text = render_markdown(data['identity']['source'], [x['text'] for x in all_segments])
    (stage / 'transcript.md').write_text(text, encoding='utf-8')
    write(stage / 'changes.json', dict(reviewed=not unreviewed, changes=changes))
    write(stage / 'complete.json', dict(key=data['key'], source=data['identity']['source'],
        source_sha256=data['identity']['sha256'], options=data['identity']['options'],
        reviewed=not unreviewed, no_speech=not all_segments,
        hashes={name: digest(stage / name) for name in OUTPUTS}))
    # Same filesystem rename publishes the validated set without partial final files.
    stage.rename(destination)
    clean_job(path)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare', help='Download model (network enabled)')
    p.add_argument('--model', default=read(ROOT / 'config.json')['asr_model'])
    p.add_argument('--model-dir', required=True)
    p = sub.add_parser('transcribe', help='Offline ASR; emit pending jobs for Codex agents')
    p.add_argument('input')
    p.add_argument('--model-dir', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--config', default=str(ROOT / 'config.json'))
    p.add_argument('--recursive', action='store_true')
    p.add_argument('--device', choices=['cpu', 'cuda'])
    p.add_argument('--compute-type', choices=['int8', 'float16', 'float32', 'int8_float16'])
    p.add_argument('--language', choices=['auto', 'zh', 'en'])
    p.add_argument('--repair-model')
    p.add_argument('--repair-effort')
    p.add_argument('--no-repair', action='store_true')
    p = sub.add_parser('finalize', help='Validate agent repairs, publish and remove intermediates')
    p.add_argument('job')
    p = sub.add_parser('clean', help='Remove an owned temporary job without publishing')
    p.add_argument('job')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args)
        elif args.command == 'transcribe':
            return transcribe(args)
        elif args.command == 'finalize':
            _, data, _ = load_job(args.job)
            destination = finalize_job(args.job, unreviewed=not data['identity']['options']['repair'])
            emit('completed', output=str(destination))
        else:
            clean_job(args.job)
            emit('cleaned', job=args.job)
        return 0
    except Exception as exc:
        emit('error', error=str(exc))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
