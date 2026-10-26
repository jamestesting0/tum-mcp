import { lectureLifecycle } from './lecture-consumer.mjs';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
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
  const skills = JSON.parse(run(process.execPath, [launcher, 'skills', 'validate']));
  assert.deepEqual(skills.checked_skills.toSorted(), ['audio-notes', 'prepare-exercises', 'prepare-study', 'publish-course', 'read-content', 'sync-course']);
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
  assert.equal(lectureEvidence.installed_skills, 7);
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
  // Exercise the optional extension from the installed wheel, with synthetic local PDFs.
  run(process.execPath, [launcher, 'install', 'studocu']);
  const optionalSkills = JSON.parse(run(process.execPath, [launcher, 'skills', 'validate']));
  assert.ok(optionalSkills.checked_skills.includes('sync-studocu'));
  assert.deepEqual(optionalSkills.errors, []);
  const supplementary = join(root, 'supplementary course');
  const snapshot = join(root, 'supplementary-snapshot.json');
  writeFileSync(snapshot, JSON.stringify({
    course: { key: 'sample-course', title: 'Synthetic Course', semester: 'Winter', bindings: [{ key: 'moodle', provider: 'moodle', course_id: '1' }] },
    coverage: [{ binding: 'moodle', status: 'partial', checked_at: '2026-01-01' }],
    resources: [{ key: 'lecture', binding: 'moodle', kind: 'content', title: 'Lecture', url: 'https://example.org/lecture', text: 'Synthetic source' }],
  }));
  run(process.execPath, [launcher, 'study', 'init', supplementary, '--course', 'Synthetic Course', '--snapshot', snapshot]);
  const selection = join(root, 'selection.json');
  const groups = ['summaries', 'exams', 'other'];
  run(first.python, ['-I', '-c', "from tum_mcp.studocu.courses import record_courses; record_courses([{'course_id':123,'institution_id':92,'name':'Synthetic Course'}])"]);
  writeFileSync(selection, JSON.stringify({ course_id: '123', documents: [] }));
  run(process.execPath, [launcher, 'studocu', 'plan', supplementary, '--selection', selection]);
  const seedDiscovery = "import sys; from pathlib import Path; from tum_mcp.studocu.state import record_discovery; record_discovery(Path(sys.argv[1]), '123', [{'id':str(i),'course_id':123} for i in (41,42,43,44)])";
  run(first.python, ['-I', '-c', seedDiscovery, supplementary]);
  writeFileSync(selection, JSON.stringify({ course_id: '123', documents: [...groups.map((group, index) => ({
    document_id: String(41 + index), title: `Synthetic ${group}`, url: `https://www.studocu.com/de/document/${41 + index}`, group, year: 2024, decision: 'include', reason: 'Synthetic review',
  })), { document_id: '44', title: 'Synthetic exam duplicate', url: 'https://www.studocu.com/de/document/44', group: 'exams', year: 2024, decision: 'include', reason: 'Synthetic review' }] }));
  run(process.execPath, [launcher, 'studocu', 'plan', supplementary, '--selection', selection]);
  const original = join(root, 'synthetic-original');
  run(first.python, ['-I', '-c', "from pypdf import PdfWriter; import sys; w=PdfWriter(); w.add_blank_page(width=200,height=200); w.write(sys.argv[1])", original]);
  let studocuBrowserPassed = false;
  let importFile = original;
  if (process.env.TUM_MCP_STUDOCU_BROWSER_QA === '1') {
    const browserSave = join(root, 'browser-saved-original');
    const downloadFixture = `import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright
from tum_mcp.moodle.browser_runtime import browser_driver
from tum_mcp.moodle.browsers import discover_browsers
choices=discover_browsers()
assert choices, 'No browser available for the requested synthetic download test.'
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        content=Path(sys.argv[1]).read_bytes() if self.path=='/original.pdf' else b'<a href="/original.pdf">Download original</a>'
        self.send_response(200)
        self.send_header('Content-Type','application/pdf' if self.path=='/original.pdf' else 'text/html')
        if self.path=='/original.pdf': self.send_header('Content-Disposition','attachment; filename="original.pdf"')
        self.send_header('Content-Length',str(len(content)))
        self.end_headers()
        self.wfile.write(content)
    def log_message(self,*args): pass
with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
    worker=Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        with browser_driver(choices[0]),sync_playwright() as playwright:
            browser=playwright.chromium.launch(executable_path=choices[0].executable,headless=True,args=['--enable-automation'])
            try:
                context=browser.new_context(accept_downloads=True)
                page=context.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                with page.expect_download() as result:
                    page.get_by_role('link',name='Download original').click()
                result.value.save_as(sys.argv[2])
                context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        worker.join(timeout=5)
`;
    run(first.python, ['-I', '-c', downloadFixture, original, browserSave], 60000, browserEnvironment());
    assert.deepEqual(readFileSync(browserSave), readFileSync(original));
    importFile = browserSave;
    studocuBrowserPassed = true;
  }
  let stagedName;
  for (const [index, group] of groups.entries()) {
    if (index === 0) {
      stagedName = JSON.parse(run(process.execPath, [launcher, 'studocu', 'stage', supplementary, '--document-id', '41', '--file', importFile])).staged_name;
      assert.equal(JSON.parse(run(process.execPath, [launcher, 'studocu', 'status', supplementary, '--json'])).counts.downloaded, 1);
      continue;
    }
    run(process.execPath, [launcher, 'studocu', 'import', supplementary, '--document-id', String(41 + index), '--file', importFile]);
    assert.deepEqual(readFileSync(join(supplementary, 'materials/studocu', group, `material-studocu-${41 + index}.pdf`)), readFileSync(original));
  }
  const duplicate = JSON.parse(run(process.execPath, [launcher, 'studocu', 'import', supplementary, '--document-id', '44', '--file', importFile]));
  assert.equal(duplicate.state, 'duplicate');
  assert.equal(duplicate.duplicate_of, '42');
  assert.ok(!existsSync(join(supplementary, 'materials/studocu/exams/material-studocu-44.pdf')));
  const optionalProtocol = `import os,sys,anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client
from tum_mcp.client_hosts import ClientHost,client_launch
async def check():
    launch=client_launch(ClientHost.LOCAL)
    params=StdioServerParameters(**(launch.entry()|{'env':{**os.environ,**launch.entry().get('env',{})}}))
    async with stdio_client(params) as (reader,writer),ClientSession(reader,writer,read_timeout_seconds=30) as client:
        await client.initialize()
        names={tool.name for tool in (await client.list_tools()).tools}
        assert 'studocu_get_document' in names
        resumed=await client.call_tool('studocu_download_document',{'project':sys.argv[1],'document_id':41})
        assert not resumed.is_error and resumed.structured_content['state']=='DOWNLOADED' and resumed.structured_content['staged_name']==sys.argv[2]
        imported=await client.call_tool('studocu_import_document',{'project':sys.argv[1],'document_id':41,'staged_name':sys.argv[2]})
        assert not imported.is_error and imported.structured_content['state']=='imported'
        result=await client.call_tool('studocu_get_document',{'project':sys.argv[1],'document_id':42,'page_start':1,'page_limit':1,'include_images':True})
        assert not result.is_error and result.structured_content['pages'][0]['number']==1
        assert any(item.type=='image' for item in result.content)
        alias=await client.call_tool('studocu_get_document',{'project':sys.argv[1],'document_id':44})
        assert not alias.is_error and alias.structured_content['source_url'].endswith('/44')
anyio.run(check)
`;
  run(first.python, ['-I', '-c', optionalProtocol, supplementary, stagedName], 60000);
  assert.deepEqual(readFileSync(join(supplementary, 'materials/studocu/summaries/material-studocu-41.pdf')), readFileSync(original));
  const decisions = JSON.parse(readFileSync(selection, 'utf8'));
  for (const entry of decisions.documents.filter(item => ['42', '44'].includes(item.document_id))) entry.raw_category = 'Reviewed exam';
  writeFileSync(selection, JSON.stringify(decisions));
  run(process.execPath, [launcher, 'studocu', 'plan', supplementary, '--selection', selection]);
  const aliasAfterReview = JSON.parse(readFileSync(join(supplementary, '.tum-mcp/state.json'), 'utf8'));
  assert.equal(aliasAfterReview.resources.find(item => item.resource.key === 'studocu-44').alias_of, 'studocu-42');
  const queue = JSON.parse(run(process.execPath, [launcher, 'studocu', 'status', supplementary, '--json']));
  const aliasReceipt = queue.selection.documents.find(item => item.document_id === '44').staged_name;
  rmSync(join(supplementary, '.tum-mcp/studocu/incoming', `${aliasReceipt}.json`));
  const recovered = JSON.parse(run(process.execPath, [launcher, 'studocu', 'import', supplementary, '--document-id', '44', '--file', importFile]));
  assert.equal(recovered.state, 'already_imported');
  assert.ok(!existsSync(join(supplementary, 'materials/studocu/exams/material-studocu-44.pdf')));
  const inventoryBefore = JSON.parse(readFileSync(join(supplementary, '.tum-mcp/state.json'), 'utf8'));
  const campusRefresh = join(root, 'campus-refresh.json');
  writeFileSync(campusRefresh, JSON.stringify({
    course: inventoryBefore.course,
    coverage: [{ binding: 'moodle', status: 'partial', checked_at: '2026-01-02' }],
    resources: [], retained_bindings: ['studocu'],
  }));
  run(process.execPath, [launcher, 'study', 'sync', supplementary, '--snapshot', campusRefresh]);
  const inventoryAfter = JSON.parse(readFileSync(join(supplementary, '.tum-mcp/state.json'), 'utf8'));
  assert.deepEqual(inventoryAfter.resources.filter(item => item.resource.binding === 'studocu'), inventoryBefore.resources.filter(item => item.resource.binding === 'studocu'));
  run(process.execPath, [launcher, 'studocu', 'plan', supplementary, '--selection', selection]);
  const wrongSelection = join(root, 'wrong-course.json');
  writeFileSync(wrongSelection, JSON.stringify({ course_id: '999', documents: [] }));
  const rejectedCourse = spawnSync(process.execPath, [launcher, 'studocu', 'plan', supplementary, '--selection', wrongSelection], { env, encoding: 'utf8', shell: false, timeout: 60000 });
  assert.notEqual(rejectedCourse.status, 0);
  const collectionStatus = JSON.parse(run(process.execPath, [launcher, 'studocu', 'status', supplementary, '--json']));
  assert.equal(collectionStatus.counts.imported, 3);
  assert.equal(collectionStatus.counts.duplicate, 1);
  run(process.execPath, [launcher, 'extensions', 'remove', 'studocu']);
  assert.ok(existsSync(join(supplementary, 'materials/studocu/exams/material-studocu-42.pdf')));
  const demoProject = join(root, 'Synthetic course');
  run(process.execPath, [launcher, 'study', 'demo', demoProject]);
  const template = JSON.parse(run(process.execPath, [launcher, 'study', 'template']));
  assert.equal(template.author, 'app/content.json');
  assert.ok(['flashcards.mjs', 'navigation.mjs', 'revision.mjs'].every(file => template.files.includes(file)));
  assert.match(template.revision, /^[a-f0-9]{64}$/);
  const study = JSON.parse(run(process.execPath, [launcher, 'study', 'inspect', demoProject]));
  assert.equal(study.course.synthetic, true); assert.deepEqual(study.stale_units, []);
  assert.ok(readFileSync(join(demoProject, 'app', 'reading.mjs'), 'utf8').includes('renderReading'));
  console.log(JSON.stringify({ platform: process.platform, architecture: process.arch, setupIdempotent: true, skills: skills.checked_skills.length, studyStateRoutingPassed: true, packagedMcpPassed: true, localEncryptedStoragePassed: true, additionalClientSetupPassed: true, studocuImportPassed: true, studocuBrowserPassed, browserEvidence, realAccountsUsed: false }));
} finally { rmSync(root, { recursive: true, force: true }); }
