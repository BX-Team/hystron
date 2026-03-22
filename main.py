import asyncio

import uvicorn

from app.db.database import init_db

init_db()

from app.main import internal_app, public_app


async def _run() -> None:
    cfg_public = uvicorn.Config(
        public_app,
        host="0.0.0.0",
        port=9000,
        log_level="info",
    )
    cfg_internal = uvicorn.Config(
        internal_app,
        host="0.0.0.0",
        port=9001,
        log_level="info",
    )
    srv_public = uvicorn.Server(cfg_public)
    srv_internal = uvicorn.Server(cfg_internal)
    await asyncio.gather(srv_public.serve(), srv_internal.serve())


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
