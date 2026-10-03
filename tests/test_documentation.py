"""Publication safeguards: corrupt, stale, missing or unreviewed screenshot assets."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import zlib

from scripts.check_screenshots import png_dimensions, validate

ROOT = Path(__file__).resolve().parents[1]


class ScreenshotPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = json.loads((ROOT / 'docs/assets/screenshots/manifest.json').read_text(encoding='utf-8'))
        # Use the complete coverage set; deliberately damage only the publication property under test.
        paths = {'VERSION', 'README.md', 'docs/assets/screenshots/manifest.json', 'local_control/web/index.html'}
        paths.update(self.manifest['digest_inputs'])
        paths.update(v['path'] for v in self.manifest['entries'])
        paths.update('docs/manual/' + v['chapter'] + '.md' for v in self.manifest['entries'])
        paths.update(v['guide'] for v in self.manifest['external_captures'])
        for name in paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def check(self, **kwargs):
        return validate(self.root, release=False, **kwargs)

    def save_manifest(self):
        (self.root / 'docs/assets/screenshots/manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_complete_publication_passes(self):
        self.assertEqual(self.check(), [])

    def test_ui_edit_requires_recapture(self):
        file = self.root / 'local_control/web/style.css'
        file.write_bytes(file.read_bytes() + b'\n/* changed */\n')
        self.assertTrue(any('sources changed' in v for v in self.check()))

    def test_windows_line_endings_do_not_make_unchanged_sources_stale(self):
        for name in self.manifest['digest_inputs']:
            file = self.root / name
            file.write_bytes(file.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        self.assertEqual(self.check(), [])

    def test_missing_and_unlisted_images_are_rejected(self):
        file = self.root / self.manifest['entries'][0]['path']
        file.rename(file.with_name('unreviewed.png'))
        errors = self.check()
        self.assertTrue(any('Unlisted PNG' in v for v in errors))
        self.assertTrue(any(file.name in v for v in errors))

    def test_modified_pixels_fail_checksum(self):
        file = self.root / self.manifest['entries'][0]['path']
        data = bytearray(file.read_bytes())
        data[len(data)//2] ^= 1
        file.write_bytes(data)
        self.assertTrue(any('checksum differs' in v for v in self.check()))

    def test_missing_manual_caption_is_rejected(self):
        entry = self.manifest['entries'][0]
        file = self.root / ('docs/manual/' + entry['chapter'] + '.md')
        file.write_text(file.read_text(encoding='utf-8').replace(entry['caption'], ''), encoding='utf-8')
        self.assertTrue(any('caption missing' in v for v in self.check()))

    def test_unknown_navigation_page_is_not_silently_omitted(self):
        file = self.root / 'local_control/web/index.html'
        file.write_text(file.read_text(encoding='utf-8') + '<button class="nav" data-page="new-page">New page</button>', encoding='utf-8')
        self.assertTrue(any('coverage is incomplete' in v for v in self.check()))

    def test_path_escape_is_rejected_before_reading(self):
        self.manifest['entries'][0]['path'] = '../private.png'
        self.save_manifest()
        self.assertTrue(any('Unsafe screenshot path' in v for v in self.check()))

    def test_png_text_metadata_is_rejected_even_with_matching_hash(self):
        entry = self.manifest['entries'][0]
        file = self.root / entry['path']
        data = file.read_bytes()
        body = b'tEXt' + b'Comment\x00unreviewed personal metadata'
        chunk = struct.pack('>I', len(body) - 4) + body + struct.pack('>I', zlib.crc32(body))
        data = data[:-12] + chunk + data[-12:]
        file.write_bytes(data)
        entry.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        self.save_manifest()
        self.assertTrue(any('embedded text' in v for v in self.check()))

    def test_external_mockup_cannot_be_claimed_as_completed(self):
        self.manifest['external_captures'][0]['status'] = 'complete'
        self.save_manifest()
        self.assertTrue(any('reviewed import' in v for v in self.check()))

    def test_truncated_png_is_rejected(self):
        data = (self.root / self.manifest['entries'][0]['path']).read_bytes()
        with self.assertRaises(ValueError):
            png_dimensions(data[:-12])


if __name__ == '__main__':
    unittest.main()
