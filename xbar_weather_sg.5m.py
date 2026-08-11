#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# <xbar.author>0xMeowth</xbar.author>
# <xbar.version>v1.0.0</xbar.version>
# <xbar.abouturl>https://github.com/0xMeowth/xbar-weather-sg</xbar.abouturl>
# <xbar.dependencies>python3</xbar.dependencies>
# <xbar.var>select(VAR_LOCATION="Select an area"): Forecast area. [Select an area, Ang Mo Kio, Bedok, Bishan, Boon Lay, Bukit Batok, Bukit Merah, Bukit Panjang, Bukit Timah, Central Water Catchment, Changi, Choa Chu Kang, City, Clementi, Geylang, Hougang, Jalan Bahar, Jurong East, Jurong Island, Jurong West, Kallang, Lim Chu Kang, Mandai, Marine Parade, Novena, Pasir Ris, Paya Lebar, Pioneer, Pulau Tekong, Pulau Ubin, Punggol, Queenstown, Seletar, Sembawang, Sengkang, Sentosa, Serangoon, Southern Islands, Sungei Kadut, Tampines, Tanglin, Tengah, Toa Payoh, Tuas, Western Islands, Western Water Catchment, Woodlands, Yishun]</xbar.var>

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree


SUPPORTED_AREAS = (
    "Ang Mo Kio", "Bedok", "Bishan", "Boon Lay", "Bukit Batok", "Bukit Merah",
    "Bukit Panjang", "Bukit Timah", "Central Water Catchment", "Changi",
    "Choa Chu Kang", "City", "Clementi", "Geylang", "Hougang", "Jalan Bahar",
    "Jurong East", "Jurong Island", "Jurong West", "Kallang", "Lim Chu Kang",
    "Mandai", "Marine Parade", "Novena", "Pasir Ris", "Paya Lebar", "Pioneer",
    "Pulau Tekong", "Pulau Ubin", "Punggol", "Queenstown", "Seletar", "Sembawang",
    "Sengkang", "Sentosa", "Serangoon", "Southern Islands", "Sungei Kadut", "Tampines",
    "Tanglin", "Tengah", "Toa Payoh", "Tuas", "Western Islands",
    "Western Water Catchment", "Woodlands", "Yishun",
)

SETUP_SENTINEL = "Select an area"
TWO_HOUR_URL = "https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast"
HEAVY_RAIN_URL = "https://www.weather.gov.sg/files/rss/rssHeavyRain_new.xml"
ALLOWED_URLS = frozenset({TWO_HOUR_URL, HEAVY_RAIN_URL})
CACHE_DIR = Path.home() / "Library" / "Caches" / "xbar-weather-sg"
FORECAST_CACHE_FILE = CACHE_DIR / "forecast.json"
WARNING_STATE_FILE = CACHE_DIR / "warning-state.json"
LOCATION_SIDECAR_FILE = Path(f"{__file__}.vars.json")
FORECAST_TTL = timedelta(minutes=30)
ATOM = "{http://www.w3.org/2005/Atom}"
NOTIFICATION_SCRIPT = """on run argv
display notification (item 1 of argv) with title "Singapore Weather"
end run"""


@dataclass(frozen=True)
class ForecastSnapshot:
    fetched_at: datetime
    updated_at: datetime
    valid_start: datetime
    valid_end: datetime
    forecasts: dict[str, str]


@dataclass(frozen=True)
class WarningSnapshot:
    entry_id: str
    updated: str
    summary: str
    fingerprint: str
    active: bool


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class ApprovedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        if new_url not in ALLOWED_URLS:
            raise ValueError("URL is not an approved official endpoint")
        return super().redirect_request(
            request, fp, code, message, headers, new_url
        )


