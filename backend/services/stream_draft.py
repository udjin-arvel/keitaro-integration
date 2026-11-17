from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from exceptions import WeightError
from models import StreamOffer, StreamPublishState
from services.keitaro import _extract_offer_id


STATUS_ACTIVE = "active"
STATUS_REMOVED = "removed"


def redistribute_weights(offers: list[StreamOffer]) -> None:
    for offer in offers:
        if offer.status != STATUS_ACTIVE:
            offer.weight = 0
    active = [offer for offer in offers if offer.status == STATUS_ACTIVE]
    pinned = [offer for offer in active if offer.is_pinned]
    unpinned = [offer for offer in active if not offer.is_pinned]
    remaining = 100 - sum(offer.weight for offer in pinned)
    if remaining < 0:
        raise WeightError()
    if not unpinned:
        return
    base, remainder = divmod(remaining, len(unpinned))
    for index, offer in enumerate(unpinned):
        offer.weight = base + (1 if index < remainder else 0)


def publish_state(db: Session, stream_id: int) -> StreamPublishState:
    state = db.get(StreamPublishState, stream_id)
    if state is None:
        state = StreamPublishState(stream_id=stream_id, is_dirty=False)
        db.add(state)
        db.flush()
    return state


def is_dirty(db: Session, stream_id: int) -> bool:
    state = db.get(StreamPublishState, stream_id)
    return bool(state and state.is_dirty)


def mark_dirty(db: Session, stream_id: int, dirty: bool = True) -> None:
    publish_state(db, stream_id).is_dirty = dirty


def stream_offers(db: Session, stream_id: int) -> list[StreamOffer]:
    return (
        db.query(StreamOffer)
        .filter(StreamOffer.stream_id == stream_id)
        .order_by(StreamOffer.id.asc())
        .all()
    )


def keitaro_offer_shares(stream: dict[str, Any]) -> dict[int, int]:
    shares: dict[int, int] = {}
    for item in stream.get("offers") or []:
        offer_id = _extract_offer_id(item)
        if offer_id is None:
            continue
        raw = item.get("share", item.get("weight", 0)) if isinstance(item, dict) else 0
        try:
            share = int(raw or 0)
        except (TypeError, ValueError):
            share = 0
        shares[offer_id] = share
    return shares


def _offer_name(names: dict[int, str], offer_id: int) -> str | None:
    name = names.get(offer_id)
    return name if isinstance(name, str) and name else None


def sync_clean_stream(db: Session, stream: dict[str, Any], names: dict[int, str] | None = None) -> None:
    stream_id = int(stream["id"])
    if is_dirty(db, stream_id):
        return
    apply_archive_sync(db, stream, names or {})


def apply_archive_sync(db: Session, stream: dict[str, Any], names: dict[int, str] | None = None) -> None:
    stream_id = int(stream["id"])
    catalog = names or {}
    remote = keitaro_offer_shares(stream)
    local = stream_offers(db, stream_id)
    by_id = {row.offer_id: row for row in local}
    for offer_id, share in remote.items():
        row = by_id.get(offer_id)
        if row is None:
            db.add(
                StreamOffer(
                    stream_id=stream_id,
                    offer_id=offer_id,
                    offer_name=_offer_name(catalog, offer_id),
                    weight=share,
                    is_pinned=False,
                    status=STATUS_ACTIVE,
                )
            )
        elif row.status == STATUS_REMOVED:
            row.status = STATUS_ACTIVE
            row.weight = share
            row.is_pinned = False
            if not row.offer_name:
                row.offer_name = _offer_name(catalog, offer_id)
        else:
            row.weight = share
            if not row.offer_name:
                row.offer_name = _offer_name(catalog, offer_id)
    for offer_id, row in by_id.items():
        if offer_id not in remote and row.status == STATUS_ACTIVE:
            row.status = STATUS_REMOVED
            row.weight = 0
    db.flush()


def revert_stream_draft(db: Session, stream: dict[str, Any], names: dict[int, str] | None = None) -> None:
    stream_id = int(stream["id"])
    catalog = names or {}
    remote = keitaro_offer_shares(stream)
    local = stream_offers(db, stream_id)
    by_id = {row.offer_id: row for row in local}
    for offer_id, share in remote.items():
        row = by_id.get(offer_id)
        if row is None:
            db.add(
                StreamOffer(
                    stream_id=stream_id,
                    offer_id=offer_id,
                    offer_name=_offer_name(catalog, offer_id),
                    weight=share,
                    is_pinned=False,
                    status=STATUS_ACTIVE,
                )
            )
        else:
            row.status = STATUS_ACTIVE
            row.weight = share
            row.is_pinned = False
            if not row.offer_name:
                row.offer_name = _offer_name(catalog, offer_id)
    for offer_id, row in by_id.items():
        if offer_id not in remote:
            row.status = STATUS_REMOVED
            row.weight = 0
    mark_dirty(db, stream_id, False)
    db.flush()


def replace_from_keitaro(db: Session, stream: dict[str, Any], names: dict[int, str] | None = None) -> None:
    stream_id = int(stream["id"])
    catalog = names or {}
    db.query(StreamOffer).filter(StreamOffer.stream_id == stream_id).delete()
    for offer_id, share in keitaro_offer_shares(stream).items():
        db.add(
            StreamOffer(
                stream_id=stream_id,
                offer_id=offer_id,
                offer_name=_offer_name(catalog, offer_id),
                weight=share,
                is_pinned=False,
                status=STATUS_ACTIVE,
            )
        )
    mark_dirty(db, stream_id, False)
    db.flush()


def replace_with_single_offer(
    db: Session,
    stream_id: int,
    offer_id: int,
    offer_name: str | None = None,
) -> None:
    replace_from_keitaro(
        db,
        {"id": stream_id, "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}]},
        {offer_id: offer_name} if offer_name else {},
    )


def delete_stream_local(db: Session, stream_id: int) -> None:
    db.query(StreamOffer).filter(StreamOffer.stream_id == stream_id).delete()
    db.query(StreamPublishState).filter(StreamPublishState.stream_id == stream_id).delete()


def recalc_active(db: Session, stream_id: int) -> None:
    rows = stream_offers(db, stream_id)
    redistribute_weights(rows)
    db.flush()


def serialize_offer(row: StreamOffer, names: dict[int, str]) -> dict[str, Any]:
    display_name = row.offer_name or names.get(row.offer_id)
    return {
        "id": row.offer_id,
        "offer_id": row.offer_id,
        "name": display_name,
        "weight": row.weight,
        "status": row.status,
        "is_pinned": row.is_pinned,
    }


def serialize_stream(
    raw: dict[str, Any],
    db: Session,
    names: dict[int, str],
    *,
    keitaro_campaign_id: int | None = None,
) -> dict[str, Any]:
    stream_id = int(raw["id"])
    rows = stream_offers(db, stream_id)
    payload: dict[str, Any] = {
        "id": stream_id,
        "name": raw.get("name"),
        "type": raw.get("type"),
        "weight": raw.get("weight"),
        "schema": raw.get("schema"),
        "action_type": raw.get("action_type"),
    }
    if keitaro_campaign_id is not None:
        payload["keitaro_campaign_id"] = keitaro_campaign_id
    if not rows:
        return payload
    payload["offers"] = [serialize_offer(row, names) for row in rows]
    payload["is_dirty"] = is_dirty(db, stream_id)
    return payload