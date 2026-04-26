from __future__ import annotations

from typing import Any

from aviation_preflight.providers import AviationDataProvider


class DummyResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


def test_request_json_handles_204() -> None:
    provider = AviationDataProvider()

    class DummySession:
        @staticmethod
        def get(*args, **kwargs):  # type: ignore[no-untyped-def]
            return DummyResponse(204, None)

    provider.session = DummySession()  # type: ignore[assignment]
    data = provider._request_json("https://example.test")
    assert data == []


def test_provider_methods_route_to_endpoints(monkeypatch) -> None:
    provider = AviationDataProvider()
    calls: list[tuple[str, dict | None]] = []

    def fake_request(url: str, params: dict | None = None) -> list[dict] | dict:
        calls.append((url, params))
        if "getTfrList" in url:
            return [{"notam_id": "9/9999"}]
        if "geoserver" in url:
            return {"features": [{"id": "f1"}]}
        if "stationinfo" in url:
            return [{"icaoId": "KGAI"}]
        return [{"icaoId": "KGAI"}]

    monkeypatch.setattr(provider, "_request_json", fake_request)

    assert provider.get_metar(["kgai", "KGAI"]) == [{"icaoId": "KGAI"}]
    assert provider.get_taf(["KGAI"]) == [{"icaoId": "KGAI"}]
    assert provider.get_station_info(["KGAI"]) == [{"icaoId": "KGAI"}]
    assert provider.get_airsigmet() == [{"icaoId": "KGAI"}]
    assert provider.get_gairmet() == [{"icaoId": "KGAI"}]
    assert provider.get_cwa() == [{"icaoId": "KGAI"}]
    assert provider.get_mis() == [{"icaoId": "KGAI"}]
    assert provider.get_tfr_list() == [{"notam_id": "9/9999"}]
    assert provider.get_tfr_geometries() == [{"id": "f1"}]

    # Empty IDs should short-circuit without calling request.
    before = len(calls)
    assert provider.get_metar([]) == []
    assert provider.get_taf([]) == []
    assert provider.get_station_info([]) == []
    assert len(calls) == before
