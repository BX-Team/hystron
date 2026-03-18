import os

from fastapi import FastAPI, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .routes.internal import config, hosts, traffic, users
from .routes.node import sync as node_sync
from .routes.node import traffic as node_traffic
from .routes.public import auth, sub


public_app = FastAPI()
public_app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")),
    name="static",
)
public_app.include_router(auth.router)
public_app.include_router(sub.router)


@public_app.get("/")
def root():
    return Response(status_code=404)


@public_app.get(
    "/health",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def health():
    return {"status": "ok"}


@public_app.get("/robots.txt")
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


internal_app = FastAPI()
internal_app.include_router(users.router)
internal_app.include_router(traffic.router)
internal_app.include_router(hosts.router)
internal_app.include_router(config.router)

node_app = FastAPI()
node_app.include_router(node_sync.router)
node_app.include_router(node_traffic.router)
