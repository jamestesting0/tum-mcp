import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { registryFixture, futureRelease, isolatedWindowsProfile } from './package-fixtures.mjs';
import { acquireLock } from './lock.mjs';

assert.ok(process.env.npm_execpath, 'Run with npm run test:package-lifecycle.');
const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
const artifact = resolve(process.argv[2] || `dist/jamestesting888-tum-mcp-${version}.tgz`);
const root = realpathSync(mkdtempSync(join(tmpdir(), 'tum-package Ω-')));
const home = join(root, 'profile'); mkdirSync(home);
const prefix = join(root, 'global prefix');
const source = join(prefix, process.platform === 'win32' ? 'node_modules' : 'lib/node_modules', '@jamestesting888/tum-mcp');
const launcher = join(source, 'npm/tum-mcp.mjs');
const registry = await registryFixture();
const allowed = new Set(['PATH', 'SYSTEMROOT', 'COMSPEC', 'TMPDIR', 'TMP', 'TEMP', 'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'WSL_INTEROP', 'WSL_DISTRO_NAME', 'WSLENV']);
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => allowed.has(name.toUpperCase())));
Object.assign(env, { HOME: home, USERPROFILE: home, TUM_MCP_DATA_DIR: join(root, 'data'), TUM_MCP_CONFIG_DIR: join(root, 'config'),
  TUM_MOODLE_DATA_DIR: join(root, 'moodle'), TUM_MOODLE_DOWNLOAD_DIR: join(root, 'downloads'),
  NPM_CONFIG_USERCONFIG: join(root, 'npmrc'), NPM_CONFIG_CACHE: join(root, 'npm cache'),
  NPM_CONFIG_PREFIX: join(root, 'unexpected prefix'),
  NPM_CONFIG_REGISTRY: registry.url, NPM_CONFIG_FETCH_RETRIES: '0', NPM_CONFIG_FETCH_TIMEOUT: '3000', npm_execpath: process.env.npm_execpath });
env.NO_PROXY = ['127.0.0.1', 'localhost', env.NO_PROXY].filter(Boolean).join(',');
writeFileSync(env.NPM_CONFIG_USERCONFIG, '', { mode: 0o600 });
let releaseWindowsProfile = () => {};

async function run(command, args, expected = 0) {
  const child = spawn(command, args, { env, cwd: root, shell: false, stdio: ['ignore', 'pipe', 'pipe'] });
  let stdout = '', stderr = '';
  child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
  child.stdout.on('data', data => { stdout += data; });
  child.stderr.on('data', data => { stderr += data; });
  const timeout = setTimeout(() => child.kill(), 600000);
  try {
    const status = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', resolve); });
    assert.equal(status, expected, `${command} failed: ${stdout}\n${stderr}`);
    return stdout;
  } finally { clearTimeout(timeout); }
}
const npm = args => run(process.execPath, [process.env.npm_execpath, ...args, '--no-audit', '--no-fund']);
const call = (args, expected) => run(process.execPath, [launcher, ...args], expected);
const metadata = () => JSON.parse(readFileSync(join(source, 'package.json'), 'utf8'));
const claude = () => JSON.parse(readFileSync(join(home, '.claude.json'), 'utf8'));
const state = () => JSON.parse(readFileSync(join(root, 'data/runtime.json'), 'utf8'));
const records = [];

