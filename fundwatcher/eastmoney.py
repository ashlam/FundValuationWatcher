import json
import time
import re
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from typing import List, Dict, Optional
import datetime
import random

def fetch_fund_estimation(code, timeout=5):
    url = f"http://fundgz.1234567.com.cn/js/{code}.js"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return None
    if not text or "jsonpgz" not in text:
        return None
    s = text.strip()
    if not s.startswith("jsonpgz(") or not s.endswith(");"):
        return None
    payload = s[len("jsonpgz("):-2]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    data["source"] = "eastmoney_fundgz"
    data["ts"] = int(time.time())
    return data

def fetch_fund_profile(code, timeout=6):
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return None
    if not text or "var fS_code" not in text:
        return None
    def pick(pattern):
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None
    name = pick(r"var\s+fS_name\s*=\s*'([^']*)'")
    ftype = pick(r"var\s+fS_type\s*=\s*'([^']*)'")
    company = pick(r"var\s+fundCompany\s*=\s*'([^']*)'")
    manager_json = pick(r"var\s+Data_fundManager\s*=\s*([^;]+);") or pick(r"var\s+Data_currentFundManager\s*=\s*([^;]+);")
    managers = []
    if manager_json:
        try:
            arr = json.loads(manager_json)
            for it in arr:
                nm = it.get("name") or it.get("managerName")
                if nm:
                    managers.append(nm)
        except Exception:
            pass
    return {
        "fundcode": code,
        "name": name,
        "type": ftype,
        "company": company,
        "managers": managers
    }

