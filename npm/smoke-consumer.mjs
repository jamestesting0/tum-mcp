import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir, release } from 'node:os';
import { join, resolve } from 'node:path';

const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url))).version;
const artifact = process.argv[2] || `dist/jamestesting888-tum-mcp-${version}.tgz`;
if (!artifact || !process.env.npm_execpath) throw new Error('Run npm run test:consumer -- /path/to/package.tgz.');
const root = mkdtempSync(join(tmpdir(), 'tum-mcp-packaged-smoke-'));
mkdirSync(join(root, 'profile'));
const allowed = new Set(['PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'COMSPEC', 'TMPDIR', 'TMP', 'TEMP', 'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'WSL_INTEROP', 'WSL_DISTRO_NAME', 'WSLENV', 'DISPLAY', 'WAYLAND_DISPLAY']);
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => allowed.has(name.toUpperCase())));
Object.assign(env, {
  HOME: join(root, 'profile'), USERPROFILE: join(root, 'profile'),
  TUM_MCP_DATA_DIR: join(root, 'data'), TUM_MCP_CONFIG_DIR: join(root, 'config'),
  TUM_MOODLE_DATA_DIR: join(root, 'moodle'), NPM_CONFIG_USERCONFIG: join(root, 'npmrc'),
});
writeFileSync(env.NPM_CONFIG_USERCONFIG, '', { mode: 0o600 });

function run(command, args, timeout = 600000, childEnv = env) {
  const result = spawnSync(command, args, { env: childEnv, encoding: 'utf8', shell: false, timeout });
  if (result.error || result.status !== 0) throw new Error(`${command} failed: ${[result.stdout, result.stderr, result.error?.message].filter(Boolean).join('\n') || result.status}`);
  return result.stdout;
}

try {
  // Invoking npm's JavaScript entrypoint also works on Windows without a shell/.cmd wrapper.
  run(process.execPath, [process.env.npm_execpath, 'install', '--prefix', root, '--ignore-scripts', '--no-audit', '--no-fund', resolve(artifact)]);
  const launcher = join(root, 'node_modules/@jamestesting888/tum-mcp/npm/tum-mcp.mjs');
  run(process.execPath, [launcher, 'setup', '--client', 'generic']);
  const first = JSON.parse(readFileSync(join(root, 'data/runtime.json'), 'utf8'));
  run(process.execPath, [launcher, 'setup', '--client', 'generic']);
  assert.deepEqual(JSON.parse(readFileSync(join(root, 'data/runtime.json'), 'utf8')), first);
  const skills = JSON.parse(run(process.execPath, [launcher, 'skills', 'validate']));
  assert.equal(skills.checked_skills.length, 4);
  assert.deepEqual(skills.errors, []);
  const diagnostics = JSON.parse(run(process.execPath, [launcher, 'doctor', '--json']));
  assert.equal(diagnostics.live_authentication, 'not_checked');
  assert.equal(diagnostics.remote_actions, 'disabled');
  assert.ok(diagnostics.services.every(service => service.state !== 'Ready'));
  const storage = `import os
from pathlib import Path
from tum_mcp.moodle import auth
from tum_mcp.moodle.auth import Cookie,Session,SessionStore
from tum_mcp.moodle.config import Paths
from tum_mcp.clients import install_client,client_config_path,read_client_config
from tum_mcp.credentials import Credential,Vault
from tum_mcp.settings import Account,Provider
def forbidden():
    raise AssertionError('Native credential storage must not be opened')
auth.system_keyring=forbidden
root=Path(os.environ['TUM_MOODLE_DATA_DIR'])
root.mkdir(parents=True,exist_ok=True)
legacy=root/'session.enc'
legacy.write_bytes(b'preserved-legacy-record')
store=SessionStore(Paths(root),storage='file')
store.save(Session(generation=store.begin_login(),cookies=[Cookie(name='session',value='synthetic-consumer-only',domain='www.moodle.tum.de')],verified_at=1))
assert store.load().cookies[0].value=='synthetic-consumer-only'
assert b'synthetic-consumer-only' not in store.file('session.enc').read_bytes()
store.logout()
assert legacy.read_bytes()==b'preserved-legacy-record'
account=Account(provider=Provider.ARTEMIS,origin='https://artemis.tum.de',principal='consumer-fixture')
vault=Vault()
vault.save(account,Credential(account_id=account.id))
assert vault.load(account).account_id==account.id
vault.logout(account)
home=root/'disposable-client-profile'
for name in ('cursor','antigravity'):
    install_client(name,home)
    install_client(name,home)
    assert read_client_config(client_config_path(name,home)).mcpServers['tum']['args']==['-I','-m','tum_mcp','serve']
`;
  run(first.python, ['-I', '-c', storage], 60000);
  let browserEvidence = null;
  if (process.env.TUM_MCP_BROWSER_INTEGRATION === '1' || /microsoft|wsl/i.test(release())) {
    // Windows browsers require the OS account's known-folder environment. They
    // still receive Playwright's separate temporary profile, never the real one.
    const browserEnv = { ...env };
    if (process.platform === 'win32') {
      for (const name of ['HOME', 'USERPROFILE']) if (process.env[name]) browserEnv[name] = process.env[name];
    }
    browserEvidence = JSON.parse(run(first.python, ['-I', '-c', readFileSync(new URL('../tests/integration/browser_consumer_fixture.py', import.meta.url), 'utf8')], 180000, browserEnv));
  }
  const protocol = `import os,sys,anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client
from tum_mcp.client_hosts import ClientHost,client_launch
from tum_mcp.moodle.browsers import is_wsl
async def check():
    launch=client_launch(ClientHost.WINDOWS if is_wsl() else ClientHost.LOCAL)
    params=StdioServerParameters(**(launch.entry()|{'env':{**os.environ,**launch.entry().get('env',{})}}))
    async with stdio_client(params) as (reader,writer),ClientSession(reader,writer,read_timeout_seconds=20) as client:
        await client.initialize()
        inventory=await client.list_tools()
        names={tool.name for tool in inventory.tools}
        assert {'moodle_list_courses','zulip_search_messages','artemis_get_feedback','artemis_list_lectures','artemis_get_lecture','artemis_get_attachment','moodle_read_discussion'} <= names
        assert not {'artemis_submit','artemis_start_exercise','artemis_prepare_workspace','tum_run_tests','artemis_prepare_submission'} & names
        status=await client.call_tool('tum_status')
        assert not status.is_error and status.structured_content['accounts']==[]
        denied=await client.call_tool('artemis_prepare_submission',{'workspace':'.','approved':True})
        assert denied.is_error
anyio.run(check)
`;
  run(first.python, ['-I', '-c', protocol], 60000);
  const demoProject = join(root, 'Synthetic course');
  run(process.execPath, [launcher, 'study', 'demo', demoProject]);
  const study = JSON.parse(run(process.execPath, [launcher, 'study', 'inspect', demoProject]));
  assert.equal(study.course.synthetic, true); assert.deepEqual(study.stale_units, []);
  assert.ok(readFileSync(join(demoProject, 'study', 'reading.mjs'), 'utf8').includes('renderReading'));
  console.log(JSON.stringify({ platform: process.platform, architecture: process.arch, setupIdempotent: true, skills: 4, packagedMcpPassed: true, localEncryptedStoragePassed: true, additionalClientSetupPassed: true, browserEvidence, realAccountsUsed: false }));
} finally { rmSync(root, { recursive: true, force: true }); }
