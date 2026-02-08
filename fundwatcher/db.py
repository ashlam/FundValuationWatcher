import os
import json
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "funds.sqlite")

def _connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS funds (code TEXT PRIMARY KEY, name TEXT, type TEXT, company TEXT, managers TEXT, updated_at INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS asset_allocations (code TEXT, date TEXT, stock REAL, bond REAL, cash REAL, net_asset REAL, PRIMARY KEY(code, date))")
        c.execute("CREATE TABLE IF NOT EXISTS holdings (code TEXT, report_date TEXT, name TEXT, weight REAL, PRIMARY KEY(code, report_date, name))")
        conn.commit()
    finally:
        conn.close()

def upsert_fund_profile(code, name=None, type_=None, company=None, managers=None):
    ts = int(time.time())
    managers_json = json.dumps(managers or [], ensure_ascii=False)
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO funds(code,name,type,company,managers,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,type=excluded.type,company=excluded.company,managers=excluded.managers,updated_at=excluded.updated_at", (code, name, type_, company, managers_json, ts))
        conn.commit()
    finally:
        conn.close()

def upsert_asset_allocations(code, items):
    if not items:
        return
    conn = _connect()
    try:
        c = conn.cursor()
        for it in items:
            c.execute("INSERT INTO asset_allocations(code,date,stock,bond,cash,net_asset) VALUES(?,?,?,?,?,?) ON CONFLICT(code,date) DO UPDATE SET stock=excluded.stock,bond=excluded.bond,cash=excluded.cash,net_asset=excluded.net_asset", (code, it.get("date"), it.get("stock"), it.get("bond"), it.get("cash"), it.get("net_asset")))
        conn.commit()
    finally:
        conn.close()

def upsert_holdings(code, report_date, items):
    if not items:
        return
    conn = _connect()
    try:
        c = conn.cursor()
        for it in items:
            c.execute("INSERT INTO holdings(code,report_date,name,weight) VALUES(?,?,?,?) ON CONFLICT(code,report_date,name) DO UPDATE SET weight=excluded.weight", (code, report_date, it.get("name"), it.get("weight")))
        conn.commit()
    finally:
        conn.close()

def get_fund(code):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT code,name,type,company,managers,updated_at FROM funds WHERE code=?", (code,))
        row = c.fetchone()
        if not row:
            return None
        managers = json.loads(row[4]) if row[4] else []
        obj = {"fundcode": row[0], "name": row[1], "type": row[2], "company": row[3], "managers": managers, "updated_at": row[5]}
        c.execute("SELECT date,stock,bond,cash,net_asset FROM asset_allocations WHERE code=? ORDER BY date DESC LIMIT 8", (code,))
        allocs = []
        for d, s, b, ca, na in c.fetchall():
            allocs.append({"date": d, "stock": s, "bond": b, "cash": ca, "net_asset": na})
        obj["asset_allocations"] = allocs
        c.execute("SELECT report_date,name,weight FROM holdings WHERE code=? ORDER BY report_date DESC", (code,))
        holds = []
        for rd, nm, wt in c.fetchall():
            holds.append({"report_date": rd, "name": nm, "weight": wt})
        obj["holdings"] = holds
        return obj
    finally:
        conn.close()

def get_stats():
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM funds")
        nf = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM asset_allocations")
        na = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM holdings")
        nh = c.fetchone()[0]
        return {"db_path": DB_PATH, "funds": nf, "asset_allocations": na, "holdings": nh}
    finally:
        conn.close()

def find_fund_code_by_name(name):
    if not name:
        return None
    def _norm(s):
        s = (s or "").strip()
        s = s.replace("发起式联接", "联接")
        s = s.replace("发起联接", "联接")
        s = s.replace("发起式", "")
        s = s.replace("发起", "")
        s = s.replace("成份指数", "指数")
        s = s.replace("中证全指证券公司", "证券")
        s = s.replace("（", "(").replace("）", ")")
        s = s.replace(" ", "")
        return s
    qn = _norm(name)
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT code,name FROM funds")
        rows = c.fetchall()
        for code, nm in rows:
            if name == nm:
                return code
        for code, nm in rows:
            if qn == _norm(nm):
                return code
        for code, nm in rows:
            nn = _norm(nm)
            if qn and (qn in nn or nn in qn):
                if nm and name and nm[:2] == name[:2]:
                    return code
        try:
            import difflib
            best = None
            best_ratio = 0.0
            for code, nm in rows:
                ratio = difflib.SequenceMatcher(a=qn, b=_norm(nm)).ratio()
                if ratio > best_ratio and nm[:2] == name[:2]:
                    best_ratio = ratio
                    best = code
            if best_ratio >= 0.82:
                return best
        except Exception:
            pass
        return None
    finally:
        conn.close()
