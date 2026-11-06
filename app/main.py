import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv


URL = "https://searchapi.api.cloud.yandex.net/v2/wordstat/topRequests"


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Прототип Wordstat через Yandex Cloud."
    )
    parser.add_argument(
        "--phrase",
        default="купить квартиру",
        help="Поисковая фраза.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Количество фраз в ответе: от 1 до 2000.",
    )
    parser.add_argument(
        "--regions",
        nargs="+",
        help="ID регионов. Если не указаны — все регионы.",
    )
    args = parser.parse_args()

    if not args.phrase.strip():
        parser.error("--phrase не может быть пустой.")

    if not 1 <= args.limit <= 2000:
        parser.error("--limit должен быть от 1 до 2000.")

    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)

    api_key = os.getenv("YANDEX_API_KEY", "").strip()
    folder_id = os.getenv("YANDEX_FOLDER_ID", "").strip()

    print("Файл настроек:", env_path)
    print("Файл существует:", env_path.is_file())
    print("Folder ID:", folder_id)
    print("Ключ задан:", bool(api_key))
    print("Длина ключа:", len(api_key))
    print("Последние 4 символа:", api_key[-4:] if api_key else "—")

    if not api_key or not folder_id:
        print(
            "Укажи YANDEX_API_KEY и YANDEX_FOLDER_ID в .env.",
            file=sys.stderr,
        )
        return 1

    payload = {
        "phrase": args.phrase.strip(),
        "numPhrases": args.limit,
        "devices": ["DEVICE_ALL"],
        "folderId": folder_id,
    }

    if args.regions:
        payload["regions"] = args.regions

    print(f"POST {URL}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    try:
        with httpx.Client(
            timeout=httpx.Timeout(60.0, connect=15.0),
            trust_env=False,
        ) as client:
            response = client.post(
                URL,
                headers={
                    "Authorization": f"Api-Key {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.RequestError as exc:
        print(f"\nОшибка соединения: {exc}", file=sys.stderr)
        return 1

    print(f"\nHTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError:
        print(response.text[:4000], file=sys.stderr)
        return 1

    print(json.dumps(data, ensure_ascii=False, indent=2))

    if not response.is_success:
        return 1

    now = datetime.now(timezone.utc)
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / (
        f"wordstat_top_{now.strftime('%Y%m%dT%H%M%S_%fZ')}.json"
    )

    output_file.write_text(
        json.dumps(
            {
                "collected_at": now.isoformat(),
                "request": payload,
                "response": data,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nСохранено: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())