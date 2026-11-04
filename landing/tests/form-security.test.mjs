import { test } from 'node:test';
import assert from 'node:assert/strict';
import { issueOperatorCookie, verifyOperatorCookie, matchesOperatorPasscode,
  allowSubmission, validateProposal, sameOrigin, jsonForScript } from '../lib/server/form-security.ts';

const valid = () => ({ name: 'Fixture Researcher', email: 'fixture@example.invalid',
  github: 'fixture-user', linkedin: 'fixture-user', message: 'Security regression fixture text.' });

test('operator cookies expire, reject tampering and do not carry the operator credential', () => {
  const credential = 'fictional-operator-fixture';
  const cookie = issueOperatorCookie(credential, 1000000);
  assert.equal(cookie.includes(credential), false);
  assert.equal(verifyOperatorCookie(cookie, credential, 1001000), true);
  assert.equal(verifyOperatorCookie(cookie, credential, 606000000), false);
  assert.equal(verifyOperatorCookie(cookie, 'rotated-fixture', 1001000), false);
  assert.equal(verifyOperatorCookie(credential, credential, 1001000), false);
  assert.equal(verifyOperatorCookie(cookie, '', 1001000), false);
  assert.equal(matchesOperatorPasscode(credential, credential), true);
  assert.equal(matchesOperatorPasscode('wrong', credential), false);
  assert.equal(matchesOperatorPasscode('', ''), false);
});

test('validation rejects malformed fields and unexpected URLs', () => {
  assert.equal(validateProposal(valid()).email, 'fixture@example.invalid');
  for (const change of [{ message: 'x'.repeat(4001) }, { name: [] }, { fax: 'automation' },
    { github: 'javascript:alert(1)' }, { linkedin: 'https://wrong.invalid/me' },
    { website: 'http://unsafe.invalid' }, { message: 'tiny' }]) {
    assert.throws(() => validateProposal({ ...valid(), ...change }));
  }
  assert.throws(() => validateProposal(JSON.parse('{"toString":"not allowed"}')));
});

test('submission quotas, duplicates and expiry use bounded state', () => {
  const body = valid();
  assert.equal(allowSubmission(body, 'quota-fixture', 0), true);
  assert.equal(allowSubmission(body, 'quota-fixture', 1), false);
  for (let i = 0; i < 4; i++) assert.equal(allowSubmission({ ...body, message: String(i) }, 'quota-fixture', 2), true);
  assert.equal(allowSubmission({ ...body, message: 'next' }, 'quota-fixture', 3), false);
  assert.equal(allowSubmission(body, 'quota-fixture', 901000), true);
});

test('operator authentication is rate limited without duplicate-login lockout', () => {
  for (let i = 0; i < 5; i++) assert.equal(allowSubmission({}, 'auth-fixture', 902000, false), true);
  assert.equal(allowSubmission({}, 'auth-fixture', 902001, false), false);
  assert.equal(allowSubmission({}, 'auth-fixture', 963000, false), true);
});

test('browser submissions require matching origin', () => {
  assert.equal(sameOrigin('https://terminal.invalid', 'terminal.invalid'), true);
  assert.equal(sameOrigin('https://wrong.invalid', 'terminal.invalid'), false);
  assert.equal(sameOrigin('malformed', 'terminal.invalid'), false);
  assert.equal(sameOrigin(undefined, 'terminal.invalid'), true);
});

test('stored proposal text cannot terminate an inline script', () => {
  const value = [{ message: '</script><script>fixture</script>&\u2028' }];
  const encoded = jsonForScript(value);
  assert.equal(encoded.includes('<'), false);
  assert.equal(encoded.includes('\u2028'), false);
  assert.deepEqual(JSON.parse(encoded), value);
});
