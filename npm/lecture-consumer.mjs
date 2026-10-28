import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export function lectureLifecycle(root, command) {
  const installed = JSON.parse(command(['install', 'lecture', '--no-asr', '--json']));
  assert.equal(installed.enabled, true);
  const skills = JSON.parse(command(['skills', 'validate', '--json']));
  assert.equal(skills.checked_skills.length, 7);
  assert.deepEqual(skills.errors, []);
  const destination = join(root, 'lecture-export');
  command(['skills', 'export', destination]);
  assert.equal(readdirSync(destination).length, 7);
  for (const name of ['SKILL.md', 'agents/openai.yaml', 'references/sources.md', 'references/authoring.md', 'references/content.md', 'references/verification.md']) {
    assert.ok(existsSync(join(destination, 'prepare-lecture', name)));
  }
  const project = join(root, 'optional-lecture-course');
  command(['study', 'demo', project, '--lectures']);
  const notes = join(project, 'app/lectures.json');
  const before = readFileSync(notes);
  const payload = JSON.parse(readFileSync(join(project, 'app/data.mjs'), 'utf8').slice('export default '.length).trim().replace(/;$/, ''));
  assert.deepEqual(payload.workspaces, ['study', 'exercises', 'lectures', 'exam']);
  const image = join(project, 'app', payload.lectures.lectures[0].sections[0].figures[0].asset);
  assert.ok(readFileSync(image).subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])));
  command(['update', '--local']);
  assert.equal(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.length, 7);
  const customized = command(['skills', 'customize', 'prepare-lecture']).trim();
  const entry = join(customized, 'SKILL.md');
  writeFileSync(entry, readFileSync(entry, 'utf8') + '\nPersonal lecture preference.\n');
  const removed = JSON.parse(command(['uninstall', 'lecture', '--json']));
  assert.equal(removed.enabled, false);
  assert.equal(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.length, 6);
  assert.ok(readFileSync(notes).equals(before));
  assert.ok(existsSync(image));
  assert.match(readFileSync(entry, 'utf8'), /Personal lecture preference/);
  command(['install', 'lecture', '--no-asr']);
  const customExport = join(root, 'lecture-custom-export');
  command(['skills', 'export', customExport]);
  assert.match(readFileSync(join(customExport, 'prepare-lecture/SKILL.md'), 'utf8'), /Personal lecture preference/);
  command(['uninstall', 'lecture']);
  // The independently optional extensions must survive each other's client refreshes.
  command(['install', 'studocu']);
  command(['install', 'lecture', '--no-asr']);
  command(['update', '--local']);
  const both = JSON.parse(command(['skills', 'validate', '--json']));
  assert.equal(both.checked_skills.length, 8);
  assert.deepEqual(both.errors, []);
  command(['install', 'audio-notes']);
  assert.equal(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.length, 9);
  command(['install', 'video-notes']);
  assert.equal(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.length, 10);
  assert.equal(JSON.parse(command(['doctor', '--json'])).extensions.find(row => row.label === 'Video Notes').state, 'Enabled');
  command(['uninstall', 'video-notes']);
  assert.ok(!JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.includes('video-notes'));
  command(['uninstall', 'studocu']);
  assert.ok(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.includes('prepare-lecture'));
  assert.ok(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.includes('audio-notes'));
  command(['install', 'studocu']);
  command(['uninstall', 'lecture']);
  assert.ok(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.includes('sync-studocu'));
  command(['uninstall', 'audio-notes']);
  assert.ok(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.includes('sync-studocu'));
  command(['uninstall', 'studocu']);
  assert.equal(JSON.parse(command(['skills', 'validate', '--json'])).checked_skills.length, 6);
  return { base_skills: 6, installed_skills: 7, update_preserved: true, notes_and_customization_preserved: true };
}
