import asyncio
import os

import uvicorn

MODE = os.environ.get("HYSTRON_MODE", "control").lower()


async def _run_control() -> None:
    from app.database import init_db

    init_db()

    from app.main import internal_app, node_app, public_app

    cfg_public = uvicorn.Config(public_app, host="0.0.0.0", port=9000, log_level="info")
    cfg_internal = uvicorn.Config(internal_app, host="0.0.0.0", port=9001, log_level="info")
    cfg_node = uvicorn.Config(node_app, host="0.0.0.0", port=9002, log_level="info")

    await asyncio.gather(
        uvicorn.Server(cfg_public).serve(),
        uvicorn.Server(cfg_internal).serve(),
        uvicorn.Server(cfg_node).serve(),
    )


async def _run_node() -> None:
    from node.agent import run

    await run()


if __name__ == "__main__":
    try:
        if MODE == "control":
            asyncio.run(_run_control())
        elif MODE == "node":
            asyncio.run(_run_node())
        else:
            raise SystemExit(f"Unknown HYSTRON_MODE: {MODE!r}. Use 'control' or 'node'.")
    except KeyboardInterrupt:
        pass
