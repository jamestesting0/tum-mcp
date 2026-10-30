import { lectureLifecycle } from './lecture-consumer.mjs';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir, release } from 'node:os';
import { join, resolve } from 'node:path';

const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url))).version;
const studyJourneys = process.env.TUM_MCP_STUDY_BROWSER_JOURNEYS ?? 'all';
assert.ok(['all', 'primary'].includes(studyJourneys), 'Study browser journeys must be all or primary.');
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

function browserEnvironment() {
  // Windows known folders must match the OS user; browser contexts remain temporary.
  const browserEnv = { ...env };
  if (process.platform === 'win32') {
    for (const name of ['HOME', 'USERPROFILE']) if (process.env[name]) browserEnv[name] = process.env[name];
  }
  return browserEnv;
}

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
  const skills = JSON.parse(run(process.execPath, [launcher, 'skills', 'validate', '--json']));
  assert.deepEqual(skills.checked_skills.toSorted(), ['prepare-exams', 'prepare-exercises', 'prepare-study', 'publish-course', 'read-content', 'review-course', 'sync-course']);
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
from tum_mcp.skill_catalog import CURRENT_SKILLS
from tum_mcp.skills import bundled
from tum_mcp.uninstall import uninstall_client
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
    skills=home/{'cursor':'.cursor/skills','antigravity':'.gemini/config/skills'}[name]
    assert {path.name for path in skills.iterdir()}==set(CURRENT_SKILLS)
    for skill in CURRENT_SKILLS:
        source=bundled()/skill
        assert {path.relative_to(source):path.read_bytes() for path in source.rglob('*') if path.is_file()}=={path.relative_to(skills/skill):path.read_bytes() for path in (skills/skill).rglob('*') if path.is_file()}
    uninstall_client(name,home)
    assert not any((skills/skill).exists() for skill in CURRENT_SKILLS)
