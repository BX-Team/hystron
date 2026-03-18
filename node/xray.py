import asyncio
import os
import signal

from .config import XRAY_CONFIG_PATH, XRAY_STATS_PORT

_proc: asyncio.subprocess.Process | None = None
_restart_delay = 1.0


async def start() -> asyncio.subprocess.Process:
    global _proc, _restart_delay
    _proc = await asyncio.create_subprocess_exec(
        "xray", "run", "-c", XRAY_CONFIG_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _restart_delay = 1.0
    asyncio.create_task(_watch())
    print(f"[node/xray] started (pid={_proc.pid})")
    return _proc


async def _watch():
    global _proc, _restart_delay
    if _proc is None:
        return
    await _proc.wait()
    code = _proc.returncode
    if code is not None and code != 0:
        print(f"[node/xray] exited with code {code}, restarting in {_restart_delay:.0f}s…")
        await asyncio.sleep(_restart_delay)
        _restart_delay = min(_restart_delay * 2, 60.0)
        await start()


async def reload() -> None:
    """Send SIGHUP for zero-downtime config reload."""
    if _proc and _proc.returncode is None:
        _proc.send_signal(signal.SIGHUP)
        print("[node/xray] sent SIGHUP (config reload)")
    else:
        print("[node/xray] process not running, starting fresh")
        await start()


async def kick_users(usernames: list[str]) -> None:
    """Remove active sessions for the given users via xray HandlerService API."""
    if not usernames:
        return
    for username in usernames:
        try:
            proc = await asyncio.create_subprocess_exec(
                "xray", "api", "rmuser",
                f"--server=127.0.0.1:{XRAY_STATS_PORT}",
                "--email", username,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception as e:
            print(f"[node/xray] kick {username}: {e}")


async def stop() -> None:
    global _proc
    if _proc and _proc.returncode is None:
        _proc.terminate()
        try:
            await asyncio.wait_for(_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            _proc.kill()
    _proc = None
