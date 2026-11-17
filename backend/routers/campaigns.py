from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from database import get_db
from exceptions import KeitaroError
from models import Campaign
from routers.deps import get_keitaro
from schemas import CampaignCreate, CampaignCreateResult, CampaignRead, CampaignUpdate
from services import stream_draft
from services.keitaro import KeitaroClient

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.post("", response_model=CampaignCreateResult)
async def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> CampaignCreateResult:
    try:
        keitaro_id = await keitaro.create_campaign_with_streams(payload.name, payload.offer_id)
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    campaign = Campaign(
        name=payload.name,
        geo=payload.geo,
        offer_id=payload.offer_id,
        keitaro_id=keitaro_id,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return CampaignCreateResult(success=True, campaign_id=campaign.id)


@router.get("", response_model=list[CampaignRead])
def list_campaigns(db: Session = Depends(get_db)) -> list[Campaign]:
    return db.query(Campaign).order_by(Campaign.id.desc()).all()


@router.put("/{campaign_id}", response_model=CampaignRead)
async def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Кампания не найдена")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return campaign
    if campaign.keitaro_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У кампании нет keitaro_id, удалённое обновление невозможно",
        )
    try:
        if "name" in changes:
            await keitaro.update_campaign(campaign.keitaro_id, {"name": changes["name"]})
        if "offer_id" in changes:
            stream_id = await keitaro.update_offer_stream(campaign.keitaro_id, changes["offer_id"])
            offer = await keitaro.get_offer(changes["offer_id"])
            offer_name = offer.get("name") if isinstance(offer.get("name"), str) else None
            stream_draft.replace_with_single_offer(db, stream_id, changes["offer_id"], offer_name)
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    for field, value in changes.items():
        setattr(campaign, field, value)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    keitaro: KeitaroClient = Depends(get_keitaro),
) -> Response:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if campaign.keitaro_id is not None:
        try:
            await keitaro.delete_campaign(campaign.keitaro_id)
        except KeitaroError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    db.delete(campaign)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)