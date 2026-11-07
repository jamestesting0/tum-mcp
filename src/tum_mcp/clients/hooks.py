"""Package native course completion guards with the pinned backend."""

import base64
import json

from tum_mcp.clients.hosts import StdioLaunch


def script_command(path: str) -> str:
    """Keep user paths out of shell interpolation on POSIX, cmd and PowerShell."""
    encoded = base64.b64encode(path.encode()).decode("ascii")
    return (
        "node -e \"process.argv.splice(1,0,'course-task');"
        "import('node:url').then(m=>import(m.pathToFileURL("
        f"Buffer.from('{encoded}','base64').toString()).href))\" --"
    )


def launcher(launch: StdioLaunch, host: str) -> bytes:
    return (
        "import { spawn } from 'node:child_process';\n"
        "const env = { ...process.env }; delete env.PYTHONPATH; delete env.PYTHONHOME;\n"
        f"Object.assign(env, {json.dumps(dict(launch.environment))});\n"
        f"const child = spawn({json.dumps(launch.command)}, "
        f"[...{json.dumps([*launch.arguments[:-1], 'study', 'task', 'hook', '--host', host])}, "
        "...process.argv.slice(2)], "
        "{ env, stdio: 'inherit', shell: false });\n"
        "for (const signal of ['SIGINT', 'SIGTERM']) "
        "process.on(signal, () => child.kill(signal));\n"
        "child.on('error', () => { console.error('Course task guard could not start.'); "
        "process.exitCode = 2; });\n"
        "child.on('exit', code => { process.exitCode = code ?? 1; });\n"
    ).encode()
