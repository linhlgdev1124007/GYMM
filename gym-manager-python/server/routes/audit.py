from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..controllers import audit_controller
from ..database import get_db
from ..dependencies import require_roles

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("", dependencies=[Depends(require_roles("admin"))])
def logs(
    q: str = "",
    action: str = "all",
    actor_id: int | None = Query(None, alias="actorId"),
    entity_type: str = Query("all", alias="entityType"),
    scope: str = "all",
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=5, le=100, alias="pageSize"),
    include_actors: bool = Query(True, alias="includeActors"),
    db: Session = Depends(get_db),
):
    return audit_controller.list_logs(
        db,
        q=q,
        action=action,
        actor_id=actor_id,
        entity_type=entity_type,
        scope=scope,
        page=page,
        page_size=page_size,
        include_actors=include_actors,
    )
