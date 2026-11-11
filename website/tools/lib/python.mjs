// Calls into the tum-mcp package so the website reuses its own logic instead of copying it.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const run = promisify(execFile);

async function python({ repo, code, args = [] }) {
  const { stdout } = await run('uv', ['run', '--project', repo, '--quiet', 'python', '-c', code, ...args], {
    cwd: repo, maxBuffer: 64 * 1024 * 1024,
  });
  return stdout;
}

/** The media indexes the local preview (`tum-mcp study`) serves for a course project. */
export async function previewIndexes({ project, repo }) {
  const code = [
    'import json, sys',
    'from pathlib import Path',
    'from tum_mcp.course.media.audio_app import preview_index as audio',
    'from tum_mcp.course.media.video_project import preview_index as videos',
    'project = Path(sys.argv[1])',
    "print(json.dumps({'audio': audio(project), 'videos': videos(project)}))",
  ].join('\n');
  return JSON.parse(await python({ repo, code, args: [project] }));
}
