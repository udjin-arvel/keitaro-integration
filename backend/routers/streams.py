from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette import status

from database import get_db
from exceptions import KeitaroError, WeightError
from models import Campaign, StreamOffer
from routers.deps import get_keitaro
from schemas import StreamDeleteResult, StreamOfferPin, StreamOffersAdd, StreamRead
from services import stream_draft
from services.keitaro import KeitaroClient

router = APIRouter(prefix="/api/campaigns", tags=["streams"])


def _detail(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _matches_query(stream: dict[str, Any], query: str) -> bool:
    needle = query.strip()
    if not needle:
        return True
    haystack = needle.lower()
    name = str(stream.get("name") or "").lower()
    stream_id = str(stream.get("id") or "")
    return haystack in name or haystack in stream_id.lower()


def _local_campaign(db: Session, campaign_id: int) -> Campaign | JSONResponse:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return _detail(status.HTTP_404_NOT_FOUND, "Кампания не найдена")
    if campaign.keitaro_id is None:
        return _detail(status.HTTP_409_CONFLICT, "У кампании нет keitaro_id, удалённый запрос невозможен")
    return campaign


def _stream_response(
    raw: dict[str, Any],
    db: Session,
    names: dict[int, str],
    keitaro_campaign_id: int | None,
) -> StreamRead:
    return StreamRead.model_validate(
        stream_draft.serialize_stream(raw, db, names, keitaro_campaign_id=keitaro_campaign_id)
    )


async def _names(keitaro: KeitaroClient) -> dict[int, str]:
    return await keitaro.offer_names()


@router.get("/{campaign_id}/streams", response_model=list[StreamRead], response_model_exclude_none=True)
async def list_campaign_streams(
    campaign_id: int,
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> list[StreamRead] | JSONResponse:
    campaign = _local_campaign(db, campaign_id)
    if isinstance(campaign, JSONResponse):
        return campaign
    try:
        streams = await keitaro.get_streams(campaign.keitaro_id)
        names = await _names(keitaro)
    except KeitaroError as exc:
        return _detail(exc.status_code, exc.message)
    result: list[StreamRead] = []
    for item in streams:
        if item.get("id") is None:
            continue
        if q and not _matches_query(item, q):
            continue
        stream_draft.sync_clean_stream(db, item, names)
        result.append(_stream_response(item, db, names, campaign.keitaro_id))
    db.commit()
    return result


@router.post(
    "/{campaign_id}/streams/sync",
    response_model=list[StreamRead],
    response_model_exclude_none=True,
)
async def sync_campaign_streams(
    campaign_id: int,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> list[StreamRead] | JSONResponse:
    campaign = _local_campaign(db, campaign_id)
    if isinstance(campaign, JSONResponse):
        return campaign
    try:
        streams = await keitaro.get_streams(campaign.keitaro_id)
        names = await _names(keitaro)
    except KeitaroError as exc:
        return _detail(exc.status_code, exc.message)
    result: list[StreamRead] = []
    for item in streams:
        if item.get("id") is None:
            continue
        if not stream_draft.is_dirty(db, int(item["id"])):
            stream_draft.apply_archive_sync(db, item, names)
        result.append(_stream_response(item, db, names, campaign.keitaro_id))
    db.commit()
    return result


@router.delete(
    "/{campaign_id}/streams/{stream_id}",
    response_model=StreamDeleteResult,
    response_model_exclude_none=True,
)
async def delete_campaign_stream(
    campaign_id: int,
    stream_id: int,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> StreamDeleteResult | JSONResponse:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Кампания не найдена"})
    try:
        await keitaro.delete_stream(stream_id)
    except KeitaroError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": exc.message},
        )
    stream_draft.delete_stream_local(db, stream_id)
    db.commit()
    return StreamDeleteResult(success=True)


async def _owned_stream(
    campaign: Campaign,
    stream_id: int,
    keitaro: KeitaroClient,
) -> dict[str, Any]:
    return await keitaro.get_owned_stream(stream_id, campaign.keitaro_id)


def _offer_row(db: Session, stream_id: int, offer_id: int) -> StreamOffer | None:
    return (
        db.query(StreamOffer)
        .filter(StreamOffer.stream_id == stream_id, StreamOffer.offer_id == offer_id)
        .one_or_none()
    )


@router.post(
    "/{campaign_id}/streams/{stream_id}/offers",
    response_model=StreamRead,
    response_model_exclude_none=True,
)
async def add_campaign_stream_offer(
    campaign_id: int,
    stream_id: int,
    payload: StreamOffersAdd,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> StreamRead | JSONResponse:
    campaign = _local_campaign(db, campaign_id)
    if isinstance(campaign, JSONResponse):
        return campaign
    try:
        stream = await _owned_stream(campaign, stream_id, keitaro)
        offer = await keitaro.get_offer(payload.offer_id)
        names = await _names(keitaro)
    except KeitaroError as exc:
        return _detail(exc.status_code, exc.message)
    offer_name = offer.get("name") if isinstance(offer.get("name"), str) else None
    stream_draft.sync_clean_stream(db, stream, names)
    existing = _offer_row(db, stream_id, payload.offer_id)
    if existing is not None and existing.status == stream_draft.STATUS_ACTIVE:
        return _detail(status.HTTP_409_CONFLICT, "Оффер уже добавлен в поток")
    if existing is not None and existing.status == stream_draft.STATUS_REMOVED:
        return _detail(status.HTTP_409_CONFLICT, "Оффер удалён, используйте Bring Back")
    db.add(
        StreamOffer(
            stream_id=stream_id,
            offer_id=payload.offer_id,
            offer_name=offer_name or names.get(payload.offer_id),
            weight=0,
            is_pinned=False,
            status=stream_draft.STATUS_ACTIVE,
        )
    )
    db.flush()
    try:
        stream_draft.recalc_active(db, stream_id)
    except WeightError as exc:
        db.rollback()
        return _detail(status.HTTP_400_BAD_REQUEST, exc.message)
    stream_draft.mark_dirty(db, stream_id, True)
    db.commit()
    return _stream_response(stream, db, names, campaign.keitaro_id)


@router.delete(
    "/{campaign_id}/streams/{stream_id}/offers/{offer_id}",
    response_model=StreamRead,
    response_model_exclude_none=True,
)
async def remove_campaign_stream_offer(
    campaign_id: int,
    stream_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> StreamRead | JSONResponse:
    campaign = _local_campaign(db, campaign_id)
    if isinstance(campaign, JSONResponse):
        return campaign
    try:
        stream = await _owned_stream(campaign, stream_id, keitaro)
        names = await _names(keitaro)
    except KeitaroError as exc:
        return _detail(exc.status_code, exc.message)
    row = _offer_row(db, stream_id, offer_id)
    if row is None:
        return _detail(status.HTTP_404_NOT_FOUND, "Оффер не найден в потоке")
    row.status = stream_draft.STATUS_REMOVED
    row.weight = 0
    try:
        stream_draft.recalc_active(db, stream_id)
    except WeightError as exc:
        db.rollback()
        return _detail(status.HTTP_400_BAD_REQUEST, exc.message)
    stream_draft.mark_dirty(db, stream_id, True)
    db.commit()
    return _stream_response(stream, db, names, campaign.keitaro_id)


@router.post(
    "/{campaign_id}/streams/{stream_id}/offers/{offer_id}/restore",
    response_model=StreamRead,
    response_model_exclude_none=True,
)
async def restore_campaign_stream_offer(
    campaign_id: int,
    stream_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> StreamRead | JSONResponse:
    campaign = _local_campaign(db, campaign_id)
    if isinstance(campaign, JSONResponse):
        return campaign
    try:
        stream = await _owned_stream(campaign, stream_id, keitaro)
        names = await _names(keitaro)
    except KeitaroError as exc:
        return _detail(exc.status_code, exc.message)
    row = _offer_row(db, stream_id, offer_id)
    if row is None:
        return _detail(status.HTTP_404_NOT_FOUND, "Оффер не найден в потоке")
    row.status = stream_draft.STATUS_ACTIVE
    try:
        stream_draft.recalc_active(db, stream_id)
    except WeightError as exc:
        db.rollback()
        return _detail(status.HTTP_400_BAD_REQUEST, exc.message)
    stream_draft.mark_dirty(db, stream_id, True)
    db.commit()
    return _stream_response(stream, db, names, campaign.keitaro_id)


@router.patch(
    "/{campaign_id}/streams/{stream_id}/offers/{offer_id}/pin",
    response_model=StreamRead,
    response_model_exclude_none=True,
)
async def pin_campaign_stream_offer(
    campaign_id: int,
    stream_id: int,
    offer_id: int,
    payload: StreamOfferPin,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> StreamRead | JSONResponse:
    campaign = _local_campaign(db, campaign_id)
    if isinstance(campaign, JSONResponse):
        return campaign
    try:
        stream = await _owned_stream(campaign, stream_id, keitaro)
        names = await _names(keitaro)
    except KeitaroError as exc:
        return _detail(exc.status_code, exc.message)
    row = _offer_row(db, stream_id, offer_id)
    if row is None:
        return _detail(status.HTTP_404_NOT_FOUND, "Оффер не найден в потоке")
    row.is_pinned = payload.is_pinned
    db.commit()
    return _stream_response(stream, db, names, campaign.keitaro_id)


@router.post(
    "/{campaign_id}/streams/{stream_id}/publish",
    response_model=StreamRead,
    response_model_exclude_none=True,
)
async def publish_campaign_stream(
    campaign_id: int,
    stream_id: int,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> StreamRead | JSONResponse:
    campaign = _local_campaign(db, campaign_id)
    if isinstance(campaign, JSONResponse):
        return campaign
    try:
        stream = await _owned_stream(campaign, stream_id, keitaro)
        names = await _names(keitaro)
        active = [
            row for row in stream_draft.stream_offers(db, stream_id) if row.status == stream_draft.STATUS_ACTIVE
        ]
        await keitaro.publish_stream_offers(
            stream_id,
            [
                {"offer_id": row.offer_id, "share": row.weight, "state": "active"}
                for row in active
            ],
            campaign_id=campaign.keitaro_id,
        )
    except KeitaroError as exc:
        return _detail(exc.status_code, exc.message)
    stream_draft.mark_dirty(db, stream_id, False)
    db.commit()
    return _stream_response(stream, db, names, campaign.keitaro_id)


@router.post(
    "/{campaign_id}/streams/{stream_id}/cancel",
    response_model=StreamRead,
    response_model_exclude_none=True,
)
async def cancel_campaign_stream(
    campaign_id: int,
    stream_id: int,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> StreamRead | JSONResponse:
    campaign = _local_campaign(db, campaign_id)
    if isinstance(campaign, JSONResponse):
        return campaign
    try:
        stream = await _owned_stream(campaign, stream_id, keitaro)
        names = await _names(keitaro)
    except KeitaroError as exc:
        return _detail(exc.status_code, exc.message)
    stream_draft.revert_stream_draft(db, stream, names)
    db.commit()
    return _stream_response(stream, db, names, campaign.keitaro_id)