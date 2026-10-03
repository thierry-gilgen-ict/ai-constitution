"""Publication boundaries are tested with synthetic data and offline scanners."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import releases, scan_publication as security
from scripts.package_local import prepare_output


class Publication(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def inventory(self, names):
        path = self.root / releases.INVENTORY
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'schema_version': 1, 'files': sorted(names)}))

    def test_export_includes_only_declared_files_even_when_private_file_is_present(self):
        (self.root / 'VERSION').write_text('0.0.0')
        (self.root / 'local_control').mkdir()
        (self.root / 'local_control/credentials.json').write_text('Synthetic private placeholder')
        (self.root / 'local_control/extra.py').write_text('Unreviewed source')
        self.inventory(['VERSION', releases.INVENTORY])
        output = self.root / 'release.zip'
        releases.export(self.root, output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {'VERSION', releases.INVENTORY, 'release-manifest.json'})

    def test_inventory_rejects_private_names_and_case_variants(self):
        for name in ('local_control/credentials.json', 'docs/Auth.JSON', 'scripts/config.json',
                     'templates/.env.example', 'docs/server-key.pem', 'scripts/secrets/key.txt'):
            with self.subTest(name=name):
                self.assertFalse(releases.allowed(name))
                self.inventory(['VERSION', releases.INVENTORY, name])
                with self.assertRaisesRegex(ValueError, 'unsafe'):
                    releases.public_files(self.root)
        self.assertTrue(releases.allowed('local_control/credentials.py'))
        self.assertFalse(releases.allowed(None))

    def test_force_added_private_filename_is_rejected_without_a_key_pattern(self):
        from scripts.constitution import scan
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        (self.root / 'Credentials.json').write_text('Synthetic placeholder')
        subprocess.run(['git', 'add', 'Credentials.json'], cwd=self.root, check=True)
        result = scan(self.root)
        self.assertEqual(result['findings'], [{'file':'Credentials.json', 'rule':'private-file'}])

    def test_missing_and_duplicate_inventory_inputs_fail_closed(self):
        self.inventory(['VERSION', releases.INVENTORY])
        with self.assertRaisesRegex(ValueError, 'missing file'):
            releases.public_files(self.root)
        self.inventory(['VERSION', 'VERSION', releases.INVENTORY])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            releases.public_files(self.root)

    def test_existing_build_output_is_preserved_and_empty_output_is_accepted(self):
        output = self.root / 'package'; output.mkdir()
        path = output / 'stale.txt'; path.write_bytes(b'Keep existing files')
        with self.assertRaisesRegex(ValueError, 'must be empty'):
            prepare_output(output)
        self.assertEqual(path.read_bytes(), b'Keep existing files')
        fresh = self.root / 'fresh'
        self.assertEqual(prepare_output(fresh), fresh)

    def test_build_output_cannot_be_inside_public_source(self):
        with patch('scripts.package_local.ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'outside public'):
                prepare_output(self.root / 'local_control/new-output')
            with self.assertRaisesRegex(ValueError, 'outside public'):
                prepare_output(self.root / '.local/../local_control/new-output')
        self.assertFalse((self.root / 'local_control').exists())

    def zip(self, name, members):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            for member, data in members.items(): archive.writestr(member, data)
        return path

    def test_private_filename_nested_inside_zip_is_rejected(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w') as archive:
            archive.writestr('library/Credentials.json', 'Synthetic placeholder')
        path = self.zip('outer.zip', {'inner.zip': inner.getvalue()})
        with self.assertRaisesRegex(ValueError, 'Private filename'):
            security.inspect_sources([path])

    def test_archive_traversal_duplicates_and_links_are_rejected(self):
        for name in ('../escape.txt', 'C:/outside.txt'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError): security.inspect_sources([self.zip('bad.zip', {name:'fixture'})])
        path = self.zip('duplicate.zip', {'A.txt':'one','a.txt':'two'})
        with self.assertRaises(ValueError): security.inspect_sources([path])
        # Windows ZipInfo normalizes separators; construct the unsafe headers explicitly.
        path = self.zip('separator.zip', {'folder/outside.txt':'fixture'})
        path.write_bytes(path.read_bytes().replace(b'folder/outside.txt', b'folder\\outside.txt'))
        with self.assertRaises(ValueError): security.inspect_sources([path])
        path = self.root / 'link.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            info = zipfile.ZipInfo('link.txt'); info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, 'outside')
        with self.assertRaises(ValueError): security.inspect_sources([path])

    def test_overdeep_archive_is_rejected_instead_of_silently_skipped(self):
        data = b'fixture'
        for depth in range(security.MAX_DEPTH + 1):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                archive.writestr('inner.zip' if depth else 'safe.txt', data)
            data = stream.getvalue()
        path = self.root / 'deep.zip'; path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'nesting'):
            security.inspect_sources([path])

    def checksum(self, nested=False):
        body = b'Public credential management source'
        value = hashlib.sha256(body).hexdigest()
        document = {'files': {'local_control/credentials.py': value}}
        raw = json.dumps(document, indent=2)
        line_number, line = next((i,l) for i,l in enumerate(raw.splitlines(), 1) if value in l)
        matched = line[line.index('credentials.py'):].rstrip(',')
        outer = self.zip('worker.zip', {'manifest.json':raw,'app/local_control/credentials.py':body})
        chain = str(outer) + '!manifest.json'
        if nested:
            outer = self.zip('artifact.zip', {'worker.zip':outer.read_bytes()})
            chain = str(outer) + '!worker.zip!manifest.json'
        return {'RuleID':'generic-api-key', 'File':chain, 'StartLine':line_number,'EndLine':line_number,
                'StartColumn':line.index('credentials.py')+1, 'EndColumn':len(line.rstrip(','))+1,
                'Match':matched.replace(value,'REDACTED'),'Secret':'REDACTED'}

    def test_real_payload_checksum_is_verified_inside_nested_archives(self):
        self.assertTrue(security.checksum_finding(self.checksum()))
        self.assertTrue(security.checksum_finding(self.checksum(nested=True)))

    def test_standalone_manifest_has_the_same_payload_verification(self):
        finding = self.checksum()
        with zipfile.ZipFile(self.root / 'worker.zip') as archive:
            for name in archive.namelist():
                path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))
        finding['File'] = str(self.root / 'manifest.json')
        self.assertTrue(security.checksum_finding(finding))
        (self.root / 'app/local_control/credentials.py').write_bytes(b'Changed')
        self.assertFalse(security.checksum_finding(finding))

    def test_manifest_digest_cannot_hide_a_different_secret_on_same_line(self):
        finding = self.checksum()
        finding['Match'] = 'REDACTED file name'
        self.assertFalse(security.checksum_finding(finding))
        finding = self.checksum(); finding['RuleID'] = 'github-pat'
        self.assertFalse(security.checksum_finding(finding))
        finding = self.checksum(); finding['Match'] += 'REDACTED'
        self.assertFalse(security.checksum_finding(finding))

    def test_changed_packaged_file_invalidates_checksum_exception(self):
        finding = self.checksum()
        with zipfile.ZipFile(self.root / 'worker.zip') as archive:
            raw = archive.read('manifest.json')
        self.zip('worker.zip', {'manifest.json':raw, 'app/local_control/credentials.py':b'Changed'})
        self.assertFalse(security.checksum_finding(finding))

    def fake_scan(self, rows, status=1):
        def run(command, **kwargs):
            report = Path(command[command.index('--report-path') + 1])
            report.write_text(json.dumps(rows))
            return subprocess.CompletedProcess(command, status, b'withheld synthetic stdout', b'withheld synthetic stderr')
        return run

    def test_scanner_findings_block_upload_without_printing_values(self):
        path = self.root / 'safe.txt'; path.write_text('fixture')
        secret = 'synthetic sensitive value'
        finding = {'RuleID':'github-pat','File':str(path),'StartLine':1,'Secret':secret,'Match':secret}
        output = io.StringIO()
        with patch.object(security.subprocess,'run',side_effect=self.fake_scan([finding])), contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(ValueError,'upload blocked'): security.scan([path], 'gitleaks')
        self.assertNotIn(secret, output.getvalue())
        self.assertIn('github-pat', output.getvalue())

    def test_scanner_failure_or_inconsistent_report_blocks_upload(self):
        path = self.root / 'safe.txt'; path.write_text('fixture')
        for status in (1, 2):
            with self.subTest(status=status), patch.object(security.subprocess,'run',side_effect=self.fake_scan([], status)):
                with self.assertRaises(ValueError): security.scan([path], 'gitleaks')

    def test_scanner_accepts_only_verified_checksum_findings(self):
        finding = self.checksum()
        with patch.object(security.subprocess,'run',side_effect=self.fake_scan([finding])):
            result = security.scan([self.root / 'worker.zip'], 'gitleaks')
        self.assertEqual(result['verified_checksum_flags'], 1)
