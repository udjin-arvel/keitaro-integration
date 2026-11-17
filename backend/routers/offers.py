from fastapi import APIRouter, Depends, HTTPException

from exceptions import KeitaroError
from routers.deps import get_keitaro
from schemas import OfferRead
from services.keitaro import KeitaroClient

router = APIRouter(prefix="/api/offers", tags=["offers"])


@router.get("", response_model=list[OfferRead])
async def list_offers(keitaro: KeitaroClient = Depends(get_keitaro)) -> list[OfferRead]:
    try:
        items = await keitaro.list_offers()
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    result: list[OfferRead] = []
    for item in items:
        raw_id = item.get("id")
        try:
            offer_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if offer_id <= 0:
            continue
        name = item.get("name")
        raw_group = item.get("group_id")
        group_id: int | None
        try:
            group_id = int(raw_group) if raw_group is not None else None
        except (TypeError, ValueError):
            group_id = None
        state = item.get("state")
        result.append(
            OfferRead(
                id=offer_id,
                name=name if isinstance(name, str) else None,
                group_id=group_id,
                state=state if isinstance(state, str) else None,
            )
        )
    return result
