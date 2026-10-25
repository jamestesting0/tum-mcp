import test from 'node:test';
import assert from 'node:assert/strict';
import { newerVersion } from '../package-manager.mjs';
import { installationTarget, packageStorage } from '../npm-command.mjs';
import { fileURLToPath } from 'node:url';
import { mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

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

test('package replacement refuses paths containing configured storage or course work', () => {
  const directory = realpathSync(mkdtempSync(join(tmpdir(), 'tum-package-paths-')));
  const root = join(directory, 'package'); mkdirSync(root);
  const note = join(root, 'note.txt'); writeFileSync(note, 'user file');
  const keys = ['TUM_MCP_CONFIG_DIR', 'TUM_MOODLE_DATA_DIR', 'TUM_MOODLE_DOWNLOAD_DIR'];
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  const normal = { TUM_MCP_CONFIG_DIR: join(directory, 'config'), TUM_MOODLE_DATA_DIR: join(directory, 'moodle'), TUM_MOODLE_DOWNLOAD_DIR: join(directory, 'downloads') };
  try {
    Object.assign(process.env, normal);
    const data = join(directory, 'data');
    assert.equal(packageStorage(root, data).TUM_MCP_CONFIG_DIR, normal.TUM_MCP_CONFIG_DIR);
    assert.throws(() => packageStorage(root, join(root, 'data')), /overlaps/);
    for (const key of keys) {
      process.env[key] = join(root, 'saved');
      assert.throws(() => packageStorage(root, data), /overlaps/);
      process.env[key] = normal[key];
    }
    mkdirSync(normal.TUM_MCP_CONFIG_DIR);
    const settings = join(normal.TUM_MCP_CONFIG_DIR, 'preferences.json');
    writeFileSync(settings, JSON.stringify({ workspace_root: join(root, 'course') }));
    assert.throws(() => packageStorage(root, data), /overlaps/);
    writeFileSync(settings, 'synthetic-unparseable-data');
    assert.throws(() => packageStorage(root, data), error => !error.message.includes('synthetic'));
    assert.equal(readFileSync(note, 'utf8'), 'user file');
  } finally {
    for (const key of keys) { if (previous[key] === undefined) delete process.env[key]; else process.env[key] = previous[key]; }
    rmSync(directory, { recursive: true, force: true });
  }
});
