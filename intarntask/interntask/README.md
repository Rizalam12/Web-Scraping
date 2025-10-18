eCourts Scraper
================

Files: single-file script (this document) containing:
- README (in this header)
- Python CLI scraper implementation

Goal:
Fetch court listings (cause lists) and case listing info from eCourts ("https://services.ecourts.gov.in/ecourtindia_v6/?p=cause_list/search").

Requirements implemented:
1. Input case details (CNR or Case Type, Number, Year).
2. Check if the case is listed today or tomorrow.
3. If listed, show its serial number and court name.
4. Optionally, download the case PDF (if available).
5. Download entire cause list for today on request.

Output:
- Prints results to console.
- Saves results and cause lists as JSON files.

Bonus:
- CLI options: --today, --tomorrow, --causelist, --download-pdf
- Simple structure ready to be extended into a web/API interface.

Notes & caveats:
- The eCourts website is JS-driven and sometimes exposes data via JSON endpoints. Those endpoints and URLs change frequently.
- This script uses requests + BeautifulSoup to attempt to fetch pages and parse HTML. If the site relies heavily on JS, consider using Selenium or Playwright.
- If you encounter 403 or missing data, check network console in your browser to find the exact API endpoints and update the `ENDPOINTS` mapping below.

Usage exinterntask

### 1) Check by CNR for today:
python interntask.py --cnr "ABCD1234567890" --today

### 2) Check by case details for tomorrow and save json
python interntask.py --type "CIVIL" --number 123 --year 2024 --tomorrow --out results.json

### 3) Download today's entire cause list (for a given court/district — see config)
python interntask.py --causelist --today --district "amravati"

### 4) Download case PDF if found
python interntask.py --cnr "ABCD1234567890" --today --download-pdf


INSTALLATION
------------
Requires Python 3.8+ and these packages:

pip install requests beautifulsoup4 tqdm

If site uses javascript heavily, install selenium and a browser driver.


IMPLEMENTATION DETAILS
----------------------
- Configurable BASE_URL and endpoint paths in ENDPOINTS dict.
- Robust error handling and retries.
- Results persisted as JSON in the working directory.
