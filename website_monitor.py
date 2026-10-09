import time
from typing import List, Dict, Any
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_website(site: Dict[str, Any], timeout: int = 8) -> Dict[str, Any]:
    url = site.get("url", "").strip()
    name = site.get("name", url)
    expected_status = site.get("expected_status", 200)

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    result = {
        "name": name,
        "url": url,
        "online": False,
        "status_code": 0,
        "latency_ms": 0,
        "error": None
    }

    start = time.perf_counter()
    try:
        headers = {"User-Agent": "VPS-Sentinel-Monitor/1.0"}
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=False)
        latency = round((time.perf_counter() - start) * 1000)
        result["latency_ms"] = latency
        result["status_code"] = resp.status_code

        # Healthy if < 400 or matches expected_status
        if resp.status_code < 400 or resp.status_code == expected_status:
            result["online"] = True
        else:
            result["error"] = f"HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        result["error"] = "Connection Timed Out"
    except requests.exceptions.SSLError as e:
        result["error"] = f"SSL Error: {str(e)[:40]}"
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection Refused / Unreachable"
    except Exception as e:
        result["error"] = f"Error: {str(e)[:40]}"

    return result

def check_all_websites(sites: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for site in sites:
        if site.get("url"):
            results.append(check_website(site))
    return results
