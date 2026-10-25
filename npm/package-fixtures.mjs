import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { chmodSync, cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { release } from 'node:os';
import { delimiter, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export function isolatedWindowsProfile(root, env) {
  if (process.platform !== 'linux' || !(env.WSL_DISTRO_NAME || /microsoft|wsl/i.test(release()))) return () => {};
  // WSL client discovery must never inspect or remove the real Windows profile.
  const script = "$ErrorActionPreference='Stop'; $root=Join-Path ([IO.Path]::GetTempPath()) ('tum-mcp-fixture-'+[guid]::NewGuid().ToString('N')); [IO.Directory]::CreateDirectory($root)|Out-Null; foreach($v in @($root,[Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString())){[Console]::WriteLine([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($v)))}";
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { env, encoding: 'utf8', timeout: 15000 });
  assert.equal(result.status, 0, 'Cannot create an isolated Windows test profile');
  const [windowsRoot, arch] = result.stdout.trim().split(/\r?\n/).map(line => Buffer.from(line, 'base64').toString('utf8'));
  assert.ok(/tum-mcp-fixture-[a-f0-9]{32}$/.test(windowsRoot));
  const mapped = spawnSync('wslpath', ['-u', windowsRoot], { env, encoding: 'utf8', timeout: 10000 });
  assert.equal(mapped.status, 0, 'Cannot map the isolated Windows test profile');
  const tools = join(root, 'host-tools'); mkdirSync(tools);
  const values = [windowsRoot + '\\profile', windowsRoot + '\\data', windowsRoot + '\\programs', windowsRoot + '\\programs-x86', arch];
  const output = values.map(value => Buffer.from(value).toString('base64')).join('\n') + '\n';
  const executable = join(tools, 'powershell.exe');
  writeFileSync(executable, '#!/usr/bin/env node\nprocess.stdout.write(' + JSON.stringify(output) + ');\n');
  chmodSync(executable, 0o700);
  env.PATH = tools + delimiter + env.PATH;
  return () => rmSync(mapped.stdout.trim(), { recursive: true, force: true });
}

export async function registryFixture() {
  let release;
  let unavailable = false;
  const server = createServer((request, response) => {
    if (unavailable) { response.writeHead(503); response.end(); return; }
    if (request.url === '/fixture.tgz' && release) {
      response.setHeader('content-type', 'application/octet-stream');
      response.end(release.body); return;
    }
    if (decodeURIComponent(request.url.split('?')[0]) === '/@jamestesting888/tum-mcp' && release) {
      response.setHeader('content-type', 'application/json');
      response.end(JSON.stringify({ name: release.manifest.name, 'dist-tags': { latest: release.manifest.version },
        versions: { [release.manifest.version]: { ...release.manifest, dist: {
          tarball: `http://127.0.0.1:${server.address().port}/fixture.tgz`,
          integrity: 'sha512-' + createHash('sha512').update(release.body).digest('base64'),
          shasum: createHash('sha1').update(release.body).digest('hex'),
        } } } })); return;
    }
    response.writeHead(404); response.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    release(manifest, path) { release = { manifest, body: readFileSync(path) }; unavailable = false; },
    unavailable(value) { unavailable = value; },
    async close() { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); },
  };
}

export async function futureRelease({ source, directory, python, version, run, npm, broken = false }) {
  const staged = join(directory, version + (broken ? '-broken' : ''));
  cpSync(source, staged, { recursive: true });
  console.log(`Package fixture ${version}: copied package`);
  const manifest = JSON.parse(readFileSync(join(staged, 'package.json'), 'utf8'));
  manifest.version = version;
  manifest.scripts.postinstall = "node -e \"require('node:fs').writeFileSync('install-script-ran','unexpected')\"";
  writeFileSync(join(staged, 'package.json'), JSON.stringify(manifest));
  const backend = join(staged, 'npm/backend');
  const before = JSON.parse(readFileSync(join(backend, 'manifest.json'), 'utf8'));
  const wheel = `tum_mcp-${version}-py3-none-any.whl`;
  const fixture = fileURLToPath(new URL('../tests/integration/package_release_fixture.py', import.meta.url));
  await run(python, ['-I', fixture, join(backend, before.wheel), join(backend, wheel), version]);
  console.log(`Package fixture ${version}: prepared backend wheel`);
  rmSync(join(backend, before.wheel));
  writeFileSync(join(backend, 'manifest.json'), JSON.stringify({ ...before, wheel,
    wheelSha256: broken ? '0'.repeat(64) : createHash('sha256').update(readFileSync(join(backend, wheel))).digest('hex'),
  }));
  const packed = JSON.parse(await npm(['pack', staged, '--ignore-scripts', '--pack-destination', directory, '--json']));
  console.log(`Package fixture ${version}: packed release`);
  return { manifest, path: join(directory, packed[0].filename) };
}
