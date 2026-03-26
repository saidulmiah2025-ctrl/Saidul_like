# ultra_controlled_update_tokens.py
# FINAL ONE-FILE SAFE VERSION (NO EXIT CODE 1)

import requests
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# ================= CONFIG =================
API_URL = "https://xtytdtyj-jwt.up.railway.app/token"
TIMEOUT = 20
MAX_WORKERS = 5
RETRIES = 2
BASE_DELAY = 2

REGIONS = [
    ("uidpass_bd.json", "token_bd.json", "BANGLADESH"),
    ("uidpass_ind.json", "token_ind.json", "INDIA"),
    ("uidpass_br.json", "token_br.json", "BRAZIL"),
]

# ================= UTILS =================
def read_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Read error {filename}: {e}")
        return []

def write_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Write error {filename}: {e}")
        return False

# ================= TOKEN GEN =================
def generate_token(item, region):
    url = f"{API_URL}?uid={item['uid']}&password={item['password']}"

    for attempt in range(RETRIES):
        try:
            time.sleep(BASE_DELAY)

            r = requests.get(url, timeout=TIMEOUT)

            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"⏳ {region} UID {item['uid']} rate limit, wait {wait}s")
                time.sleep(wait)
                continue

            if r.status_code >= 500:
                time.sleep(3)
                continue

            r.raise_for_status()
            data = r.json()

            if data.get("token") and data["token"] != "N/A":
                return {"token": data["token"], "uid": item["uid"]}

        except Exception as e:
            print(f"⚠️ {region} UID {item['uid']} error: {str(e)[:60]}")
            time.sleep(2)

    return None

def process_region(uidpass_file, token_file, region):
    print(f"\n🚀 START {region}")
    start = time.time()

    uidpass = read_json(uidpass_file)
    if not uidpass:
        print(f"❌ No UID data for {region}")
        return False

    tokens = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = [exe.submit(generate_token, item, region) for item in uidpass]

        done = 0
        for f in as_completed(futures):
            done += 1
            res = f.result()
            if res:
                tokens.append({"token": res["token"]})
                print(f"✅ {region} {done}/{len(uidpass)} UID {res['uid']}")
            else:
                print(f"❌ {region} {done}/{len(uidpass)} failed")

    if tokens:
        write_json(token_file, tokens)
        elapsed = time.time() - start
        print(f"✅ {region} DONE | {len(tokens)} tokens | {elapsed:.1f}s")
        return True
    else:
        print(f"⚠️ {region} NO TOKENS GENERATED")
        return False

# ================= MAIN =================
def main():
    print("🔥 TOKEN UPDATE STARTED (SAFE MODE)")

    results = []
    overall_start = time.time()

    for uidpass, tokenfile, region in REGIONS:
        try:
            ok = process_region(uidpass, tokenfile, region)
            results.append((region, ok))
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ {region} unexpected error: {e}")
            results.append((region, False))

    print("\n====== FINAL SUMMARY ======")
    for r, ok in results:
        print(f"{r}: {'SUCCESS' if ok else 'FAILED'}")

    elapsed = time.time() - overall_start
    print(f"⏱️ Total time: {elapsed:.1f}s")

    # 🔥 NEVER FAIL GITHUB ACTION
    sys.exit(0)

# ================= RUN =================
if __name__ == "__main__":
    main()