def fetch_bytes(url: str, timeout: float = 10.0) -> bytes:
    if url not in ALLOWED_URLS:
        raise ValueError("URL is not an approved official endpoint")
    request = urllib.request.Request(url, headers={"User-Agent": "xbar-weather-sg/1.0"})
    opener = urllib.request.build_opener(ApprovedRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def clean_forecast(text: str) -> str:
    return re.sub(r"\s*\((?:Day|Night)\)\s*$", "", text).strip()


def sanitize_text(value: str) -> str:
    parser = TextExtractor()
    parser.feed(html.unescape(value))
    text = " ".join("".join(parser.parts).split())
    return text.replace("|", "¦")


def parse_warning_feed(payload: bytes) -> WarningSnapshot:
    root = ElementTree.fromstring(payload)
    entry = root.find(f"{ATOM}entry")
    if entry is None:
        raise ValueError("warning feed returned no entry")
    entry_id = (entry.findtext(f"{ATOM}id") or "").strip()
    updated = (entry.findtext(f"{ATOM}updated") or "").strip()
    summary = sanitize_text(entry.findtext(f"{ATOM}summary") or "")
    active = bool(summary) and summary.upper() != "NIL"
    normalized = summary if active else ""
    digest = hashlib.sha256("\0".join((entry_id, updated, normalized)).encode()).hexdigest()
    return WarningSnapshot(entry_id, updated, normalized, digest, active)


def parse_forecast_payload(payload: bytes, fetched_at: datetime) -> ForecastSnapshot:
    document = json.loads(payload)
    if document.get("code") != 0:
        raise ValueError("forecast API returned a nonzero status")
    items = document.get("data", {}).get("items") or []
    if not items:
        raise ValueError("forecast API returned no items")
    item = items[0]
    forecasts = {
        row["area"]: clean_forecast(row["forecast"])
        for row in item.get("forecasts", [])
        if isinstance(row.get("area"), str) and isinstance(row.get("forecast"), str)
    }
    if not forecasts:
        raise ValueError("forecast API returned no forecasts")
    period = item["valid_period"]
    return ForecastSnapshot(
        fetched_at=fetched_at,
        updated_at=datetime.fromisoformat(item["update_timestamp"]),
        valid_start=datetime.fromisoformat(period["start"]),
        valid_end=datetime.fromisoformat(period["end"]),
        forecasts=forecasts,
    )


def snapshot_to_dict(value: ForecastSnapshot) -> dict:
    return {
        "fetched_at": value.fetched_at.isoformat(),
        "updated_at": value.updated_at.isoformat(),
        "valid_start": value.valid_start.isoformat(),
        "valid_end": value.valid_end.isoformat(),
        "forecasts": value.forecasts,
    }


def snapshot_from_dict(data: dict) -> ForecastSnapshot:
    forecasts = data["forecasts"]
    if not isinstance(forecasts, dict) or not forecasts:
        raise ValueError("invalid cached forecasts")
    timestamps = {
        name: datetime.fromisoformat(data[name])
        for name in ("fetched_at", "updated_at", "valid_start", "valid_end")
    }
    if any(
        value.tzinfo is None or value.utcoffset() is None
        for value in timestamps.values()
    ):
        raise ValueError("invalid cached timestamp")
    return ForecastSnapshot(
        fetched_at=timestamps["fetched_at"],
        updated_at=timestamps["updated_at"],
        valid_start=timestamps["valid_start"],
        valid_end=timestamps["valid_end"],
        forecasts={str(key): str(value) for key, value in forecasts.items()},
    )


def cache_is_fresh(
    snapshot: ForecastSnapshot, now: datetime, max_age: timedelta = FORECAST_TTL
) -> bool:
    age = now - snapshot.fetched_at
    return timedelta() <= age < max_age


def load_forecast_cache(path: Path = FORECAST_CACHE_FILE) -> ForecastSnapshot | None:
    try:
        with path.open(encoding="utf-8") as cache_file:
            return snapshot_from_dict(json.load(cache_file))
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


def _save_json_atomic(data: dict, path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False,
        ) as cache_file:
            temporary_path = Path(cache_file.name)
            json.dump(data, cache_file)
            cache_file.flush()
            os.fsync(cache_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def save_location(
    location: str, path: Path = LOCATION_SIDECAR_FILE
) -> None:
    if location not in (SETUP_SENTINEL, *SUPPORTED_AREAS):
        raise ValueError("unsupported forecast area")
    _save_json_atomic({"VAR_LOCATION": location}, path)


def load_location(path: Path = LOCATION_SIDECAR_FILE) -> str | None:
    try:
        with path.open(encoding="utf-8") as location_file:
            location = json.load(location_file).get("VAR_LOCATION")
    except (OSError, AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if location in (SETUP_SENTINEL, *SUPPORTED_AREAS):
        return location
    return None


def handle_command(
    arguments: list[str], path: Path = LOCATION_SIDECAR_FILE
) -> bool:
    if not arguments:
        return False
    if len(arguments) != 2 or arguments[0] != "--set-location":
        raise ValueError("unsupported command")
    save_location(arguments[1], path)
    return True


def save_forecast_cache(
    snapshot: ForecastSnapshot, path: Path = FORECAST_CACHE_FILE
) -> None:
    _save_json_atomic(snapshot_to_dict(snapshot), path)


def load_warning_fingerprint(path: Path = WARNING_STATE_FILE) -> str | None:
    try:
        with path.open(encoding="utf-8") as state_file:
            fingerprint = json.load(state_file).get("fingerprint")
    except (OSError, AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return fingerprint if isinstance(fingerprint, str) else None


def save_warning_fingerprint(
    fingerprint: str, path: Path = WARNING_STATE_FILE
) -> None:
    _save_json_atomic({"fingerprint": fingerprint}, path)


def send_notification(message: str, runner=subprocess.run) -> None:
    runner(
        ["/usr/bin/osascript", "-e", NOTIFICATION_SCRIPT, "--", message],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )


def handle_warning_notification(
    warning: WarningSnapshot,
    notifier=send_notification,
    state_path: Path = WARNING_STATE_FILE,
) -> str | None:
    if not warning.active or load_warning_fingerprint(state_path) == warning.fingerprint:
        return None
    error = None
    try:
        notifier(warning.summary)
    except Exception as notification_error:
        error = f"Notification unavailable ({type(notification_error).__name__})"
    finally:
        try:
            save_warning_fingerprint(warning.fingerprint, state_path)
        except OSError as state_error:
            return f"Warning state unavailable ({type(state_error).__name__})"
    return error


def get_forecast_snapshot(
    now: datetime,
    fetcher=fetch_bytes,
    cache_path: Path = FORECAST_CACHE_FILE,
) -> tuple[ForecastSnapshot | None, bool, str | None]:
    cached_snapshot = load_forecast_cache(cache_path)
    if cached_snapshot is not None and cache_is_fresh(cached_snapshot, now):
        return cached_snapshot, False, None
    try:
        refreshed_snapshot = parse_forecast_payload(fetcher(TWO_HOUR_URL), now)
    except Exception as error:
        if cached_snapshot is not None:
            return cached_snapshot, True, type(error).__name__
        return None, False, type(error).__name__
    try:
        save_forecast_cache(refreshed_snapshot, cache_path)
    except OSError as error:
        return (
            refreshed_snapshot,
            False,
            f"Cache write unavailable ({type(error).__name__})",
        )
    return refreshed_snapshot, False, None


def format_sgt(value: datetime) -> str:
    return value.astimezone(timezone(timedelta(hours=8))).strftime("%H:%M")


def render_area_menu(
    location: str, script_path: Path = Path(__file__)
) -> list[str]:
    command = (
        f"shell={shlex.quote(str(script_path))} param1=--set-location "
        "terminal=false refresh=true"
    )
    lines = [f"Forecast area: {sanitize_text(location)}"]
    for area in sorted(SUPPORTED_AREAS):
        marker = "✓ " if area == location else ""
        lines.append(
            f"--{marker}{area} | {command} param2={shlex.quote(area)}"
        )
    return lines


def render_menu(
    location: str,
    forecast: ForecastSnapshot | None,
    warning: WarningSnapshot | None,
    stale: bool,
    errors: list[str],
) -> str:
    safe_location = sanitize_text(location)
    if forecast is None or location not in forecast.forecasts:
        headline = f"{safe_location}: Forecast unavailable"
        forecast_text = "Unavailable"
        valid_text = "Unavailable"
        updated_text = "Unavailable"
    else:
        forecast_text = sanitize_text(forecast.forecasts[location])
        headline = f"{safe_location}: {forecast_text}"
        valid_text = sanitize_text(
            f"{format_sgt(forecast.valid_start)}–{format_sgt(forecast.valid_end)}"
        )
        updated_text = sanitize_text(format_sgt(forecast.updated_at))
    warning_text = "None"
    if warning is not None and warning.active:
        warning_text = sanitize_text(warning.summary)
        headline = f"Rain warning — {headline} | color=red"
    lines = [
        headline,
        "---",
        f"Valid: {valid_text}",
        f"Data updated: {updated_text}",
        f"Heavy-rain warning: {warning_text}",
    ]
    if stale:
        lines.append("Forecast may be stale")
    lines.extend(sanitize_text(error) for error in errors)
    lines.extend((
        *render_area_menu(location),
        "---",
        "Open MSS weather | href=https://www.weather.gov.sg/weather-forecast-2hrnowcast-2/",
        "Open heavy-rain warnings | href=https://www.weather.gov.sg/warning-heavy-rain/",
    ))
    return "\n".join(lines)


def main(
    environ=os.environ,
    now_provider=lambda: datetime.now(timezone.utc),
    fetcher=fetch_bytes,
    notifier=send_notification,
    cache_path: Path = FORECAST_CACHE_FILE,
    state_path: Path = WARNING_STATE_FILE,
    location_path: Path = LOCATION_SIDECAR_FILE,
) -> int:
    location = load_location(location_path) or environ.get(
        "VAR_LOCATION", SETUP_SENTINEL
    )
    if location == SETUP_SENTINEL:
        print("\n".join((
            "Select an area from the menu below to view its forecast.",
            "---",
            *render_area_menu(location),
        )))
        return 0

    forecast, stale, forecast_error = get_forecast_snapshot(
        now_provider(), fetcher, cache_path
    )
    errors = []
    if forecast_error is not None:
        if forecast_error.startswith("Cache write unavailable ("):
            errors.append(forecast_error)
        else:
            errors.append(f"Forecast status unavailable ({forecast_error})")

    warning = None
    try:
        warning = parse_warning_feed(fetcher(HEAVY_RAIN_URL))
    except Exception:
        errors.append("Warning status unavailable; will retry")
    else:
        notification_error = handle_warning_notification(warning, notifier, state_path)
        if notification_error is not None:
            errors.append(notification_error)

    if forecast is None or location not in forecast.forecasts:
        errors.append("Selected area is unavailable")
    print(render_menu(location, forecast, warning, stale, errors))
    return 0


if __name__ == "__main__":
    if not handle_command(sys.argv[1:]):
        raise SystemExit(main())
