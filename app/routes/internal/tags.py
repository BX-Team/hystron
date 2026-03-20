from fastapi import APIRouter

from app.database import list_all_tags

router = APIRouter(prefix="/api", tags=["Tags"])


@router.get("/tags")
def tags_list():
    return list_all_tags()
