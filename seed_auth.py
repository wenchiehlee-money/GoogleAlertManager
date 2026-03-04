"""
互動式 Google 登入 — 取代已損壞的 google-alerts seed 指令。

執行後會開啟 Chrome 瀏覽器，請手動登入 Google，
登入成功後按 Enter，cookies 會自動儲存供 google-alerts 使用。
"""

import os
import pickle
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".config", "google_alerts")
SESSION_FILE = os.path.join(CONFIG_PATH, "session")
AUTH_COOKIE_NAME = "SIDCC"
TIMEOUT = 300  # 最多等待 300 秒（5 分鐘）


def main():
    os.makedirs(CONFIG_PATH, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # 使用獨立 profile 避免與已開啟的 Chrome 衝突
    user_data = os.path.join(os.environ.get("TEMP", "/tmp"), "selenium_chrome_profile")
    options.add_argument(f"--user-data-dir={user_data}")
    options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    driver_path = os.path.expanduser(
        "~/.wdm/drivers/chromedriver/win64/145.0.7632.76/chromedriver-win64/chromedriver.exe"
    )
    service = Service(driver_path, log_path="chromedriver.log", service_args=["--verbose"])
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://accounts.google.com/signin")
        print("[*] 瀏覽器已開啟，請在 Chrome 中手動登入 Google。")
        print(f"[!] 等待登入完成（最多 {TIMEOUT} 秒）...")

        for i in range(TIMEOUT):
            cookies = driver.get_cookies()
            if any(c["name"] == AUTH_COOKIE_NAME for c in cookies):
                print("[*] 偵測到登入 cookie，繼續...")
                break
            time.sleep(1)
        else:
            print("[!] 等待逾時，請重新執行。")
            return

        # 導向 Google Alerts 確保取得相關 cookies
        driver.get("https://www.google.com/alerts")
        time.sleep(3)
        cookies = driver.get_cookies()

        collected = {str(c["name"]): str(c["value"]) for c in cookies}
        with open(SESSION_FILE, "wb") as f:
            pickle.dump(collected, f, protocol=2)

        print(f"[+] Session 已儲存：{SESSION_FILE}")
        print("[+] google-alerts 已可使用。")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
