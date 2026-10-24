import { createHash } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import https from 'node:https';

const hosts = new Set(['github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com', 'releases.astral.sh']);

export async function download(url, destination, expected, redirects = 0) {
  const target = new URL(url);
  if (target.protocol !== 'https:' || !hosts.has(target.hostname) || redirects > 5) throw new Error('Untrusted runtime download origin.');
  await new Promise((resolve, reject) => {
    const request = https.get(target, { timeout: 30000, headers: { 'User-Agent': 'tum-mcp-bootstrap' } }, response => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
        response.resume();
        if (!response.headers.location) return reject(new Error('Runtime redirect has no location.'));
        download(new URL(response.headers.location, target).href, destination, expected, redirects + 1).then(resolve, reject);
        return;
      }
      if (response.statusCode !== 200) { response.resume(); reject(new Error(`Runtime download returned HTTP ${response.statusCode}.`)); return; }
      let size = 0;
      const chunks = [];
      response.on('data', chunk => {
        size += chunk.length;
        if (size > 64 * 1024 * 1024) response.destroy(new Error('Runtime download exceeds the size budget.'));
        else chunks.push(chunk);
      });
      response.on('error', reject);
      response.on('end', async () => {
        try {
          const bytes = Buffer.concat(chunks);
          if (createHash('sha256').update(bytes).digest('hex') !== expected) throw new Error('Runtime checksum mismatch.');
          await writeFile(destination, bytes, { mode: 0o600 }); resolve();
        } catch (error) { reject(error); }
      });
    });
    request.on('timeout', () => request.destroy(new Error('Runtime download timed out.')));
    request.on('error', reject);
  });
}
