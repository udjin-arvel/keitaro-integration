import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Campaign

KEITARO = "https://tracker.test/admin_api/v1"


def _seed(db_session: Session, **kwargs) -> Campaign:
    campaign = Campaign(
        name=kwargs.get("name", "Seed"),
        geo=kwargs.get("geo", "DE"),
        offer_id=kwargs.get("offer_id", 10),
        keitaro_id=kwargs.get("keitaro_id", 101),
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    return campaign


@respx.mock
def test_create_campaign_saves_local_row(client: TestClient, db_session: Session) -> None:
    respx.post(f"{KEITARO}/campaigns").mock(return_value=httpx.Response(200, json={"id": 101}))
    respx.post(f"{KEITARO}/streams").mock(side_effect=[
        httpx.Response(200, json={"id": 1}),
        httpx.Response(200, json={"id": 2}),
    ])

    response = client.post("/api/campaigns", json={"name": "My Campaign", "geo": "US", "offer_id": 42})

    assert response.status_code == 200
    body = response.json()
    assert body == {"success": True, "campaign_id": body["campaign_id"]}
    campaign = db_session.get(Campaign, body["campaign_id"])
    assert campaign is not None
    assert campaign.name == "My Campaign"
    assert campaign.geo == "US"
    assert campaign.offer_id == 42
    assert campaign.keitaro_id == 101

    campaign_call = respx.calls[0]
    assert campaign_call.request.method == "POST"
    assert b'"type": "weight"' in campaign_call.request.content
    assert b'"domain_id": 9' in campaign_call.request.content
    assert b'"traffic_source_id": 7' in campaign_call.request.content
    stream_calls = [c for c in respx.calls if c.request.url.path.endswith("/streams")]
    assert len(stream_calls) == 2
    white, offer = stream_calls
    assert b'"schema": "redirect"' in white.request.content
    assert b'"action_type": "http"' in white.request.content
    assert b'"schema": "landings"' in offer.request.content
    assert b'"action_type": "http"' in offer.request.content
    assert b'"offer_id": 42' in offer.request.content


@respx.mock
def test_create_invalid_api_key_does_not_persist(client: TestClient, db_session: Session) -> None:
    respx.post(f"{KEITARO}/campaigns").mock(
        return_value=httpx.Response(401, json={"error": "Invalid API key"}),
    )

    response = client.post("/api/campaigns", json={"name": "Bad Key", "geo": "US", "offer_id": 1})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"
    assert db_session.query(Campaign).count() == 0


@respx.mock
def test_create_rolls_back_campaign_if_stream_fails(client: TestClient, db_session: Session) -> None:
    respx.post(f"{KEITARO}/campaigns").mock(return_value=httpx.Response(200, json={"id": 77}))
    respx.post(f"{KEITARO}/streams").mock(return_value=httpx.Response(422, json={"error": "bad stream"}))
    respx.delete(f"{KEITARO}/campaigns/77").mock(return_value=httpx.Response(204))

    response = client.post("/api/campaigns", json={"name": "Partial", "geo": "PL", "offer_id": 5})

    assert response.status_code == 422
    assert response.json()["detail"] == "bad stream"
    assert db_session.query(Campaign).count() == 0
    assert any(call.request.method == "DELETE" for call in respx.calls)


def test_list_campaigns(client: TestClient, db_session: Session) -> None:
    first = _seed(db_session, name="Alpha", geo="FR", offer_id=3, keitaro_id=11)
    second = _seed(db_session, name="Beta", geo="IT", offer_id=4, keitaro_id=12)

    response = client.get("/api/campaigns")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == ["Beta", "Alpha"]
    item = next(row for row in response.json() if row["id"] == first.id)
    assert item["keitaro_id"] == 11
    assert item["keitaro_campaign_id"] == 11
    assert item["view_in_kt_url"] == "https://tracker.test/admin/#!/campaign/11/main"
    assert item["geo"] == "FR"
    assert second.id in {row["id"] for row in response.json()}


@respx.mock
def test_update_name_goes_to_keitaro(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, name="Old", geo="DE", offer_id=10, keitaro_id=101)
    route = respx.put(f"{KEITARO}/campaigns/101").mock(
        return_value=httpx.Response(200, json={"id": 101, "name": "New"}),
    )

    response = client.put(f"/api/campaigns/{campaign.id}", json={"name": "New"})

    assert response.status_code == 200
    assert response.json()["name"] == "New"
    assert response.json()["geo"] == "DE"
    assert route.called
    assert b'"name": "New"' in route.calls[0].request.content
    db_session.refresh(campaign)
    assert campaign.name == "New"


@respx.mock
def test_update_offer_updates_offer_stream(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, offer_id=10, keitaro_id=101)
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": 5, "name": "White Redirect"}, {"id": 6, "name": "Offer Redirect"}],
        ),
    )
    respx.get(f"{KEITARO}/offers/99").mock(return_value=httpx.Response(200, json={"id": 99, "name": "Offer 99"}))
    stream_route = respx.put(f"{KEITARO}/streams/6").mock(return_value=httpx.Response(200, json={"id": 6}))

    response = client.put(f"/api/campaigns/{campaign.id}", json={"offer_id": 99})

    assert response.status_code == 200
    assert response.json()["offer_id"] == 99
    assert stream_route.called
    assert b'"offer_id": 99' in stream_route.calls[0].request.content