`;
  run(first.python, ['-I', '-c', storage], 60000);
  const studyProject = join(root, 'course Ω');
  const status = () => JSON.parse(run(process.execPath, [launcher, 'study', 'status', studyProject]));
  assert.equal(status().mode, 'initialize');
  assert.equal(existsSync(studyProject), false);
  run(process.execPath, [launcher, 'study', 'demo', studyProject]);
  const boundStatus = status();
  assert.equal(boundStatus.mode, 'sync');
  assert.equal(boundStatus.course.synthetic, true);
  const lectureEvidence = lectureLifecycle(root, args => run(process.execPath, [launcher, ...args]));
  assert.equal(lectureEvidence.installed_skills, 8);
  const studyState = join(studyProject, '.tum-mcp/state.json');
  writeFileSync(studyState, 'synthetic damaged study state');
  assert.equal(status().mode, 'recover');
  assert.equal(readFileSync(studyState, 'utf8'), 'synthetic damaged study state');
  let browserEvidence = null;
  if (process.env.TUM_MCP_BROWSER_INTEGRATION === '1' || /microsoft|wsl/i.test(release())) {
    const browserEnv = browserEnvironment();
    const studyFixtureRoot = join(root, 'course-fixture');
    mkdirSync(studyFixtureRoot);
    for (const name of ['snapshot.json', 'content.json']) {
      writeFileSync(join(studyFixtureRoot, name), readFileSync(new URL(`../tests/fixtures/course_app/${name}`, import.meta.url)));
    }
    browserEnv.TUM_MCP_STUDY_QA_FIXTURE = studyFixtureRoot;
    browserEnv.TUM_MCP_STUDY_QA_PROJECT = studyProject;
    browserEnv.TUM_MCP_STUDY_BROWSER_JOURNEYS = studyJourneys;
    const fixture = readFileSync(new URL('../tests/integration/browser_consumer_fixture.py', import.meta.url), 'utf8');
    const revisionFixture = readFileSync(new URL('../tests/integration/study_revision_fixture.py', import.meta.url), 'utf8');
    const popoverFixture = readFileSync(new URL('../tests/integration/study_popover_fixture.py', import.meta.url), 'utf8');
    const commentsFixture = readFileSync(new URL('../tests/integration/study_comments_fixture.py', import.meta.url), 'utf8')
      .replace('from study_popover_fixture import popover_checks', popoverFixture);
    const activityCommentsFixture = readFileSync(new URL('../tests/integration/study_activity_comments_fixture.py', import.meta.url), 'utf8')
      .replace('from study_comments_fixture import open_notes, select_passage', '');
    const tableFixture = readFileSync(new URL('../tests/integration/study_table_fixture.py', import.meta.url), 'utf8');
    const inlineFixture = readFileSync(new URL('../tests/integration/study_inline_fixture.py', import.meta.url), 'utf8')
      .replace('from study_comments_fixture import open_notes, select_passage', '');
    const studyFixture = readFileSync(new URL('../tests/integration/study_browser_fixture.py', import.meta.url), 'utf8')
      .replace(/^from study_revision_fixture import (?:\([\s\S]*?\)|[^\r\n]+)\r?\n/m, revisionFixture)
      .replace('from study_comments_fixture import comment_checks', commentsFixture)
      .replace('from study_table_fixture import table_layout_checks', tableFixture)
      .replace('from study_inline_fixture import inline_math_checks, mobile_outline_checks', inlineFixture)
      .replace('from study_activity_comments_fixture import activity_comment_checks', activityCommentsFixture);
    // Isolated Python intentionally cannot import helpers from the checkout.
    const combined = fixture.replace('from study_browser_fixture import study_website', studyFixture);
    const browserScript = join(root, 'browser-consumer.py');
    writeFileSync(browserScript, combined, { mode: 0o600 });
    browserEvidence = JSON.parse(run(first.python, ['-I', browserScript], 300000, browserEnv));
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
        assert {'moodle_list_courses','zulip_search_messages','artemis_get_feedback','artemis_list_lectures','artemis_get_lecture','artemis_get_attachment','moodle_read_discussion','tumonline_status','tumonline_list_courses','tumonline_list_studies','tumonline_course_curriculum'} <= names
        search=next(tool for tool in inventory.tools if tool.name=='tumonline_list_courses')
        assert 'query' in search.input_schema['properties']
        assert not {'artemis_submit','artemis_start_exercise','artemis_prepare_workspace','tum_run_tests','artemis_prepare_submission'} & names
        status=await client.call_tool('tum_status')
        assert not status.is_error and status.structured_content['accounts']==[]
        online=await client.call_tool('tumonline_status')
        assert not online.is_error and online.structured_content['accounts']==[]
        denied_online=await client.call_tool('tumonline_course_curriculum',{'account_id':'a'*64,'course_id':1})
        assert denied_online.is_error
        denied=await client.call_tool('artemis_prepare_submission',{'workspace':'.','approved':True})
        assert denied.is_error
anyio.run(check)
`;
  run(first.python, ['-I', '-c', protocol], 60000);
  const demoProject = join(root, 'Synthetic course');
  run(process.execPath, [launcher, 'study', 'demo', demoProject]);
  const template = JSON.parse(run(process.execPath, [launcher, 'study', 'template']));
  assert.equal(template.author, 'app/content.json');
  assert.ok(['flashcards.mjs', 'navigation.mjs', 'revision.mjs'].every(file => template.files.includes(file)));
  assert.match(template.revision, /^[a-f0-9]{64}$/);
  const study = JSON.parse(run(process.execPath, [launcher, 'study', 'inspect', demoProject]));
  assert.equal(study.course.synthetic, true); assert.deepEqual(study.stale_units, []);
  assert.ok(readFileSync(join(demoProject, 'app', 'reading.mjs'), 'utf8').includes('renderReading'));
  console.log(JSON.stringify({ platform: process.platform, architecture: process.arch, setupIdempotent: true, skills: skills.checked_skills.length, studyStateRoutingPassed: true, packagedMcpPassed: true, localEncryptedStoragePassed: true, additionalClientSetupPassed: true, browserEvidence, realAccountsUsed: false }));
} finally { rmSync(root, { recursive: true, force: true }); }
