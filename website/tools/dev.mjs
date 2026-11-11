// Serves the walkthrough at http://127.0.0.1:4310 and rebuilds it on every page load. Each build
// runs in a fresh Node process, so changes to the build tools apply without a restart.
import { execFile } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import path from 'node:path';
import { promisify } from 'node:util';
import { paths } from './lib/paths.mjs';

const run = promisify(execFile);
const port = Number(process.env.PORT ?? 4310);
const output = path.join(paths.dist, 'tum-mcp-walkthrough.html');

createServer(async (request, response) => {
  if (new URL(request.url, 'http://localhost').pathname !== '/') {
    response.writeHead(404).end();
    return;
  }
  try {
    await run(process.execPath, [path.join(paths.website, 'tools/build.mjs')], { cwd: paths.website, maxBuffer: 8 * 1024 * 1024 });
    const html = await readFile(output);
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' }).end(html);
  } catch (error) {
    response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' }).end(`Build failed:\n${error.stderr || error.stack || error}`);
  }
}).listen(port, '127.0.0.1', () => console.log(`Walkthrough: http://127.0.0.1:${port}/`));
