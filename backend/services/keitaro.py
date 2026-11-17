from __future__ import annotations

import json
import logging
import re
import secrets
from typing import Any
from urllib.parse import urljoin

import httpx

from config import Settings, get_settings
from exceptions import KeitaroError

logger = logging.getLogger("keitaro")

WHITE_REDIRECT_URL = "https://www.google.com/search?q=почему+я+не+вижу+свою+рекламу"
WHITE_STREAM_NAME = "White Redirect"
OFFER_STREAM_NAME = "Offer Redirect"
REQUEST_TIMEOUT = 15.0


def _extract_offer_id(item: Any) -> int | None:
    if not isinstance(item, dict):
        return None
    raw = item.get("offer_id", item.get("id"))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _admin_base(url: str) -> str:
    return url.rstrip("/") + "/admin_api/v1/"


def campaign_alias(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    suffix = secrets.token_hex(2)
    if not slug:
        return f"campaign-{suffix}"
    return f"{slug}-{suffix}"


def _parse_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or f"Keitaro HTTP {response.status_code}"
    if isinstance(payload, dict):
        error = payload.get("error") or payload.get("message") or payload.get("detail")
        if isinstance(error, str) and error:
            return error
        if error:
            return json.dumps(error, ensure_ascii=False)
        field_errors = []
        for key, value in payload.items():
            if isinstance(value, list):
                field_errors.append(f"{key}: {', '.join(str(item) for item in value)}")
            elif isinstance(value, str):
                field_errors.append(f"{key}: {value}")
        if field_errors:
            return "; ".join(field_errors)
    return json.dumps(payload, ensure_ascii=False) if payload else f"Keitaro HTTP {response.status_code}"


class KeitaroClient:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings or get_settings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=_admin_base(self.settings.keitaro_api_url),
            headers={
                "Api-Key": self.settings.keitaro_api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> Any:
        url = urljoin(str(self._client.base_url), path.lstrip("/"))
        logger.info("Keitaro %s %s body=%s", method, url, json.dumps(json_body, ensure_ascii=False) if json_body else None)
        try:
            response = await self._client.request(method, path, json=json_body)
        except httpx.RequestError as exc:
            raise KeitaroError(f"Keitaro недоступен: {exc}", status_code=502) from exc
        logger.info("Keitaro %s %s status=%s", method, url, response.status_code)
        if response.is_success:
            if response.status_code == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                return None
        raise KeitaroError(_parse_error(response), status_code=response.status_code)

    def _campaign_extras(self) -> dict[str, Any]:
        extras: dict[str, Any] = {}
        if self.settings.keitaro_domain_id is not None:
            extras["domain_id"] = self.settings.keitaro_domain_id
        if self.settings.keitaro_group_id is not None:
            extras["group_id"] = self.settings.keitaro_group_id
        if self.settings.keitaro_source_id is not None:
            extras["traffic_source_id"] = self.settings.keitaro_source_id
        return extras

    async def create_campaign(self, name: str) -> dict[str, Any]:
        payload = {
            "name": name,
            "alias": campaign_alias(name),
            "type": "weight",
            **self._campaign_extras(),
        }
        data = await self._request("POST", "campaigns", payload)
        if not isinstance(data, dict) or data.get("id") is None:
            raise KeitaroError("Keitaro не вернул id кампании")
        return data

    async def update_campaign(self, keitaro_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        return await self._request("PUT", f"campaigns/{keitaro_id}", data)

    async def delete_campaign(self, keitaro_id: int) -> None:
        try:
            await self._request("DELETE", f"campaigns/{keitaro_id}")
        except KeitaroError as exc:
            if exc.status_code == 404:
                return
            raise

    async def create_white_stream(self, campaign_id: int) -> dict[str, Any]:
        payload = {
            "campaign_id": campaign_id,
            "type": "regular",
            "name": WHITE_STREAM_NAME,
            "schema": "redirect",
            "action_type": "http",
            "action_payload": WHITE_REDIRECT_URL,
            "weight": 50,
        }
        return await self._request("POST", "streams", payload)

    async def create_offer_stream(self, campaign_id: int, offer_id: int) -> dict[str, Any]:
        # StreamRequest: schema is landings | redirect | action, action_type is required.
        # Offers are a separate array (offer_id + share), not a schema value.
        payload = {
            "campaign_id": campaign_id,
            "type": "regular",
            "name": OFFER_STREAM_NAME,
            "schema": "landings",
            "action_type": "http",
            "weight": 50,
            "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
        }
        return await self._request("POST", "streams", payload)

    def _normalize_streams(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            streams = data.get("streams") or data.get("data") or []
            if isinstance(streams, list):
                return [item for item in streams if isinstance(item, dict)]
        return []

    async def get_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        try:
            data = await self._request("GET", f"campaigns/{campaign_id}/streams")
        except KeitaroError as exc:
            if exc.status_code != 404:
                raise
            campaign = await self._request("GET", f"campaigns/{campaign_id}")
            data = campaign if isinstance(campaign, dict) else []
        return self._normalize_streams(data)

    async def list_streams(self, keitaro_id: int) -> list[dict[str, Any]]:
        return await self.get_streams(keitaro_id)

    async def get_stream(self, stream_id: int) -> dict[str, Any]:
        data = await self._request("GET", f"streams/{stream_id}")
        if not isinstance(data, dict):
            raise KeitaroError("Keitaro не вернул поток", status_code=502)
        return data

    async def delete_stream(self, stream_id: int) -> bool:
        try:
            await self._request("DELETE", f"streams/{stream_id}")
        except KeitaroError as exc:
            if exc.status_code == 404:
                return True
            raise
        return True

    def owned_stream(self, stream: dict[str, Any], campaign_id: int) -> dict[str, Any]:
        raw_campaign_id = stream.get("campaign_id")
        try:
            stream_campaign_id = int(raw_campaign_id)
        except (TypeError, ValueError):
            stream_campaign_id = None
        if stream_campaign_id != campaign_id:
            raise KeitaroError("Поток не найден", status_code=404)
        return stream

    async def get_owned_stream(self, stream_id: int, campaign_id: int) -> dict[str, Any]:
        return self.owned_stream(await self.get_stream(stream_id), campaign_id)

    async def publish_stream_offers(
        self,
        stream_id: int,
        offers: list[dict[str, Any]],
        *,
        campaign_id: int,
    ) -> dict[str, Any]:
        stream = await self.get_owned_stream(stream_id, campaign_id)
        payload = {
            "schema": "landings",
            "action_type": "http",
            "offers": offers,
        }
        data = await self._request("PUT", f"streams/{stream_id}", payload)
        if isinstance(data, dict):
            return data
        return {**stream, **payload}

    async def get_offer(self, offer_id: int) -> dict[str, Any]:
        data = await self._request("GET", f"offers/{offer_id}")
        if not isinstance(data, dict) or data.get("id") is None:
            raise KeitaroError("Оффер не найден", status_code=404)
        return data

    async def list_offers(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "offers")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            items = data.get("offers") or data.get("data") or []
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    async def offer_names(self) -> dict[int, str]:
        try:
            items = await self.list_offers()
        except KeitaroError:
            return {}
        names: dict[int, str] = {}
        for item in items:
            raw_id = item.get("id")
            try:
                offer_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                names[offer_id] = name
        return names

    async def update_offer_stream(self, keitaro_id: int, offer_id: int) -> int:
        streams = await self.list_streams(keitaro_id)
        offer_stream = next((s for s in streams if s.get("name") == OFFER_STREAM_NAME), None)
        if offer_stream is None or offer_stream.get("id") is None:
            raise KeitaroError("Поток Offer Redirect не найден в Keitaro")
        stream_id = int(offer_stream["id"])
        await self._request(
            "PUT",
            f"streams/{stream_id}",
            {
                "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
                "schema": "landings",
                "action_type": "http",
            },
        )
        return stream_id

    async def create_campaign_with_streams(self, name: str, offer_id: int) -> int:
        campaign = await self.create_campaign(name)
        keitaro_id = int(campaign["id"])
        try:
            await self.create_white_stream(keitaro_id)
            await self.create_offer_stream(keitaro_id, offer_id)
        except Exception:
            try:
                await self.delete_campaign(keitaro_id)
            except KeitaroError:
                logger.exception("Не удалось откатить кампанию Keitaro %s", keitaro_id)
            raise
        return keitaro_id