try {
  releaseWindowsProfile = isolatedWindowsProfile(root, env);
  console.log('Package lifecycle: install and prepare isolated global clients');
  await npm(['install', '--global', '--prefix', prefix, '--ignore-scripts', artifact]);
  console.log('Package lifecycle: installed global package; preparing managed runtime');
  await call(['setup', '--client', 'codex', '--client', 'claude', '--client', 'cursor']);
  console.log('Package lifecycle: prepared clients; creating unpublished release fixture');
  const original = state();
  const nextVersion = version.split('.').slice(0, 2).concat(Number(version.split('.')[2]) + 1).join('.');
  const laterVersion = version.split('.').slice(0, 2).concat(Number(version.split('.')[2]) + 2).join('.');
  const futureDirectory = join(root, 'unpublished fixtures'); mkdirSync(futureDirectory);
  const next = await futureRelease({ source, directory: futureDirectory, python: original.python, version: nextVersion, run, npm });
  console.log('Package lifecycle: prepared unpublished release fixture');
  registry.release(next.manifest, next.path);
  const project = join(home, 'University/course');
  const saved = [
    [join(root, 'data/credentials/local/session.key'), 'synthetic-private-key'],
    [join(root, 'moodle/session.enc'), 'synthetic-legacy-record'],
    [join(root, 'downloads/lecture.pdf'), 'synthetic-original'],
    [join(project, '.tum-mcp/comments.json'), '{"synthetic":"learner comment"}'],
    [join(project, 'audio/lesson.wav'), Buffer.from([0x52, 0x49, 0x46, 0x46, 0, 0xff, 0x80, 13, 10])],
    [join(project, 'materials/notes.md'), 'synthetic-course-material'],
    [join(project, 'app/content.json'), '{"synthetic":"study content"}'],
    [join(home, '.codex/plugins/local/tum-mcp/personal-note.txt'), 'user-added-file'],
  ];
  for (const [path, body] of saved) { mkdirSync(join(path, '..'), { recursive: true }); writeFileSync(path, body); }
  const settings = join(root, 'config/preferences.json');
  writeFileSync(settings, JSON.stringify({ workspace_root: project, language: 'en' }));
  saved.push([settings, readFileSync(settings, 'utf8')]);
  const other = { command: 'synthetic-unrelated-tool', args: ['retain'] };
  writeFileSync(join(home, '.claude.json'), JSON.stringify({ ...claude(), mcpServers: { ...claude().mcpServers, other } }));
  const retained = () => {
    for (const [path, body] of saved) assert.deepEqual(readFileSync(path), Buffer.from(body), path);
    assert.deepEqual(claude().mcpServers.other, other);
  };

  const dataDirectory = env.TUM_MCP_DATA_DIR;
  env.TUM_MCP_DATA_DIR = join(source, 'personal-data');
  mkdirSync(env.TUM_MCP_DATA_DIR); writeFileSync(join(env.TUM_MCP_DATA_DIR, 'note.txt'), 'Preserve overlapping data');
  await call(['uninstall', '--all'], 2);
  assert.equal(readFileSync(join(env.TUM_MCP_DATA_DIR, 'note.txt'), 'utf8'), 'Preserve overlapping data');
  const relocated = join(root, 'relocated personal-data'); renameSync(env.TUM_MCP_DATA_DIR, relocated);
  saved.push([join(relocated, 'note.txt'), 'Preserve overlapping data']);
  env.TUM_MCP_DATA_DIR = dataDirectory;
  Object.assign(env, { TUM_MCP_DATA_DIR: 'data', TUM_MCP_CONFIG_DIR: 'config', TUM_MOODLE_DATA_DIR: 'moodle', TUM_MOODLE_DOWNLOAD_DIR: 'downloads' });
  console.log('Package lifecycle: download, validate and install the newer release');

  const updated = await call(['update']);
  assert.equal(metadata().version, nextVersion, updated);
  assert.ok(!existsSync(join(source, 'install-script-ran')), 'npm lifecycle scripts must stay disabled');
  const current = state();
  assert.notEqual(current.python, original.python);
  assert.equal(claude().mcpServers.tum.command, current.python);
  assert.equal((await run(current.python, ['-I', '-m', 'tum_mcp', 'version'])).trim(), nextVersion);
  assert.ok(existsSync(original.python)); retained();
  const selected = readFileSync(join(root, 'data/runtime.json'), 'utf8');
  await call(['update']);
  assert.equal(readFileSync(join(root, 'data/runtime.json'), 'utf8'), selected);
  registry.release(JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')), artifact);
  await call(['update']);
  assert.equal(metadata().version, nextVersion, 'A published older latest tag must not downgrade a newer installation');
  registry.release(next.manifest, next.path);
  records.push('download, validate, install and refresh; repeat update is idempotent');
  console.log('Package lifecycle: exercise registry and preparation failures');

  registry.unavailable(true);
  await call(['update'], 2);
  assert.equal(metadata().version, nextVersion); retained();
  registry.unavailable(false);
  const broken = await futureRelease({ source, directory: futureDirectory, python: current.python, version: laterVersion, run, npm, broken: true });
  registry.release(broken.manifest, broken.path);
  await call(['update'], 2);
  assert.equal(metadata().version, nextVersion);
  assert.equal(claude().mcpServers.tum.command, current.python); retained();
  records.push('registry and corrupt preparation failures preserve package and client runtime');
  console.log('Package lifecycle: exercise npm replacement failure');

  const later = await futureRelease({ source, directory: futureDirectory, python: current.python, version: laterVersion, run, npm });
  registry.release(later.manifest, later.path);
  const fakeNpm = join(root, 'failing npm'); mkdirSync(join(fakeNpm, 'bin'), { recursive: true });
  writeFileSync(join(fakeNpm, 'package.json'), '{"name":"npm"}');
  const attempted = join(root, 'replacement-attempted');
  writeFileSync(join(fakeNpm, 'bin/npm-cli.js'), `const {spawnSync}=require('node:child_process');const a=process.argv.slice(2);if(a[0]==='install'&&a[a.indexOf('--prefix')+1]===${JSON.stringify(prefix)}){require('node:fs').writeFileSync(${JSON.stringify(attempted)},'attempted');process.exit(73);}const r=spawnSync(process.execPath,[${JSON.stringify(process.env.npm_execpath)},...a],{stdio:'inherit'});process.exit(r.status??2);`);
  env.npm_execpath = join(fakeNpm, 'bin/npm-cli.js');
  await call(['update'], 2);
  assert.ok(existsSync(attempted), 'The failure must occur during replacement, after preparation');
  delete env.npm_execpath; env.npm_execpath = process.env.npm_execpath;
  assert.equal(metadata().version, nextVersion);
  assert.equal(claude().mcpServers.tum.command, current.python); retained();
  records.push('npm replacement failure retains the installed package and pinned clients');
  console.log('Package lifecycle: check concurrency, customized files and client-only removal');

  registry.release(next.manifest, next.path);
  const unlock = await acquireLock(prefix, 'tum-mcp-package');
  try { await call(['update'], 2); } finally { await unlock(); }
  assert.equal(metadata().version, nextVersion); retained();
  await call(['uninstall', '--client', 'cursor']);
  assert.ok(existsSync(launcher));
  assert.equal(JSON.parse(readFileSync(join(home, '.cursor/mcp.json'), 'utf8')).mcpServers.tum, undefined);
  const edited = join(home, '.claude/skills/read-content/SKILL.md');
  const before = readFileSync(edited, 'utf8'); writeFileSync(edited, before + '\nPersonal guidance.\n');
  await call(['update'], 2);
  await call(['uninstall', '--all'], 2);
  assert.ok(existsSync(launcher));
  assert.equal(readFileSync(edited, 'utf8'), before + '\nPersonal guidance.\n'); retained();
  writeFileSync(edited, before);
  records.push('concurrent operations, client-only removal and customization conflicts are safe');
  console.log('Package lifecycle: remove npm and runtimes, then check a fresh installation');

  await call(['uninstall', '--all', '--purge-runtime']);
  assert.ok(!existsSync(source));
  assert.ok(!existsSync(join(root, 'data/runtimes')));
  assert.equal(claude().mcpServers.tum, undefined); retained();
  records.push('one-command uninstall removes npm and runtimes, retaining credentials and personal work');
  await npm(['install', '--global', '--prefix', prefix, '--ignore-scripts', artifact]);
  env.TUM_MCP_DATA_DIR = join(root, 'never configured');
  env.TUM_MCP_CONFIG_DIR = join(root, 'never configured config');
  await call(['uninstall', '--all']);
  assert.ok(!existsSync(source)); retained();
  assert.ok(!existsSync(join(env.TUM_MCP_DATA_DIR, 'runtimes')));
  records.push('reinstalled package can be removed without registered clients');
  console.log('Package lifecycle: check project-local update and uninstall');
  const local = join(root, 'local project');
  await npm(['install', '--prefix', local, '--global=false', '--ignore-scripts', artifact]);
  const localSource = join(local, 'node_modules/@jamestesting888/tum-mcp');
  const localCall = args => run(process.execPath, [join(localSource, 'npm/tum-mcp.mjs'), ...args]);
  const personal = join(local, 'notes.md'); writeFileSync(personal, 'Local project notes');
  await localCall(['setup', '--client', 'generic']);
  await localCall(['update']);
  assert.equal(JSON.parse(readFileSync(join(localSource, 'package.json'), 'utf8')).version, nextVersion);
  const declared = JSON.parse(readFileSync(join(local, 'package.json'), 'utf8')).dependencies['@jamestesting888/tum-mcp'];
  assert.ok(declared.includes(nextVersion) && !declared.startsWith('file:'), 'Local manifests must not reference a deleted temporary archive');
  await localCall(['uninstall', '--all']);
  assert.ok(!existsSync(localSource));
  assert.equal(readFileSync(personal, 'utf8'), 'Local project notes'); retained();
  records.push('local npm updates maintain project metadata and removal preserves project files');
  console.log(JSON.stringify({ platform: process.platform, scenarios: records, passed: true, publicPublicationUsed: false, realAccountsUsed: false }));
} catch (error) {
  console.error(error); process.exitCode = 1;
} finally { await registry.close(); releaseWindowsProfile(); rmSync(root, { recursive: true, force: true }); }
