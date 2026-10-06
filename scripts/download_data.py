"""Download the public benchmark dataset, never the original Kaggle outcomes."""

import concurrent.futures
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"
FILES = {
    "README.md": "1-a1N26_O_wmvf2gtAuTP00jf124vbqhC",
    "case_pack.csv": "11GAxXOPWCxrB1EfePMHB9IquGJ9rDIod",
    "closed_cases_history.csv": "1S05ULujpOwSlv_YSrcDbVJcyS3JpTOZT",
    "identity.csv": "1zsMMY7lnnjZWsubsO25D9n2ZiZHSU8J_",
    "transactions.csv": "1svn7YqgPlJ-Iv3A8ar1Lh91eVWp6sukR",
}


def download(item):
    name, identifier = item
    target = ROOT / name
    if target.exists() and target.stat().st_size > 100:
        return f"{name}: already present"
    url = f"https://drive.google.com/uc?export=download&id={identifier}"
    response = urllib.request.urlopen(url, timeout=90)
    if "text/html" in response.headers.get("Content-Type", ""):
        page = response.read().decode()
        action = re.search(r'<form[^>]+action="([^"]+)"', page)
        inputs = dict(
            re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', page)
        )
        if not action:
            raise RuntimeError(f"{name}: download denied or unavailable")
        import html

        url = html.unescape(action.group(1)) + "?" + urllib.parse.urlencode(inputs)
        response = urllib.request.urlopen(url, timeout=90)
        if "text/html" in response.headers.get("Content-Type", ""):
            raise RuntimeError(f"{name}: expected data, received HTML")
    with open(target.with_suffix(target.suffix + ".part"), "wb") as f:
        while chunk := response.read(1024 * 1024):
            f.write(chunk)
    target.with_suffix(target.suffix + ".part").replace(target)
    return f"{name}: {target.stat().st_size:,} bytes"


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(download, FILES.items()):
            print(result, flush=True)
