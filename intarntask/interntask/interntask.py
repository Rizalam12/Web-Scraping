import argparse
import datetime
import json
import os
import re
import time
from typing import Any, List, Optional

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://services.ecourts.gov.in/ecourtindia_v6/?p=cause_list/search"


ENDPOINTS = {
    "cnr_search": BASE_URL + "/case/cnrdetail?cnr={cnr}",
    "cause_list": BASE_URL + "/causeList/causelist?district={district}&date={date}",
    "case_detail": BASE_URL + "/case/case_detail?case_no={case_no}&case_year={year}&case_type={case_type}",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) eCourtsScraper/1.0"
}

def safe_request(url: str, params: dict = None, method: str = "GET", timeout: int = 15) -> Optional[requests.Response]:
    """Send an HTTP request with basic retry handling."""
    tries = 3
    for i in range(tries):
        try:
            if method.upper() == "GET":
                r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            else:
                r = requests.post(url, data=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            print(f"Request error ({i+1}/{tries}) for {url}: {e}")
            time.sleep(1 + i * 2)
    return None


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_json(obj: Any, filename: str) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print(f"Saved: {filename}")


def parse_causelist_html(html: str) -> List[dict]:
   
    soup = BeautifulSoup(html, "html.parser")
    entries: List[dict] = []

    tables = soup.find_all("table")
    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        header_text = " ".join(headers)
        if any(x in header_text for x in ["sl no", "serial", "sr no"]) and any(x in header_text for x in ["court", "case no", "case no."]):
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                row_text = [td.get_text(separator=" ", strip=True) for td in tds]
                entry = {
                    "raw_cells": row_text,
                }
                try:
                    entry["serial"] = row_text[0]
                    for cell in row_text:
                        if re.search(r"court|civil|criminal|family|tribunal", cell, re.I):
                            entry.setdefault("court_name", cell)
                            break
                except Exception:
                    pass

                pdf = tr.find("a", href=re.compile(r"\.pdf$"))
                if pdf and pdf.get("href"):
                    entry["pdf_url"] = pdf.get("href")
                entries.append(entry)
            break

    if not entries:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf"):
                entries.append({"pdf_url": href, "title": a.get_text(strip=True)})
    return entries


def search_by_cnr(cnr: str) -> Optional[dict]:
    """Attempt to lookup a case by CNR. Returns parsed data or None."""
    url = ENDPOINTS.get("cnr_search").format(cnr=cnr)
    print(f"Searching CNR at: {url}")
    r = safe_request(url)
    if r is None:
        print("Failed to fetch CNR page.")
        return None
    try:
        data = r.json()
        print("Received JSON response for CNR search (parsed).")
        return data
    except ValueError:
        pass
    soup = BeautifulSoup(r.text, "html.parser")
    details = {"cnr": cnr, "raw_html_snippet": soup.get_text()[:1000]}
    return details


def search_by_case(case_type: str, case_no: str, case_year: str) -> Optional[dict]:
    url = ENDPOINTS.get("case_detail").format(case_no=case_no, year=case_year, case_type=case_type)
    print(f"Searching case at: {url}")
    r = safe_request(url)
    if r is None:
        return None
    try:
        return r.json()
    except ValueError:
        return {"raw_html": r.text[:2000]}


def get_cause_list_for_date(d: datetime.date, district: str = "") -> List[dict]:
    if d > datetime.date.today():
        print(f"Cannot fetch cause list for future date: {d}. Returning empty list.")
        return []
    date_str = d.strftime("%Y-%m-%d")
    url = ENDPOINTS.get("cause_list").format(district=district, date=date_str)
    print(f"Fetching cause list: {url}")
    r = safe_request(url)
    if r is None:
        return []
    try:
        js = r.json()
        if isinstance(js, list):
            return js
        elif isinstance(js, dict) and "data" in js:
            return js["data"]
        else:
            return [js]
    except ValueError:
        return parse_causelist_html(r.text)


def download_file(url: str, out_folder: str = "downloads") -> Optional[str]:
    ensure_dir(out_folder)
    local_filename = os.path.join(out_folder, os.path.basename(url.split("?")[0]))
    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            with open(local_filename, "wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=os.path.basename(local_filename)) as bar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        bar.update(len(chunk))
        return local_filename
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None


def check_case_listing(cnr: Optional[str], case_type: Optional[str], case_no: Optional[str], case_year: Optional[str], when: str = "today", district: str = "", download_pdf: bool = False) -> dict:
    if when not in ("today", "tomorrow"):
        raise ValueError("when must be 'today' or 'tomorrow'")
    target_date = datetime.date.today() if when == "today" else datetime.date.today() + datetime.timedelta(days=1)
    result = {"query": {"cnr": cnr, "case_type": case_type, "case_no": case_no, "case_year": case_year, "date": str(target_date)}, "listed": False, "matches": []}

    if cnr:
        info = search_by_cnr(cnr)
        result["lookup_raw"] = info
    cause_list_entries = get_cause_list_for_date(target_date, district=district)
    result["cause_list_count"] = len(cause_list_entries)

    for e in cause_list_entries:
        text = " ".join(e.get("raw_cells", e.get("title", []) if isinstance(e.get("title"), list) else [e.get("title", "")])) if isinstance(e, dict) else str(e)
        found = False
        if cnr and cnr in text:
            found = True
        if not found and case_no and case_year and case_type:
            if str(case_no) in text and str(case_year) in text and case_type.lower() in text.lower():
                found = True
        if found:
            result["listed"] = True
            match = {"entry": e}
            if isinstance(e, dict):
                match["serial"] = e.get("serial")
                match["court_name"] = e.get("court_name")
                if e.get("pdf_url"):
                    match["pdf_url"] = e.get("pdf_url")
                    if download_pdf:
                        dl = download_file(e["pdf_url"])
                        match["pdf_local"] = dl
            result["matches"].append(match)

    return result




def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="eCourts Scraper — Check if a case is listed today/tomorrow and optionally download PDFs or cause lists.")
    group = p.add_mutually_exclusive_group(required=False)
    group.add_argument("--today", action="store_true", help="Check for today")
    group.add_argument("--tomorrow", action="store_true", help="Check for tomorrow")
    p.add_argument("--cnr", type=str, help="CNR number of the case")
    p.add_argument("--type", type=str, help="Case type (e.g., CIVIL)")
    p.add_argument("--number", type=str, help="Case number")
    p.add_argument("--year", type=str, help="Case year")
    p.add_argument("--district", type=str, default="", help="District (used to fetch cause list)")
    p.add_argument("--date", type=str, help="Specific date in 2020-10-01 format for cause list")
    p.add_argument("--causelist", action="store_true", help="Download entire cause list for the chosen date")
    p.add_argument("--download-pdf", action="store_true", help="Download PDFs found for matched cases")
    p.add_argument("--out", type=str, help="Write results to JSON file")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    when = "today"
    if args.tomorrow:
        when = "tomorrow"

    if not args.today and not args.tomorrow:
        # default to today if none specified
        when = "today"

    if args.causelist:
        if args.date:
            try:
                d = datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
            except ValueError:
                print("Invalid date format. Use YYYY-MM-DD.")
                return
        else:
            d = datetime.date.today() if when == "today" else datetime.date.today() + datetime.timedelta(days=1)
        cause_list = get_cause_list_for_date(d, district=args.district)
        outname = args.out or f"cause_list_{d.isoformat()}.json"
        save_json({"date": str(d), "district": args.district, "items": cause_list}, outname)
        print(f"Cause list entries: {len(cause_list)}")
        return

    result = check_case_listing(cnr=args.cnr, case_type=args.type, case_no=args.number, case_year=args.year, when=when, district=args.district, download_pdf=args.download_pdf)

    # Print summary to console
    print("\n=== Result ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.out:
        save_json(result, args.out)


if __name__ == "__main__":
    main()

