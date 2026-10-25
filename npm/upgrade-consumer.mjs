import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { isolatedWindowsProfile } from './package-fixtures.mjs';

const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url))).version;
const artifact = resolve(process.argv[2] || `dist/jamestesting888-tum-mcp-${version}.tgz`);
assert.ok(process.env.npm_execpath, 'Run with npm run test:upgrade.');
const allowed = new Set(['PATH', 'SYSTEMROOT', 'COMSPEC', 'TMPDIR', 'TMP', 'TEMP', 'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'WSL_INTEROP', 'WSL_DISTRO_NAME', 'WSLENV']);
const inherited = Object.fromEntries(Object.entries(process.env).filter(([name]) => allowed.has(name.toUpperCase())));
const records = [];
for (const previousVersion of ['0.6.0']) {
  const root = mkdtempSync(join(tmpdir(), 'tum-mcp upgrade Ω-'));
  const home = join(root, 'profile'); mkdirSync(home);
  const env = { ...inherited, HOME: home, USERPROFILE: home,
    TUM_MCP_DATA_DIR: join(root, 'data'), TUM_MCP_CONFIG_DIR: join(root, 'config'),
    TUM_MOODLE_DATA_DIR: join(root, 'moodle'), TUM_MOODLE_DOWNLOAD_DIR: join(root, 'downloads'),
    NPM_CONFIG_USERCONFIG: join(root, 'npmrc') };
  writeFileSync(env.NPM_CONFIG_USERCONFIG, '', { mode: 0o600 });
  let releaseWindowsProfile = () => {};
  function run(command, args, expected = 0, timeout = 600000) {
    const result = spawnSync(command, args, { env, encoding: 'utf8', shell: false, timeout, maxBuffer: 4 * 1024 * 1024 });
    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, expected, `${command} failed: ${result.stdout}\n${result.stderr}`);
    return result.stdout;
  }
  function npm(args) { return run(process.execPath, [process.env.npm_execpath, ...args]); }
  function launcher(prefix) { return join(prefix, 'node_modules/@jamestesting888/tum-mcp/npm/tum-mcp.mjs'); }
  function call(prefix, args, expected = 0) { return run(process.execPath, [launcher(prefix), ...args], expected); }
  try {
    releaseWindowsProfile = isolatedWindowsProfile(root, env);
    const oldPrefix = join(root, 'old');
    npm(['install', '--prefix', oldPrefix, '--ignore-scripts', '--no-audit', '--no-fund', `@jamestesting888/tum-mcp@${previousVersion}`]);
    const clients = ['codex', 'claude', 'generic', 'cursor', 'antigravity'];
    call(oldPrefix, ['setup', ...clients.flatMap(name => ['--client', name])]);
    const previous = JSON.parse(readFileSync(join(root, 'data/runtime.json')));
    const source = join(home, '.codex/plugins/local/tum-mcp');
    const note = join(source, 'personal-note.txt'); writeFileSync(note, 'retain this user note');
    const credential = join(root, 'data/credentials/local', `${'a'.repeat(64)}.enc`);
    mkdirSync(join(root, 'data/credentials/local'), { recursive: true });
    writeFileSync(credential, 'synthetic-private-record');
    const work = join(home, 'University/assignment/Main.java');
    mkdirSync(join(home, 'University/assignment'), { recursive: true }); writeFileSync(work, 'class Main {}');
    mkdirSync(env.TUM_MOODLE_DOWNLOAD_DIR, { recursive: true });
    const download = join(env.TUM_MOODLE_DOWNLOAD_DIR, 'original.pdf'); writeFileSync(download, 'synthetic-original');
    const currentPrefix = join(root, 'current');
    npm(['install', '--prefix', currentPrefix, '--ignore-scripts', '--no-audit', '--no-fund', artifact]);
    call(currentPrefix, ['update', '--local']);
    const current = JSON.parse(readFileSync(join(root, 'data/runtime.json')));
    assert.notEqual(current.python, previous.python);
    assert.ok(existsSync(previous.python), 'Previous runtime must remain for pinned clients.');
    assert.equal(run(previous.python, ['-I', '-m', 'tum_mcp', 'version']).trim(), previousVersion);
    assert.deepEqual(readdirSync(join(source, 'skills')).filter(name => existsSync(join(source, 'skills', name, 'SKILL.md'))).sort(), ['audio-notes', 'prepare-study', 'publish-study', 'read-content', 'sync-study']);
    assert.equal(JSON.parse(readFileSync(join(home, '.claude.json'))).mcpServers.tum.command, current.python);
    assert.equal(readFileSync(note, 'utf8'), 'retain this user note');
    assert.equal(readFileSync(credential, 'utf8'), 'synthetic-private-record');
    const first = readFileSync(join(root, 'data/runtime.json'), 'utf8');
    call(currentPrefix, ['update', '--local']);
    assert.equal(readFileSync(join(root, 'data/runtime.json'), 'utf8'), first, 'Update must be idempotent.');
    // An invalid prepared package must not replace the existing selected runtime.
    const backend = join(currentPrefix, 'node_modules/@jamestesting888/tum-mcp/npm/backend');
    const manifestPath = join(backend, 'manifest.json'); const manifestBytes = readFileSync(manifestPath);
    const manifest = JSON.parse(manifestBytes); const wheelPath = join(backend, manifest.wheel); const wheel = readFileSync(wheelPath);
    const invalid = Buffer.from('synthetic-invalid-wheel'); writeFileSync(wheelPath, invalid);
    writeFileSync(manifestPath, JSON.stringify({ ...manifest, wheelSha256: createHash('sha256').update(invalid).digest('hex') }));
    call(currentPrefix, ['setup'], 2);
    assert.equal(readFileSync(join(root, 'data/runtime.json'), 'utf8'), first);
    writeFileSync(wheelPath, wheel); writeFileSync(manifestPath, manifestBytes);
    // Force health validation to repair this package using a new immutable generation.
    const initializer = JSON.parse(run(current.python, ['-I', '-c', 'import json,tum_mcp;print(json.dumps(tum_mcp.__file__))']));
    writeFileSync(initializer, '__version__="synthetic-broken-runtime"\n');
    call(currentPrefix, ['update', '--local']);
    const repaired = JSON.parse(readFileSync(join(root, 'data/runtime.json')));
    assert.notEqual(repaired.python, current.python);
    assert.ok(existsSync(current.python));
    const protocol = readFileSync(new URL('../tests/integration/upgrade_protocol_fixture.py', import.meta.url), 'utf8');
    run(repaired.python, ['-I', '-c', protocol], 0, 60000);
    call(currentPrefix, ['uninstall', '--all', '--purge-runtime']);
    assert.ok(!existsSync(join(root, 'data/runtimes')));
    assert.ok(!existsSync(join(source, 'plugin.json')) && existsSync(note));
    assert.ok(existsSync(credential) && existsSync(work) && existsSync(download));
    records.push({ from: previousVersion, to: version, clients: clients.length, skills: 5, idempotent: true, failedPreparationRetainedRuntime: true, damagedRuntimeRepaired: true, oldRuntimeRetainedUntilExplicitRemoval: true, removalKeptWorkAndCredentials: true, realAccountsUsed: false });
    console.log(JSON.stringify(records.at(-1)));
  } finally { releaseWindowsProfile(); rmSync(root, { recursive: true, force: true }); }
}
console.log(JSON.stringify({ upgrades: records, passed: true }));
