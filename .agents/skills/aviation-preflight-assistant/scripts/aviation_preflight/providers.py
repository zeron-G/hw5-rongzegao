"""External data providers for weather and FAA advisories."""

from __future__ import annotations

from typing import Protocol

import requests


class DataProvider(Protocol):
    """Protocol used by briefing logic and tests."""

    def get_metar(self, ids: list[str]) -> list[dict]:
        ...

    def get_taf(self, ids: list[str]) -> list[dict]:
        ...

    def get_station_info(self, ids: list[str]) -> list[dict]:
        ...

    def get_airsigmet(self) -> list[dict]:
        ...

    def get_gairmet(self) -> list[dict]:
        ...

    def get_cwa(self) -> list[dict]:
        ...

    def get_mis(self) -> list[dict]:
        ...

    def get_tfr_list(self) -> list[dict]:
        ...

    def get_tfr_geometries(self) -> list[dict]:
        ...


class AviationDataProvider:
    """Live provider against AWC and FAA public endpoints."""

    AWC_BASE = "https://aviationweather.gov/api/data"
    FAA_TFR_BASE = "https://tfr.faa.gov/tfrapi"
    FAA_TFR_WFS = (
        "https://tfr.faa.gov/geoserver/TFR/ows"
        "?service=WFS&version=1.1.0&request=GetFeature"
        "&typeName=TFR:V_TFR_LOC&maxFeatures=300"
        "&outputFormat=application/json&srsname=EPSG:3857"
    )

    def __init__(
        self,
        user_agent: str = "aviation-preflight-assistant/0.1",
        timeout: int = 20,
    ) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def _request_json(self, url: str, params: dict | None = None) -> list[dict] | dict:
        response = self.session.get(url, params=params, timeout=self.timeout)
        if response.status_code == 204:
            return []
        response.raise_for_status()
        payload = response.json()
        if payload is None:
            return []
        return payload

    @staticmethod
    def _clean_ids(ids: list[str]) -> str:
        unique = sorted({item.strip().upper() for item in ids if item and item.strip()})
        return ",".join(unique)

    def get_metar(self, ids: list[str]) -> list[dict]:
        query_ids = self._clean_ids(ids)
        if not query_ids:
            return []
        data = self._request_json(
            f"{self.AWC_BASE}/metar",
            {"ids": query_ids, "format": "json"},
        )
        return data if isinstance(data, list) else []

    def get_taf(self, ids: list[str]) -> list[dict]:
        query_ids = self._clean_ids(ids)
        if not query_ids:
            return []
        data = self._request_json(
            f"{self.AWC_BASE}/taf",
            {"ids": query_ids, "format": "json"},
        )
        return data if isinstance(data, list) else []

    def get_station_info(self, ids: list[str]) -> list[dict]:
        query_ids = self._clean_ids(ids)
        if not query_ids:
            return []
        data = self._request_json(
            f"{self.AWC_BASE}/stationinfo",
            {"ids": query_ids, "format": "json"},
        )
        return data if isinstance(data, list) else []

    def get_airsigmet(self) -> list[dict]:
        data = self._request_json(f"{self.AWC_BASE}/airsigmet", {"format": "json"})
        return data if isinstance(data, list) else []

    def get_gairmet(self) -> list[dict]:
        data = self._request_json(f"{self.AWC_BASE}/gairmet", {"format": "json"})
        return data if isinstance(data, list) else []

    def get_cwa(self) -> list[dict]:
        data = self._request_json(f"{self.AWC_BASE}/cwa", {"format": "json"})
        return data if isinstance(data, list) else []

    def get_mis(self) -> list[dict]:
        data = self._request_json(f"{self.AWC_BASE}/mis", {"format": "json"})
        return data if isinstance(data, list) else []

    def get_tfr_list(self) -> list[dict]:
        data = self._request_json(f"{self.FAA_TFR_BASE}/getTfrList")
        return data if isinstance(data, list) else []

    def get_tfr_geometries(self) -> list[dict]:
        data = self._request_json(self.FAA_TFR_WFS)
        if isinstance(data, dict):
            return list(data.get("features", []))
        return []
