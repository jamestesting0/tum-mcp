import test from 'node:test';
import assert from 'node:assert/strict';
import { newerVersion } from '../package-manager.mjs';
import { installationTarget } from '../npm-command.mjs';
import { fileURLToPath } from 'node:url';

test('release selection follows semver and refuses downgrades', () => {
  for (const [latest, current, newer] of [
    ['0.6.1', '0.6.0', true], ['1.0.0', '0.99.0', true], ['0.6.1', '0.7.0', false],
    ['0.6.1', '0.6.1', false], ['1.0.0', '1.0.0-rc.1', true], ['1.0.0-beta', '1.0.0', false],
    ['1.0.0-beta.10', '1.0.0-beta.9', true], ['1.0.0-alpha.beta', '1.0.0-alpha.9', true],
    ['1.0.0-alpha.1', '1.0.0-alpha', true], ['1.0.0-alpha', '1.0.0-alpha.1', false],
    ['1.0.0+next', '1.0.0+current', false], ['1.0.0-a', '1.0.0-b', false],
  ]) assert.equal(newerVersion(latest, current), newer, `${latest} / ${current}`);
  for (const invalid of [null, {}, 'latest', '1.2', '01.0.0', '1.0.0-01', '1.0.0-..']) {
    assert.throws(() => newerVersion(invalid, '1.0.0'), /invalid/);
  }
});

test('source and temporary npx installations are preserved for explicit management', () => {
  assert.throws(() => installationTarget(fileURLToPath(new URL('../../', import.meta.url))), /npm installation/);
  assert.throws(() => installationTarget('/cache/_npx/fixture/node_modules/@jamestesting888/tum-mcp'), /npm installation/);
  assert.throws(() => installationTarget('/prefix/lib/node_modules/@alias/tum-mcp'), /aliases were preserved/);
});
