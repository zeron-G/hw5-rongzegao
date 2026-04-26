from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = (
    PROJECT_ROOT
    / ".agents"
    / "skills"
    / "aviation-preflight-assistant"
    / "scripts"
)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def references_dir() -> Path:
    return (
        PROJECT_ROOT
        / ".agents"
        / "skills"
        / "aviation-preflight-assistant"
        / "references"
    )


class FakeProvider:
    def __init__(self) -> None:
        self.metar_data = [
            {
                "icaoId": "KGAI",
                "rawOb": "METAR KGAI 261530Z 14008KT 10SM SCT035 20/12 A3005 RMK AO2",
                "lat": 39.1696,
                "lon": -77.1653,
                "temp": 20,
                "wdir": 140,
                "wspd": 8,
                "altim": 1017.5,
                "fltCat": "VFR",
                "visib": "10+",
            },
            {
                "icaoId": "KJYO",
                "rawOb": "METAR KJYO 261530Z 17009KT 10SM SCT030 21/11 A3004 RMK AO2",
                "lat": 39.0779,
                "lon": -77.5575,
                "temp": 21,
                "wdir": 170,
                "wspd": 9,
                "altim": 1017.1,
                "fltCat": "VFR",
                "visib": "10+",
            },
            {
                "icaoId": "KIAD",
                "rawOb": "METAR KIAD 261530Z 17010KT 10SM SCT025 BKN060 19/10 A3003",
                "lat": 38.9474,
                "lon": -77.4599,
                "temp": 19,
                "wdir": 170,
                "wspd": 10,
                "altim": 1016.8,
                "fltCat": "VFR",
                "visib": "10+",
            },
        ]
        self.taf_data = [
            {
                "icaoId": "KJYO",
                "rawTAF": (
                    "TAF KJYO 261130Z 2612/2712 17008KT P6SM SCT035 "
                    "FM262200 21007KT P6SM SCT050"
                ),
            },
            {
                "icaoId": "KIAD",
                "rawTAF": (
                    "TAF KIAD 261130Z 2612/2718 17009KT P6SM SCT035 "
                    "FM270000 20007KT P6SM BKN060"
                ),
            },
        ]
        self.station_data = [
            {
                "id": "KXYZ",
                "icaoId": "KXYZ",
                "site": "Test Airport",
                "lat": 39.2,
                "lon": -77.2,
                "elev": 160,
                "state": "MD",
            }
        ]
        self.airsigmet_data = [
            {
                "airSigmetType": "SIGMET",
                "hazard": "CONVECTIVE",
                "validTimeFrom": 1777170000,
                "validTimeTo": 1777177200,
                "rawAirSigmet": "WSUS31 KKCI 260255 SIGMET E CONVECTIVE ...",
                "coords": [
                    {"lat": 39.0, "lon": -77.6},
                    {"lat": 38.8, "lon": -77.2},
                    {"lat": 39.2, "lon": -76.9},
                ],
            }
        ]
        self.gairmet_data = [
            {
                "hazard": "MT_OBSC",
                "product": "SIERRA",
                "validTime": "2026-04-26T18:00:00Z",
                "due_to": "MTNS OBSC BY CLDS",
                "coords": [
                    {"lat": "39.4", "lon": "-77.9"},
                    {"lat": "39.0", "lon": "-77.0"},
                    {"lat": "38.8", "lon": "-77.4"},
                ],
            }
        ]
        self.cwa_data: list[dict] = []
        self.mis_data = [
            {
                "cwsu": "ZDC",
                "validTimeFrom": 1777146300,
                "validTimeTo": 1777194900,
                "rawText": "ZDC MIS TEST MESSAGE",
            }
        ]
        self.tfr_list_data = [
            {
                "notam_id": "9/9999",
                "facility": "ZDC",
                "state": "MD",
                "type": "SECURITY",
                "description": "10NM NW GAI, active now",
            }
        ]
        self.tfr_geom_data = [
            {
                "properties": {
                    "NOTAM_KEY": "9/9999-1-FDC-F",
                    "TITLE": "10NM NW GAITHERSBURG",
                    "STATE": "MD",
                    "LEGAL": "SECURITY",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-8589000.0, 4738000.0],
                            [-8575000.0, 4738000.0],
                            [-8575000.0, 4727000.0],
                            [-8589000.0, 4727000.0],
                            [-8589000.0, 4738000.0],
                        ]
                    ],
                },
            }
        ]

    @staticmethod
    def _filter(items: list[dict], ids: list[str], key: str) -> list[dict]:
        wanted = {item.upper() for item in ids}
        return [row for row in items if str(row.get(key, "")).upper() in wanted]

    def get_metar(self, ids: list[str]) -> list[dict]:
        return self._filter(self.metar_data, ids, "icaoId")

    def get_taf(self, ids: list[str]) -> list[dict]:
        return self._filter(self.taf_data, ids, "icaoId")

    def get_station_info(self, ids: list[str]) -> list[dict]:
        return self._filter(self.station_data, ids, "icaoId")

    def get_airsigmet(self) -> list[dict]:
        return self.airsigmet_data

    def get_gairmet(self) -> list[dict]:
        return self.gairmet_data

    def get_cwa(self) -> list[dict]:
        return self.cwa_data

    def get_mis(self) -> list[dict]:
        return self.mis_data

    def get_tfr_list(self) -> list[dict]:
        return self.tfr_list_data

    def get_tfr_geometries(self) -> list[dict]:
        return self.tfr_geom_data


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()
