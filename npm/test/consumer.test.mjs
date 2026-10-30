import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

test('an invalid browser journey mode stops before consumer installation', () => {
  const root = mkdtempSync(join(tmpdir(), 'tum-consumer-mode-'));
  const marker = join(root, 'npm-invoked');
  const npm = join(root, 'npm.mjs');
  writeFileSync(npm, `import { writeFileSync } from 'node:fs'; writeFileSync(${JSON.stringify(marker)}, 'called'); process.exit(73);`);
  try {
    for (const mode of ['primray', '']) {
      const result = spawnSync(process.execPath, [fileURLToPath(new URL('../smoke-consumer.mjs', import.meta.url)), 'synthetic-missing.tgz'], {
        encoding: 'utf8',
        env: { ...process.env, npm_execpath: npm, TUM_MCP_STUDY_BROWSER_JOURNEYS: mode },
      });
      assert.notEqual(result.status, 0);
      assert.equal(existsSync(marker), false, 'Invalid QA settings must not invoke npm');
    }
  } finally { rmSync(root, { recursive: true, force: true }); }
});
