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
from urllib.parse import parse_qs, urlparse
import json

import requests

try:  # optional: helps if Cloudflare blocks plain requests
    import cloudscraper
except ImportError:
    cloudscraper = None
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"), override=True)  # .env next to the script
    load_dotenv(override=True)  # and/or in the current directory
except ImportError:
    pass

API = "https://srv.kolhalashon.com/api/"
# Endpoint that returns the one-time download key. Tried in order; first that answers wins.
KEY_URLS = [
    "https://srv.kolhalashon.com/api/files/checkAutorizationDownload/{}/false",
    "https://www2.kolhalashon.com/api/files/checkAutorizationDownload/{}/false",
    "https://www2.kolhalashon.com:444/api/files/checkAutorizationDownload/{}/false",
]
AUDIO = 1  # quality level: 1 = audio only
PAGE_SIZE = 24  # lessons per website page
SITE_KEYS = ["8ea2pe8", "oxugrsl"]  # public site keys seen in the wild; override with --site-key
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://www2.kolhalashon.com",
    "referer": "https://www2.kolhalashon.com/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--url", help="Rav page URL copied from the site (sets rav, page and --order)")
    p.add_argument("--rav", type=int, default=None, help="Rav ID from the site URL [140]")
    p.add_argument("--start-page", type=int, default=None, help="First website page to read [1]")
    p.add_argument("--order", type=int, default=None,
                   help="Sort order number (the site's orderBy=N) [7]")
    p.add_argument("--filters-json", default=os.getenv("KH_FILTERS_JSON"),
                   help="Raw FiltersArray JSON copied from the browser request; see README")
    p.add_argument("--pages", type=int, default=1, help="How many website pages to read")
    p.add_argument("--all", action="store_true", help="Read all pages (ignores --pages)")
    p.add_argument("--limit", type=int, help="Max number of lessons to download")
    p.add_argument("--site-key", default=os.getenv("KH_SITE_KEY"),
                   help="Value of the 'authorization-site-key' header (without 'Bearer '); see README")
    p.add_argument("--key-url", default=os.getenv("KH_KEY_URL"),
                   help="Override the download-key URL (use {} for the file id); see README")
    p.add_argument("--out", default="downloads", help="Output directory")
    p.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between downloads")
    p.add_argument("--retries", type=int, default=3, help="Retries per file")
    p.add_argument("--overwrite", action="store_true", help="Re-download existing files")
    p.add_argument("--list-only", action="store_true", help="Only list lessons (no login needed)")
    p.add_argument("--username", default=os.getenv("KOL_HALASHON_USERNAME"))
    p.add_argument("--password", default=os.getenv("KOL_HALASHON_PASSWORD"))
    a = p.parse_args()
    if a.url:
        u = urlparse(a.url)
        m = re.search(r"/ravs/(\d+)(?:/(\d+))?", u.path)
        q = parse_qs(u.query)
        if m:
            a.rav = a.rav or int(m.group(1))
            a.start_page = a.start_page or (int(m.group(2)) if m.group(2) else None)
        if a.order is None and "orderBy" in q:
            a.order = int(q["orderBy"][0])
        if "urlFilters" in q and not a.filters_json:  # "6:5|25:18823|" -> API filter objects
            pairs = [f.split(":") for f in q["urlFilters"][0].split("|") if ":" in f]
            a.filters_json = json.dumps([
                {"ResultType": int(t), "ResultId": int(i), "ResultParentId": None,
                 "ResultString": None, "ResultOrder": None, "ActiveFilter": True}
                for t, i in pairs])
    a.rav, a.start_page, a.order = a.rav or 140, a.start_page or 1, a.order or 7
    a.filters = json.loads(a.filters_json) if a.filters_json else []
    if a.filters:
        print(f"Filters: {[(f.get('ResultType'), f.get('ResultId', f.get('ResultString'))) for f in a.filters]}")
    return a


def new_session():
    s = cloudscraper.create_scraper() if cloudscraper else requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_page(s, a, page):
    body = {
        "QueryType": -1, "LangID": -1, "MasechetID": -1, "DafNo": -1, "MasechetIDY": -1,
        "DafNoY": -1, "MoedID": -1, "ParashaID": -1, "EnglishDisplay": False,
        "MasechetIDYOz": -1, "DafNoYOz": -1, "FromRow": (page - 1) * PAGE_SIZE,
        "NumOfRows": PAGE_SIZE, "PrefferedLanguage": -1, "SearchOrder": a.order,
        "FiltersArray": a.filters, "GeneralID": a.rav,
        "CustomBool": False, "activefilterType": "all", "FilterSwitch": "1" * 111,
    }
    r = s.post(API + "Search/WebSite_GetRavShiurim/", json=body, timeout=30)
    if not r.ok:
        raise requests.HTTPError(f"HTTP {r.status_code}: {r.text[:200]!r}", response=r)
    return r.json()


def pick_site_key(s, a):
    """Use --site-key if given, otherwise try the known keys until the API accepts one."""
    given = (a.site_key or "").strip().strip("\"'").removeprefix("Bearer ").strip()
    for key in ([given] if given else SITE_KEYS):
        s.headers["authorization-site-key"] = f"Bearer {key}"
        print(f"Trying site key {key} ({'from --site-key/.env' if given else 'built-in'})")
        try:
            fetch_page(s, a, a.start_page)
            return
        except requests.HTTPError as e:
            print(f"Site key {key} rejected: {e}")
    sys.exit("No working site key. See 'If you get 403' in the README.")


def list_lessons(s, a):
    """Yield lessons that have audio, page by page."""
    page, read = a.start_page, 0
    while a.all or read < a.pages:
        rows = fetch_page(s, a, page)
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
    """Log in; a 6-digit user code is also retried with the leading 9 the site's form adds."""
    variants = [user] + (["9" + user] if user.isdigit() and len(user) == 6 else [])
    for name in variants:
        r = s.post(API + "Accounts/UserLogin/", json={"Username": name, "Password": pwd}, timeout=30)
        token = r.json().get("Token") if r.ok else None
        if token:
            s.headers["authorization"] = f"Bearer {token}"
            print(f"Logged in as {name!r}")
            return
        print(f"Login as {name!r} failed: HTTP {r.status_code} {r.text[:200]!r}")
    sys.exit("Login failed. See 'If login fails' in the README.")


def filename(row):
    title = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", row.get("TitleHebrew") or "shiur").strip()[:100]
    date = (row.get("RecordDate") or "")[:10].replace("/", "-")
    return f"{date} {title} [{row['FileId']}].mp3".strip()


def get_key(s, fid, key_urls):
    """Ask each key URL in turn (short connect timeout); keep the one that works first."""
    errors = []
    for url in list(key_urls):
        try:
            r = s.get(url.format(fid), timeout=(10, 30))
            if r.ok and r.json().get("key"):
                key_urls.remove(url)
                key_urls.insert(0, url)
                return r.json()["key"]
            errors.append(f"{url.split('/api/')[0]}: HTTP {r.status_code} {r.text[:100]!r}")
        except (requests.RequestException, ValueError) as e:
            errors.append(f"{url.split('/api/')[0]}: {type(e).__name__}")
    raise ValueError("no download key (" + "; ".join(errors) + ")")


def download(s, row, out, key_urls):
    fid = row["FileId"]
    key = get_key(s, fid, key_urls)
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
        pick_site_key(s, a)
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

    key_urls = [a.key_url] if a.key_url else list(KEY_URLS)
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
                print(f"{tag}: {download(s, row, out, key_urls).name}")
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
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped. Re-run the same command to resume.")