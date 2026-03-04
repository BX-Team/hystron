import asyncio

import uvicorn

from app.database import create_user, init_db, user_exists
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
    init_db()

    if not user_exists("admin"):
        result = create_user("admin")
        if result:
            print(f"[init] created default user  admin / {result['password']}")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