def fetch_asset_allocation(code, timeout=6):
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return None
    m = re.search(r"var\s+Data_assetAllocation\s*=\s*([^;]+);", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except Exception:
        return None
    cats = data.get("categories") or []
    ser = data.get("series") or []
    stock = None
    bond = None
    cash = None
    net = None
    for s in ser:
        nm = s.get("name")
        vals = s.get("data") or []
        if nm and "股票" in nm:
            stock = vals
        elif nm and "债券" in nm:
            bond = vals
        elif nm and "现金" in nm:
            cash = vals
        elif nm and ("净资产" in nm or s.get("type") == "line"):
            net = vals
    items = []
    for i, d in enumerate(cats):
        items.append({
            "date": d,
            "stock": stock[i] if stock and i < len(stock) else None,
            "bond": bond[i] if bond and i < len(bond) else None,
            "cash": cash[i] if cash and i < len(cash) else None,
            "net_asset": net[i] if net and i < len(net) else None
        })
    return items or None

def fetch_top_holdings(code, timeout=6):
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return None
    m = re.search(r"var\s+Data_fundSharesPositions\s*=\s*([^;]+);", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except Exception:
        return None
    if isinstance(data, dict):
        cats = data.get("categories") or []
        ser = data.get("series") or []
        names = []
        weights = []
        for s in ser:
            nm = s.get("name")
            vals = s.get("data") or []
            if nm and "股票" in nm:
                weights = vals
            elif nm and "股票名称" in nm:
                names = vals
        items = []
        report_date = cats[-1] if cats else None
        for i in range(min(len(names), len(weights))):
            items.append({"name": names[i], "weight": weights[i]})
        return {"report_date": report_date, "items": items} if items else None
    return None

def fetch_latest_nav_change(code, timeout=6):
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return None
    m = re.search(r"var\s+Data_netWorthTrend\s*=\s*([^;]+);", text)
    if not m:
        return None
    try:
        arr = json.loads(m.group(1))
    except Exception:
        return None
    if not isinstance(arr, list) or not arr:
        return None
    it = arr[-1]
    try:
        nav = float(it.get("y") or 0)
    except Exception:
        nav = None
    try:
        pct = float(it.get("equityReturn") or 0)
    except Exception:
        pct = None
    dt = None
    x = it.get("x")
    try:
        if isinstance(x, (int, float)):
            import datetime as _dt
            dt = _dt.datetime.fromtimestamp(x/1000.0).date().isoformat()
    except Exception:
        dt = None
    return {"date": dt, "nav": nav, "pct": pct} if (pct is not None) else None

def fetch_nav_change_series(code, timeout=8):
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return None
    m = re.search(r"var\s+Data_netWorthTrend\s*=\s*([^;]+);", text)
    if not m:
        return None
    try:
        arr = json.loads(m.group(1))
    except Exception:
        return None
    out = []
    for it in arr or []:
        try:
            x = it.get("x")
            if isinstance(x, (int, float)):
                import datetime as _dt
                dt = _dt.datetime.fromtimestamp(x/1000.0).date().isoformat()
            else:
                dt = None
            pct = float(it.get("equityReturn")) if it.get("equityReturn") is not None else None
            nav = float(it.get("y")) if it.get("y") is not None else None
            if dt is not None and pct is not None:
                out.append({"date": dt, "pct": pct, "nav": nav})
        except Exception:
            continue
    return out or None

def fetch_fundcode_search(timeout=8) -> Optional[List[Dict[str, str]]]:
    url = "http://fund.eastmoney.com/js/fundcode_search.js"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return None
    if not text or "var r =" not in text:
        return None
    m = re.search(r"var\s+r\s*=\s*(\[[\s\S]*?\]);", text)
    if not m:
        return None
    payload = m.group(1)
    try:
        arr = json.loads(payload)
    except Exception:
        return None
    items: List[Dict[str, str]] = []
    for it in arr:
        try:
            code = str(it[0]).strip()
            name = str(it[2]).strip()
            ftype = str(it[3]).strip()
            if code:
                items.append({"code": code, "name": name, "type": ftype})
        except Exception:
            continue
    return items or None

def fetch_fund_ranking(sc="1n", st="desc", ft="all", *, page=1, page_size=50, sd=None, ed=None, timeout=10):
    now = datetime.datetime.now()
    if ed is None:
        ed = now.date().isoformat()
    if sd is None:
        sd = (now.date() - datetime.timedelta(days=30)).isoformat()
    page = int(page or 1)
    page_size = int(page_size or 50)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50
    v = str(random.random())
    url = (
        "https://fund.eastmoney.com/data/rankhandler.aspx"
        f"?op=ph&dt=kf&ft={ft}&rs=&gs=0&sc={sc}&st={st}"
        f"&sd={sd}&ed={ed}&qdii=&tabSubtype=,,,,,&pi={page}&pn={page_size}&dx=1&v={v}"
    )
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://fund.eastmoney.com/data/fundranking.html"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return {"items": [], "all_records": 0}
    if not text or "rankData" not in text:
        return {"items": [], "all_records": 0}
    if "无访问权限" in text:
        return {"items": [], "all_records": 0}
    m = re.search(r"datas\s*:\s*\[([\s\S]*?)\]\s*,\s*(?:allRecords|allRecords\s*:)", text)
    if not m:
        m = re.search(r"datas\s*:\s*\[([\s\S]*?)\]", text)
    if not m:
        return {"items": [], "all_records": 0}
    body = m.group(1) if m else ""
    arr = re.findall(r"\"([^\"]*)\"|'([^']*)'", body)
    rows = []
    for a, b in arr:
        s = a or b
        if s:
            rows.append(s)
    am = re.search(r"allRecords\s*:\s*(\d+)", text)
    all_records = 0
    if am:
        try:
            all_records = int(am.group(1))
        except Exception:
            all_records = 0
    items = []
    for s in rows:
        parts = s.split(",")
        if len(parts) < 7:
            continue
        code = (parts[0] or "").strip()
        name = (parts[1] or "").strip()
        d = (parts[3] or "").strip() if len(parts) > 3 else ""
        pct = None
        try:
            pct = float((parts[6] or "").strip())
        except Exception:
            pct = None
        if not code:
            continue
        items.append({
            "fundcode": code,
            "name": name or None,
            "daily_pct": pct,
            "daily_pct_date": d or None,
            "pct_source": "official",
            "nav_fetched_at": time.strftime("%H:%M"),
        })
    return {"items": items, "all_records": all_records}

def fetch_fund_guzhi_list(type_=0, sort="3", order_type="desc", *, canbuy="0", page=1, page_size=50, timeout=10):
    page = int(page or 1)
    page_size = int(page_size or 50)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50
    url = (
        "https://api.fund.eastmoney.com/FundGuZhi/GetFundGZList"
        f"?type={int(type_)}&sort={sort}&orderType={order_type}&canbuy={canbuy}"
        f"&pageIndex={page}&pageSize={page_size}"
    )
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://fund.eastmoney.com/fundguzhi.html"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return {"items": [], "total_count": 0}
    try:
        obj = json.loads(text)
    except Exception:
        return {"items": [], "total_count": 0}
    if not isinstance(obj, dict):
        return {"items": [], "total_count": 0}
    data = obj.get("Data") or {}
    if not isinstance(data, dict):
        return {"items": [], "total_count": 0}
    rows = data.get("list") or []
    if not isinstance(rows, list):
        rows = []
    items = []
    now_hm = time.strftime("%H:%M")
    for it in rows:
        try:
            code = str(it.get("bzdm") or "").strip()
            name = str(it.get("jjjc") or "").strip()
            pct_raw = it.get("gszzl")
            pct = None
            try:
                if isinstance(pct_raw, (int, float)):
                    pct = float(pct_raw)
                else:
                    s = str(pct_raw or "").replace("%", "").strip()
                    pct = float(s) if s else None
            except Exception:
                pct = None
            items.append({
                "fundcode": code,
                "name": name or None,
                "daily_pct": pct,
                "daily_pct_date": (data.get("gxrq") or None),
                "pct_source": "estimate",
                "nav_fetched_at": now_hm,
            })
        except Exception:
            continue
    total_count = 0
    try:
        total_count = int((obj or {}).get("TotalCount") or 0)
    except Exception:
        total_count = 0
    return {"items": items, "total_count": total_count}
