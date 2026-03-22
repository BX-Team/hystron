from fastapi import APIRouter

from app.db.database import list_all_tags

router = APIRouter(prefix="/api", tags=["Tags"])


@router.get("/tags")
def tags_list():
    return list_all_tags()
