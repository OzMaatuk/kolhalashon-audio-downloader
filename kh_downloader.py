#!/usr/bin/env python3
"""Download the audio-only (.mp3) version of a rav's lessons from kolhalashon.com.

URL https://www.kolhalashon.com/he/regularSite/ravs/140/1/1  ->  rav 140, page 1.
Listing needs no login; downloading does (credentials via .env, flags, or prompt).
"""
import argparse
import getpass
import os
import re
import sys
import time
from pathlib import Path

import requests

try:  # optional: helps if Cloudflare blocks plain requests
    import cloudscraper
except ImportError:
    cloudscraper = None
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API = "https://srv.kolhalashon.com/api/"
KEY_URL = "https://www2.kolhalashon.com:444/api/files/checkAutorizationDownload/{}/false"
AUDIO = 1  # quality level: 1 = audio only
PAGE_SIZE = 24  # lessons per website page
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "authorization-site-key": "Bearer 8ea2pe8",
    "content-type": "application/json",
    "origin": "https://www2.kolhalashon.com",
    "referer": "https://www2.kolhalashon.com/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--rav", type=int, default=140, help="Rav ID from the site URL")
    p.add_argument("--start-page", type=int, default=1, help="First website page to read")
    p.add_argument("--pages", type=int, default=1, help="How many website pages to read")
    p.add_argument("--all", action="store_true", help="Read all pages (ignores --pages)")
    p.add_argument("--limit", type=int, help="Max number of lessons to download")
    p.add_argument("--out", default="downloads", help="Output directory")
    p.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between downloads")
    p.add_argument("--retries", type=int, default=3, help="Retries per file")
    p.add_argument("--overwrite", action="store_true", help="Re-download existing files")
    p.add_argument("--list-only", action="store_true", help="Only list lessons (no login needed)")
    p.add_argument("--username", default=os.getenv("KOL_HALASHON_USERNAME"))
    p.add_argument("--password", default=os.getenv("KOL_HALASHON_PASSWORD"))
    return p.parse_args()


def new_session():
    s = cloudscraper.create_scraper() if cloudscraper else requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_page(s, rav, page):
    body = {
        "QueryType": -1, "LangID": -1, "MasechetID": -1, "DafNo": -1, "MasechetIDY": -1,
        "DafNoY": -1, "MoedID": -1, "ParashaID": -1, "EnglishDisplay": False,
        "MasechetIDYOz": -1, "DafNoYOz": -1, "FromRow": (page - 1) * PAGE_SIZE,
        "NumOfRows": PAGE_SIZE, "PrefferedLanguage": -1, "SearchOrder": 7,
        "FiltersArray": [], "GeneralID": rav, "FilterSwitch": "1" * 111,
    }
    r = s.post(API + "Search/WebSite_GetRavShiurim/", json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def list_lessons(s, a):
    """Yield lessons that have audio, page by page."""
    page, read = a.start_page, 0
    while a.all or read < a.pages:
        rows = fetch_page(s, a.rav, page)
        print(f"Page {page}: {len(rows)} lessons")
        for row in rows:
            if row.get("HasAudio"):
                yield row
            else:
                print(f"  skip (no audio): [{row.get('FileId')}] {row.get('TitleHebrew')}")
        if len(rows) < PAGE_SIZE:
            return
        page, read = page + 1, read + 1


def login(s, user, pwd):
    r = s.post(API + "Accounts/UserLogin/", json={"Username": user, "Password": pwd}, timeout=30)
    token = r.json().get("Token") if r.ok else None
    if not token:
        sys.exit(f"Login failed (HTTP {r.status_code}). Check username/password.")
    s.headers["authorization"] = f"Bearer {token}"


def filename(row):
    title = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", row.get("TitleHebrew") or "shiur").strip()[:100]
    date = (row.get("RecordDate") or "")[:10].replace("/", "-")
    return f"{date} {title} [{row['FileId']}].mp3".strip()


def download(s, row, out, retries):
    fid = row["FileId"]
    key = s.get(KEY_URL.format(fid), timeout=30).json()["key"]
    url = f"{API}files/GetFileDownload/{fid}/{AUDIO}/{key}/null/false/false"
    path = out / filename(row)
    tmp = path.with_suffix(".part")
    with s.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
    tmp.replace(path)
    return path


def main():
    a = parse_args()
    s = new_session()
    try:
        lessons = list(list_lessons(s, a))
    except requests.RequestException as e:
        sys.exit(f"Could not list lessons: {e}")
    if a.limit:
        lessons = lessons[:a.limit]
    print(f"{len(lessons)} lessons with audio.")

    if a.list_only:
        for i, row in enumerate(lessons, 1):
            print(f"{i:4d}. [{row['FileId']}] {row.get('RecordDate', '')[:10]}  {row.get('TitleHebrew')}")
        return
    if not lessons:
        return

    user = a.username or input("Username: ").strip()
    pwd = a.password or getpass.getpass("Password: ")
    login(s, user, pwd)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    existing = {n.rsplit("[", 1)[-1] for n in os.listdir(out)}
    ok = skipped = 0
    failed = []
    for i, row in enumerate(lessons, 1):
        tag = f"[{i}/{len(lessons)}] {row.get('TitleHebrew')}"
        if not a.overwrite and f"{row['FileId']}].mp3" in existing:
            skipped += 1
            print(f"{tag}: exists, skipped")
            continue
        for attempt in range(1, a.retries + 1):
            try:
                print(f"{tag}: {download(s, row, out, a.retries).name}")
                ok += 1
                break
            except (requests.RequestException, KeyError, ValueError) as e:
                if attempt == a.retries:
                    failed.append(row["FileId"])
                    print(f"{tag}: FAILED ({e})")
                else:
                    time.sleep(2 * attempt)
        time.sleep(a.delay)
    print(f"\nDone. downloaded={ok} skipped={skipped} failed={len(failed)} {failed or ''}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
