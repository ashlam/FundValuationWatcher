def fetch_all_funds_basic():
    try:
        import akshare as ak
        try:
            df = ak.fund_name_em()
        except Exception:
            df = None
        if df is not None:
            items = []
            try:
                for _, row in df.iterrows():
                    code = str(row.get("基金代码") or "").strip()
                    name = str(row.get("基金简称") or "").strip()
                    type_ = str(row.get("基金类型") or "").strip()
                    if code:
                        items.append({"code": code, "name": name or None, "type": type_ or None})
            except Exception:
                items = []
            if items:
                return items
    except Exception:
        pass
    try:
        import requests
        import json
        r = requests.get("http://fund.eastmoney.com/js/fundcode_search.js", timeout=10)
        t = r.text or ""
        s = t[t.find("["): t.rfind("]")+1]
        arr = json.loads(s)
        items = []
        for x in arr:
            code = str((x[0] if len(x) > 0 else "") or "").strip()
            name = str((x[2] if len(x) > 2 else "") or "").strip()
            type_ = str((x[4] if len(x) > 4 else "") or "").strip()
            if code:
                items.append({"code": code, "name": name or None, "type": type_ or None})
        return items
    except Exception:
        return []

def fetch_fund_detail_xq(code):
    if not code:
        return {}
    try:
        import akshare as ak
    except Exception:
        return {}
    try:
        df = ak.fund_individual_basic_info_xq(symbol=str(code))
    except Exception:
        return {}
    kv = {}
    try:
        for _, r in df.iterrows():
            item = str(r.get("item") or "").strip()
            val = str(r.get("value") or "").strip()
            if item:
                kv[item] = val
    except Exception:
        kv = {}
    name = kv.get("基金名称")
    company = kv.get("基金公司")
    mgr_text = kv.get("基金经理") or ""
    mgr_text = mgr_text.replace("，", " ").replace(",", " ")
    managers = [x.strip() for x in mgr_text.split() if x.strip()]
    type_ = kv.get("基金类型")
    return {"code": str(code), "name": name or None, "company": company or None, "managers": managers, "type": type_ or None}
