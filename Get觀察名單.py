"""從 GoPublic GitHub 下載兩份股票觀察名單 CSV。"""

import urllib.request
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/wenchiehlee/GoPublic/refs/heads/main/"
# GitHub 上的檔名（中文）→ 本地儲存名稱
FILES = [
    ("%E8%A7%80%E5%AF%9F%E5%90%8D%E5%96%AE.csv", "StockID_TWSE_TPEX.csv"),
    ("%E5%B0%88%E6%B3%A8%E5%90%8D%E5%96%AE.csv", "StockID_TWSE_TPEX_focus.csv"),
]

ROOT = Path(__file__).parent


def download():
    for remote_name, local_name in FILES:
        url = BASE_URL + remote_name
        dest = ROOT / local_name
        print(f"Downloading {local_name}...")
        urllib.request.urlretrieve(url, dest)
        print(f"  -> saved to {dest}")


if __name__ == "__main__":
    download()
