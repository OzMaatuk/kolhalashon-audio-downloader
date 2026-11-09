# Kol Halashon Audio Downloader

Downloads the **audio-only (.mp3)** version of a rav's lessons from [kolhalashon.com](https://www.kolhalashon.com).
Lessons without audio are skipped. Re-running is safe: existing files are skipped.

The site URL `.../ravs/140/1/1` means **rav 140, page 1**.

## Setup

**Dev container:** open the folder in VS Code → *Reopen in Container*, then edit `.env`.

**Local:**
```bash
pip install -r requirements.txt
cp .env.example .env   # add your Kol Halashon username & password
```
Downloading requires a site login. Listing does not. If `.env` is empty you are prompted.

## Usage

```bash
python kh_downloader.py --rav 140 --list-only        # preview page 1, no login
python kh_downloader.py --rav 140                    # download page 1 (24 lessons)
python kh_downloader.py --rav 140 --pages 5          # pages 1-5
python kh_downloader.py --rav 140 --start-page 3 --pages 2
python kh_downloader.py --rav 140 --all              # every page
python kh_downloader.py --rav 140 --all --limit 50   # all pages, stop at 50 lessons
```

| Option | Default | Meaning |
|---|---|---|
| `--rav` | 140 | Rav ID |
| `--start-page` / `--pages` | 1 / 1 | Page range |
| `--all` | off | Read every page |
| `--limit` | none | Max lessons to download |
| `--out` | `downloads` | Output folder |
| `--delay` | 1.0 | Seconds between downloads |
| `--retries` | 3 | Retries per file |
| `--overwrite` | off | Re-download existing files |
| `--site-key` | auto | `authorization-site-key` header value (or env `KH_SITE_KEY`) |
| `--list-only` | off | List only |

Files are named `DATE TITLE [fileId].mp3`.

## Filters and sorting

Paste a URL from the site. Rav, page, sort order and filters are all taken from it:

```bash
python kh_downloader.py --url "https://www.kolhalashon.com/en/regularSite/ravs/140?urlFilters=6:5%7C25:18823%7C&orderBy=9" --pages 5
```

- `orderBy=N` is sent as the API's `SearchOrder` (override with `--order N`).
- `urlFilters=6:5|25:18823|` is read as `type:id` pairs and sent as `FiltersArray` objects (`ResultType`, `ResultId`).
- Text filters (e.g. a search word such as `{"ResultType":1,"ResultString":"פרשת","ActiveFilter":true}`) are not in the URL. Pass them with `--filters-json '[...]'` (or `KH_FILTERS_JSON` in `.env`), copied from the `FiltersArray` in DevTools → Network → `WebSite_GetRavShiurim` → Payload. This replaces the filters taken from the URL.

Run with `--list-only` first and compare with the website's list to confirm the filters took effect.

## If you get 403

The API requires a public `authorization-site-key` header that the site may change. The script tries two known values; if both fail:

1. Open the rav page in your browser, press F12 → **Network** → reload.
2. Click the `WebSite_GetRavShiurim` request → **Headers** → copy the value of `authorization-site-key` (after `Bearer `).
3. Run with `--site-key THAT_VALUE` (or put `KH_SITE_KEY=...` in `.env`).

The error message prints the server's response: a page saying "Just a moment" means Cloudflare is blocking the request, not the key.

## If login fails

The error prints the server's reply. A 6-digit user code is also retried with a leading `9` automatically. If both fail, log in on the website with DevTools → Network open, click the login request → **Payload**, and compare the field names/username format with what the script sends (`Username`, `Password`).

## If downloads hang or fail

Each file needs a short-lived download key from a separate endpoint. The script tries three known URLs (10 s connect timeout each) and prints which ones failed. To find the current one: with DevTools → Network open, click **download → audio** on a lesson, find the request containing `checkAutorizationDownload`, and pass its URL with the lesson id replaced by `{}`:

```bash
python kh_downloader.py --key-url "https://HOST/api/files/checkAutorizationDownload/{}/false"
```
(or `KH_KEY_URL=...` in `.env`).

## Notes

Uses the site's own JSON API (the same calls the website makes). If you get blocked, retry later or raise `--delay`.
Please respect the site's terms of use.