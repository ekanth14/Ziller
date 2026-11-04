"""Report security tests. Findings never include sensitive text or offsets."""
from pathlib import Path
import pytest
from cryptoscope.security.report_secrets import scan, violations, redact
from cryptoscope.security.report_secrets import redact_document
import json


def test_reports_and_logs_contain_zero_secret_fragments():
    result = scan(Path.cwd())
    assert not result['findings'], 'Confidential report scan failed; run the safe scanner for file identifiers.'


@pytest.mark.parametrize('text', [
    'fictional-boundary-fixture', 'fict', 'ture',
    'API key starts with an example', 'The secret is 64 characters long',
    'Credential prefix is documented', 'ABCD...WXYZ',
    'The keys are 64 characters long', 'Credentials have length 42',
    'The tokens end with an example', 'Password first 4 are described',
    'api_key_length: 64', 'credentials_valid_characters: true', 'secret_suffix_position: 3',
])
def test_sensitive_report_examples_are_refused(text):
    assert bool(violations(text, {'fictional-boundary-fixture'}))


def test_redaction_is_idempotent_and_does_not_return_sensitive_matches(tmp_path):
    (tmp_path / '.env').write_text('API_KEY=fictional-boundary-fixture\n')
    directory = tmp_path / 'reports'
    directory.mkdir()
    report = directory / 'PHASE_1_REPORT.md'
    report.write_text('fict and ture and fictional-boundary-fixture\nAPI key starts with an example\n')
    result = scan(tmp_path)
    assert result['files_scanned'] == 1
    assert len(result['findings']) == 1
    assert set(result['findings'][0]) == {'path', 'rules'}
    text = redact(report.read_text(), {'fictional-boundary-fixture'})
    assert not violations(text, {'fictional-boundary-fixture'})
    assert redact(text, {'fictional-boundary-fixture'}) == text


def test_structured_redaction_preserves_json_and_repairs_only_withheld_tokens():
    fictional = {'1234-fictional-5678'}
    safe = redact_document('{"price":1234.25,"retained":42,"text":"1234"}', fictional, '.json')
    value = json.loads(safe)
    assert value['price'] is None
    assert value['retained'] == 42
    assert value['text'] == '[REDACTED]'
    assert value['security_redactions']['withheld_values'] == 2
    repaired = json.loads(redact_document('{"price":123[REDACTED].25,"retained":42}', fictional, '.json'))
    assert repaired['price'] is None
    assert repaired['retained'] == 42
    with pytest.raises(ValueError):
        redact_document('{unrelated invalid document', fictional, '.json')


def test_structured_credential_descriptions_are_removed_with_their_values():
    safe = redact_document('{"api_key_length":64,"retained":42}', set(), '.json')
    value = json.loads(safe)
    assert 'api_key_length' not in value
    assert value['redacted_field_0'] == '[REDACTED]'
    assert value['retained'] == 42
    assert not violations(safe, set())
