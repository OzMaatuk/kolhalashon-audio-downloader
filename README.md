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
| `--list-only` | off | List only |

Files are named `DATE TITLE [fileId].mp3`.

## Notes

Uses the site's own JSON API (the same calls the website makes). If you get blocked, retry later or raise `--delay`.
Please respect the site's terms of use.