@respx.mock
def test_delete_campaign(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    campaign_id = campaign.id
    respx.delete(f"{KEITARO}/campaigns/101").mock(return_value=httpx.Response(204))

    response = client.delete(f"/api/campaigns/{campaign_id}")

    assert response.status_code == 204
    db_session.expire_all()
    assert db_session.get(Campaign, campaign_id) is None


@respx.mock
def test_delete_when_already_gone_in_keitaro(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    campaign_id = campaign.id
    respx.delete(f"{KEITARO}/campaigns/101").mock(
        return_value=httpx.Response(404, json={"error": "Not found"}),
    )

    first = client.delete(f"/api/campaigns/{campaign_id}")
    second = client.delete(f"/api/campaigns/{campaign_id}")

    assert first.status_code == 204
    assert second.status_code == 204
    db_session.expire_all()
    assert db_session.get(Campaign, campaign_id) is None


def _stream_payload(**kwargs):
    data = {
        "id": 5,
        "name": "White Redirect",
        "type": "regular",
        "weight": 50,
        "schema": "redirect",
        "action_type": "http",
        "action_payload": "https://www.google.com/search?q=white",
        "state": "active",
        "position": 0,
        "campaign_id": 101,
    }
    data.update(kwargs)
    return data


def _mock_offer_catalog(*items) -> None:
    respx.get(f"{KEITARO}/offers").mock(return_value=httpx.Response(200, json=list(items)))


@respx.mock
def test_list_streams_maps_keitaro_fields(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog({"id": 42, "name": "Offer 42"})
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(
            200,
            json=[
                _stream_payload(),
                _stream_payload(
                    id=6,
                    name="Offer Redirect",
                    schema="landings",
                    action_payload=None,
                    offers=[{"offer_id": 42, "share": 100, "state": "active"}],
                    position=1,
                ),
            ],
        ),
    )

    response = client.get(f"/api/campaigns/{campaign.id}/streams")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == 5
    assert body[0]["name"] == "White Redirect"
    assert body[0]["type"] == "regular"
    assert body[0]["weight"] == 50
    assert body[0]["schema"] == "redirect"
    assert body[0]["action_type"] == "http"
    assert body[0]["keitaro_campaign_id"] == 101
    assert "redirect_url" not in body[0]
    assert "offers" not in body[0]
    assert body[1]["id"] == 6
    assert body[1]["schema"] == "landings"
    assert body[1]["action_type"] == "http"
    assert body[1]["offers"] == [
        {
            "id": 42,
            "offer_id": 42,
            "name": "Offer 42",
            "weight": 100,
            "status": "active",
            "is_pinned": False,
        }
    ]
    assert body[1]["is_dirty"] is False


@respx.mock
def test_list_streams_filters_by_query(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(
            200,
            json=[
                _stream_payload(),
                _stream_payload(id=1313859, name="Offer Redirect"),
            ],
        ),
    )

    by_name = client.get(f"/api/campaigns/{campaign.id}/streams", params={"q": "white"})
    by_id = client.get(f"/api/campaigns/{campaign.id}/streams", params={"q": "131"})

    assert [row["id"] for row in by_name.json()] == [5]
    assert [row["id"] for row in by_id.json()] == [1313859]


@respx.mock
def test_list_streams_falls_back_to_campaign_when_subresource_missing(
    client: TestClient, db_session: Session
) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(404, json={"error": "Not Found"}),
    )
    _mock_offer_catalog()
    respx.get(f"{KEITARO}/campaigns/101").mock(
        return_value=httpx.Response(200, json={"id": 101, "streams": [_stream_payload()]}),
    )

    response = client.get(f"/api/campaigns/{campaign.id}/streams")

    assert response.status_code == 200
    assert response.json()[0]["id"] == 5


def test_list_streams_missing_campaign(client: TestClient) -> None:
    response = client.get("/api/campaigns/999/streams")
    assert response.status_code == 404
    assert response.json()["detail"] == "Кампания не найдена"


@respx.mock
def test_list_streams_keitaro_error(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(401, json={"error": "Invalid API key"}),
    )

    response = client.get(f"/api/campaigns/{campaign.id}/streams")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


@respx.mock
def test_delete_stream_success(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    respx.delete(f"{KEITARO}/streams/6").mock(return_value=httpx.Response(204))

    response = client.delete(f"/api/campaigns/{campaign.id}/streams/6")

    assert response.status_code == 200
    assert response.json() == {"success": True}


@respx.mock
def test_delete_stream_already_gone(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    respx.delete(f"{KEITARO}/streams/6").mock(return_value=httpx.Response(404, json={"error": "Not found"}))

    response = client.delete(f"/api/campaigns/{campaign.id}/streams/6")

    assert response.status_code == 200
    assert response.json()["success"] is True


@respx.mock
def test_delete_stream_keitaro_error(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    respx.delete(f"{KEITARO}/streams/6").mock(return_value=httpx.Response(500, json={"error": "boom"}))

    response = client.delete(f"/api/campaigns/{campaign.id}/streams/6")

    assert response.status_code == 400
    assert response.json() == {"success": False, "error": "boom"}


def test_delete_stream_missing_campaign(client: TestClient) -> None:
    response = client.delete("/api/campaigns/999/streams/6")
    assert response.status_code == 404
    assert response.json()["detail"] == "Кампания не найдена"


def _offer_stream(**kwargs):
    data = _stream_payload(
        id=6,
        name="Offer Redirect",
        schema="landings",
        action_payload=None,
        offers=[{"offer_id": 10, "share": 100, "state": "active"}],
    )
    data.update(kwargs)
    return data


def _mock_stream(stream_id: int = 6, **kwargs) -> None:
    respx.get(f"{KEITARO}/streams/{stream_id}").mock(
        return_value=httpx.Response(200, json=_offer_stream(id=stream_id, **kwargs)),
    )


def _mock_offer(offer_id: int, name: str | None = None) -> None:
    respx.get(f"{KEITARO}/offers/{offer_id}").mock(
        return_value=httpx.Response(200, json={"id": offer_id, "name": name or f"Offer {offer_id}"}),
    )


@respx.mock
def test_add_offer_recalculates_and_marks_dirty(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, offer_id=10, keitaro_id=101)
    _mock_offer_catalog({"id": 10, "name": "Offer 10"}, {"id": 20, "name": "Offer 20"})
    _mock_stream()
    _mock_offer(20)
    put_route = respx.put(f"{KEITARO}/streams/6").mock(return_value=httpx.Response(200, json={}))

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/offers", json={"offer_id": 20})

    assert response.status_code == 200
    assert not put_route.called
    body = response.json()
    assert body["is_dirty"] is True
    weights = {row["offer_id"]: row["weight"] for row in body["offers"]}
    assert weights == {10: 50, 20: 50}
    assert all(row["status"] == "active" for row in body["offers"])


@respx.mock
def test_add_offer_to_empty_stream(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    _mock_stream(5, offers=[])
    _mock_offer(123)
    put_route = respx.put(f"{KEITARO}/streams/5").mock(return_value=httpx.Response(200, json={}))

    response = client.post(f"/api/campaigns/{campaign.id}/streams/5/offers", json={"offer_id": 123})

    assert response.status_code == 200
    assert not put_route.called
    assert response.json()["offers"][0]["weight"] == 100
    assert response.json()["is_dirty"] is True


@respx.mock
def test_add_offer_missing_in_keitaro(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    _mock_stream()
    respx.get(f"{KEITARO}/offers/20").mock(return_value=httpx.Response(404, json={"error": "Not found"}))

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/offers", json={"offer_id": 20})

    assert response.status_code == 404


@respx.mock
def test_add_offer_duplicate_active(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    _mock_stream()
    _mock_offer(10)

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/offers", json={"offer_id": 10})

    assert response.status_code == 409
    assert response.json()["detail"] == "Оффер уже добавлен в поток"


@respx.mock
def test_add_offer_rejects_foreign_stream(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    respx.get(f"{KEITARO}/streams/9").mock(
        return_value=httpx.Response(200, json=_stream_payload(id=9, campaign_id=777)),
    )
    put_route = respx.put(f"{KEITARO}/streams/9").mock(return_value=httpx.Response(200, json={}))

    response = client.post(f"/api/campaigns/{campaign.id}/streams/9/offers", json={"offer_id": 1})

    assert response.status_code == 404
    assert response.json()["detail"] == "Поток не найден"
    assert not put_route.called


@respx.mock
def test_add_offer_keitaro_error_keeps_local_offer(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, offer_id=10, keitaro_id=101)
    respx.get(f"{KEITARO}/streams/6").mock(return_value=httpx.Response(500, json={"error": "tracker down"}))

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/offers", json={"offer_id": 20})

    assert response.status_code == 500
    assert response.json()["detail"] == "tracker down"
    db_session.refresh(campaign)
    assert campaign.offer_id == 10


@respx.mock
def test_remove_offer_marks_removed(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    offers = [{"offer_id": 10, "share": 50}, {"offer_id": 20, "share": 50}]
    _mock_stream(offers=offers)
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(200, json=[_offer_stream(offers=offers)]),
    )
    client.get(f"/api/campaigns/{campaign.id}/streams")

    response = client.delete(f"/api/campaigns/{campaign.id}/streams/6/offers/20")

    assert response.status_code == 200
    by_id = {row["offer_id"]: row for row in response.json()["offers"]}
    assert by_id[20]["status"] == "removed"
    assert by_id[20]["weight"] == 0
    assert by_id[10]["weight"] == 100
    assert response.json()["is_dirty"] is True


@respx.mock
def test_restore_offer(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    _mock_stream(offers=[{"offer_id": 10, "share": 50}, {"offer_id": 20, "share": 50}])
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(
            200,
            json=[_offer_stream(offers=[{"offer_id": 10, "share": 50}, {"offer_id": 20, "share": 50}])],
        ),
    )
    client.get(f"/api/campaigns/{campaign.id}/streams")
    client.delete(f"/api/campaigns/{campaign.id}/streams/6/offers/20")

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/offers/20/restore")

    assert response.status_code == 200
    by_id = {row["offer_id"]: row for row in response.json()["offers"]}
    assert by_id[20]["status"] == "active"
    assert by_id[10]["weight"] == 50
    assert by_id[20]["weight"] == 50
    assert response.json()["is_dirty"] is True


@respx.mock
def test_pin_weight_stays_on_add(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    _mock_stream()
    _mock_offer(20)
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(200, json=[_offer_stream()]),
    )
    client.get(f"/api/campaigns/{campaign.id}/streams")
    pin = client.patch(
        f"/api/campaigns/{campaign.id}/streams/6/offers/10/pin",
        json={"is_pinned": True},
    )
    assert pin.json()["offers"][0]["is_pinned"] is True
    assert pin.json()["offers"][0]["weight"] == 100

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/offers", json={"offer_id": 20})

    by_id = {row["offer_id"]: row for row in response.json()["offers"]}
    assert by_id[10]["weight"] == 100
    assert by_id[10]["is_pinned"] is True
    assert by_id[20]["weight"] == 0


@respx.mock
def test_publish_pushes_to_keitaro(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    _mock_stream()
    _mock_offer(20)
    put_route = respx.put(f"{KEITARO}/streams/6").mock(return_value=httpx.Response(200, json={"id": 6}))
    client.post(f"/api/campaigns/{campaign.id}/streams/6/offers", json={"offer_id": 20})

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/publish")

    assert response.status_code == 200
    assert response.json()["is_dirty"] is False
    assert put_route.called
    content = put_route.calls[0].request.content
    assert b'"schema": "landings"' in content
    assert b'"offer_id": 10' in content
    assert b'"offer_id": 20' in content
    assert b'"share": 50' in content


@respx.mock
def test_publish_error_keeps_dirty(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    _mock_stream()
    _mock_offer(20)
    client.post(f"/api/campaigns/{campaign.id}/streams/6/offers", json={"offer_id": 20})
    respx.put(f"{KEITARO}/streams/6").mock(return_value=httpx.Response(500, json={"error": "boom"}))

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/publish")

    assert response.status_code == 500
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(200, json=[_offer_stream()]),
    )
    listed = client.get(f"/api/campaigns/{campaign.id}/streams")
    offer_stream = next(row for row in listed.json() if row["id"] == 6)
    assert offer_stream["is_dirty"] is True


@respx.mock
def test_cancel_reloads_from_keitaro(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    _mock_stream()
    _mock_offer(20)
    client.post(f"/api/campaigns/{campaign.id}/streams/6/offers", json={"offer_id": 20})
    _mock_stream(offers=[{"offer_id": 10, "share": 100, "state": "active"}])

    response = client.post(f"/api/campaigns/{campaign.id}/streams/6/cancel")

    assert response.status_code == 200
    assert response.json()["is_dirty"] is False
    by_id = {row["offer_id"]: row for row in response.json()["offers"]}
    assert by_id[10]["weight"] == 100
    assert by_id[10]["status"] == "active"
    assert by_id[20]["status"] == "removed"
    assert by_id[20]["weight"] == 0


@respx.mock
def test_sync_marks_missing_keitaro_offer_removed(client: TestClient, db_session: Session) -> None:
    campaign = _seed(db_session, keitaro_id=101)
    _mock_offer_catalog()
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(
            200,
            json=[_offer_stream(offers=[{"offer_id": 10, "share": 50}, {"offer_id": 20, "share": 50}])],
        ),
    )
    client.get(f"/api/campaigns/{campaign.id}/streams")
    respx.get(f"{KEITARO}/campaigns/101/streams").mock(
        return_value=httpx.Response(
            200,
            json=[_offer_stream(offers=[{"offer_id": 10, "share": 100}])],
        ),
    )

    response = client.post(f"/api/campaigns/{campaign.id}/streams/sync")

    assert response.status_code == 200
    by_id = {row["offer_id"]: row for row in response.json()[0]["offers"]}
    assert by_id[20]["status"] == "removed"
    assert by_id[20]["weight"] == 0
    assert by_id[10]["status"] == "active"
    assert response.json()[0]["is_dirty"] is False


@respx.mock
def test_list_offers(client: TestClient) -> None:
    respx.get(f"{KEITARO}/offers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "name": "A", "group_id": 5, "state": "active"},
                {"id": 2, "name": "B", "group_id": 6, "state": "disabled"},
            ],
        ),
    )

    response = client.get("/api/offers")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "name": "A", "group_id": 5, "state": "active"},
        {"id": 2, "name": "B", "group_id": 6, "state": "disabled"},
    ]


def test_redistribute_weights_remainder() -> None:
    from models import StreamOffer
    from services import stream_draft

    rows = [
        StreamOffer(stream_id=1, offer_id=i, weight=0, is_pinned=False, status=stream_draft.STATUS_ACTIVE)
        for i in range(6)
    ]
    stream_draft.redistribute_weights(rows)
    assert [row.weight for row in rows] == [17, 17, 17, 17, 16, 16]
