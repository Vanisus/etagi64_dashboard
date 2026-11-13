import re
import time
from datetime import date
from typing import Any, Literal, Self

import httpx

from app.config import setup_logger

logger = setup_logger(__name__)
Period = Literal["daily", "weekly", "monthly"]
Device = Literal["all", "desktop", "phone", "tablet"]


class WordStatError(RuntimeError):
    pass


class WordStatConnectionError(WordStatError):
    pass


class WordStatResponseError(WordStatError):
    pass


class WordStatAPIError(WordStatError):
    def __init__(self, status_code: int, message: str, request_id: str | None = None) -> None:
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        text = f"WordStat HTTP {status_code}: {message}"
        if request_id:
            text += f"| requestID={request_id}"
        super().__init__(text)


class WordStatClient:
    BASE_URL = "https://searchapi.api.cloud.yandex.net"
    PERIODS = {"daily": "PERIOD_DAILY", "weekly": "PERIOD_WEEKLY", "monthly": "PERIOD_MONTHLY"}
    DEVICES = {"all": "DEVICE_ALL", "desktop": "DEVICE_DESKTOP", "phone": "DEVICE_PHONE", "tablet": "DEVICE_TABLET"}

    def __init__(self, api_key: str, folder_id: str, timeout_seconds: float = 60.0, *,
                 transport: httpx.BaseTransport | None = None, max_retries: int = 2, min_interval: float = 1.0) -> None:
        if not 0 <= max_retries <= 5 or not 0 <= min_interval <= 60:
            raise ValueError("Некорректные параметры повторов или интервала.")
        self._folder_id = folder_id
        self._max_retries = max_retries
        self._min_interval = min_interval
        self._last_request = 0.0
        self._http = httpx.Client(
            base_url=self.BASE_URL, transport=transport,
            timeout=httpx.Timeout(timeout_seconds, connect=min(15.0, timeout_seconds)), trust_env=False,
            headers={"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def top_requests(self, phrase: str, limit: int = 10, regions: list[str] | None = None, device: Device = "all") -> dict[str, Any]:
        if not 1 <= limit <= 2000:
            raise ValueError("limit must be between 1 and 2000")
        payload = self._base_payload(phrase=phrase, regions=regions, device=device)
        payload["numPhrases"] = str(limit)
        return self._post("v2/wordstat/topRequests", payload=payload)

    def dynamics(self, phrase: str, date_from: date, date_to: date, period: Period = "daily",
                 regions: list[str] | None = None, device: Device = "all") -> dict[str, Any]:
        if date_from > date_to:
            raise ValueError("date_from must not be greater than date_to")
        if period not in self.PERIODS:
            raise ValueError("period must be one of ['daily', 'weekly', 'monthly']")
        payload = self._base_payload(phrase=phrase, regions=regions, device=device)
        payload.update({"period": self.PERIODS[period], "fromDate": self._format_date(date_from), "toDate": self._format_date(date_to)})
        return self._post("v2/wordstat/dynamics", payload=payload)

    def _base_payload(self, phrase: str, regions: list[str] | None, device: Device) -> dict[str, Any]:
        phrase = phrase.strip()
        if not phrase:
            raise ValueError("phrase must not be empty")
        if len(phrase) > 400:
            raise ValueError("phrase must be less than 400")
        if device not in self.DEVICES:
            raise ValueError("device must be one of ['all', 'desktop', 'phone', 'tablet']")
        payload: dict[str, Any] = {"phrase": phrase, "folderId": self._folder_id, "devices": [self.DEVICES[device]]}
        if regions is not None:
            if not regions:
                raise ValueError("regions must not be empty Enter region or None")
            if len(regions) > 100:
                raise ValueError("region must be less than 100")
            normalized = [str(region).strip() for region in regions]
            if any(re.fullmatch(r"[1-9][0-9]{0,18}", region) is None for region in normalized):
                raise ValueError("Region ID must be a positive integer")
            payload["regions"] = normalized
        return payload

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("WordStat request: method=%s, phrase=%r", path, payload.get("phrase"))
        for attempt in range(self._max_retries + 1):
            delay = max(0.0, self._min_interval - (time.monotonic() - self._last_request))
            time.sleep(delay)
            self._last_request = time.monotonic()
            try:
                response = self._http.post(path, json=payload)
            except httpx.RequestError as exc:
                if attempt == self._max_retries:
                    raise WordStatConnectionError(f"Connection error: {exc}") from exc
                time.sleep(min(2**attempt, 30))
                continue
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == self._max_retries:
                break
            retry_after = response.headers.get("Retry-After", "")
            wait = min(float(retry_after), 30) if re.fullmatch(r"[0-9]+", retry_after) else min(2**attempt, 30)
            time.sleep(wait)
        logger.info("WordStat response: status=%s", response.status_code)
        try:
            data = response.json()
        except ValueError as exc:
            if not response.is_success:
                raise WordStatAPIError(status_code=response.status_code, message="Server return an error not in JSON format") from exc
            raise WordStatResponseError("WordStat return response not in JSON format") from exc
        if not response.is_success:
            message, request_id = "WordStat return an error.", None
            if isinstance(data, dict):
                message = str(data.get("message") or message)
                details = data.get("details")
                if isinstance(details, list):
                    for detail in details:
                        if isinstance(detail, dict) and detail.get("requestId"):
                            request_id = str(detail["requestId"])
                            break
            raise WordStatAPIError(status_code=response.status_code, message=message, request_id=request_id)
        if not isinstance(data, dict):
            raise WordStatResponseError("JSON object was expected in the WordStat response.")
        return data

    @staticmethod
    def _format_date(value: date) -> str:
        return f"{value.isoformat()}T00:00:00Z"
