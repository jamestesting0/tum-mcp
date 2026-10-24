import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const artifact = process.argv[2];
if (!artifact || !process.env.npm_execpath) throw new Error('Run npm run test:consumer -- /path/to/package.tgz.');
const root = mkdtempSync(join(tmpdir(), 'tum-mcp-packaged-smoke-'));
const allowed = new Set(['PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'COMSPEC', 'TMPDIR', 'TMP', 'TEMP', 'LOCALAPPDATA', 'APPDATA', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR']);
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => allowed.has(name.toUpperCase())));
Object.assign(env, {
  TUM_MCP_DATA_DIR: join(root, 'data'), TUM_MCP_CONFIG_DIR: join(root, 'config'),
  TUM_MOODLE_DATA_DIR: join(root, 'moodle'), NPM_CONFIG_USERCONFIG: join(root, 'npmrc'),
});
writeFileSync(env.NPM_CONFIG_USERCONFIG, '', { mode: 0o600 });

function run(command, args, timeout = 600000) {
  const result = spawnSync(command, args, { env, encoding: 'utf8', shell: false, timeout });
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
  assert.equal(skills.checked_skills.length, 7);
  assert.deepEqual(skills.errors, []);
  const protocol = `import os,sys,anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client
async def check():
    params=StdioServerParameters(command=sys.executable,args=['-I','-m','tum_mcp','serve'],env=dict(os.environ))
    async with stdio_client(params) as (reader,writer),ClientSession(reader,writer,read_timeout_seconds=20) as client:
        await client.initialize()
        inventory=await client.list_tools()
        names={tool.name for tool in inventory.tools}
        assert {'moodle_list_courses','zulip_search_messages','artemis_get_feedback'} <= names
        assert not {'artemis_submit','artemis_start_exercise'} & names
        status=await client.call_tool('tum_status')
        assert not status.is_error and status.structured_content['accounts']==[]
        denied=await client.call_tool('artemis_prepare_submission',{'workspace':'.','approved':True})
        assert denied.is_error
anyio.run(check)
`;
  run(first.python, ['-I', '-c', protocol], 60000);
  console.log(JSON.stringify({ platform: process.platform, architecture: process.arch, setupIdempotent: true, skills: 7, packagedMcpPassed: true, realAccountsUsed: false }));
} finally { rmSync(root, { recursive: true, force: true }); }
