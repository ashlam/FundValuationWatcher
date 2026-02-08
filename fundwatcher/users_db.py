import os
import sqlite3
import time
import secrets
import hashlib

USERS_DB_PATH = os.path.join(os.path.dirname(__file__), "users.sqlite")


def _connect():
    return sqlite3.connect(USERS_DB_PATH)


def init_users_db():
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "username TEXT UNIQUE,"
            "password_hash TEXT,"
            "is_super INTEGER,"
            "created_at INTEGER"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "token TEXT PRIMARY KEY,"
            "user_id INTEGER,"
            "created_at INTEGER,"
            "last_seen INTEGER"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS user_positions_json ("
            "user_id INTEGER,"
            "code TEXT,"
            "fund_name TEXT,"
            "amount REAL,"
            "earnings_yesterday REAL,"
            "total_earnings REAL,"
            "return_rate REAL,"
            "notes TEXT,"
            "updated_at INTEGER,"
            "PRIMARY KEY(user_id, code)"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS user_positions_daily ("
            "user_id INTEGER,"
            "date TEXT,"
            "time_slot TEXT,"
            "code TEXT,"
            "fund_name TEXT,"
            "amount REAL,"
            "return_rate REAL,"
            "profit REAL,"
            "ts INTEGER,"
            "PRIMARY KEY(user_id, date, time_slot, code)"
            ")"
        )
        conn.commit()
    finally:
        conn.close()

    ensure_default_admin()


def _hash_password(password, *, salt=None, iterations=120000):
    if salt is None:
        salt = secrets.token_bytes(16)
    if isinstance(salt, str):
        salt = bytes.fromhex(salt)
    dk = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, int(iterations))
    return f"pbkdf2_sha256${int(iterations)}${salt.hex()}${dk.hex()}"


def _verify_password(password, stored):
    try:
        parts = str(stored or "").split("$")
        if len(parts) != 4:
            return False
        algo, it_raw, salt_hex, dk_hex = parts
        if algo != "pbkdf2_sha256":
            return False
        computed = _hash_password(password, salt=salt_hex, iterations=int(it_raw))
        return secrets.compare_digest(computed, stored)
    except Exception:
        return False


def ensure_default_admin():
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", ("admin",))
        row = c.fetchone()
        if row:
            return
        ts = int(time.time())
        ph = _hash_password("admin")
        c.execute(
            "INSERT INTO users(username,password_hash,is_super,created_at) VALUES(?,?,?,?)",
            ("admin", ph, 1, ts),
        )
        conn.commit()
    finally:
        conn.close()


def list_users(*, include_admin=True):
    conn = _connect()
    try:
        c = conn.cursor()
        if include_admin:
            c.execute("SELECT id,username,is_super,created_at FROM users ORDER BY id ASC")
        else:
            c.execute("SELECT id,username,is_super,created_at FROM users WHERE username<>? ORDER BY id ASC", ("admin",))
        items = []
        for uid, un, sup, ct in c.fetchall():
            items.append({"id": uid, "username": un, "is_super": int(sup or 0) == 1, "created_at": ct})
        return items
    finally:
        conn.close()


def get_user_by_username(username):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT id,username,password_hash,is_super,created_at FROM users WHERE username=?", (str(username or ""),))
        row = c.fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "password_hash": row[2], "is_super": int(row[3] or 0) == 1, "created_at": row[4]}
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT id,username,is_super,created_at FROM users WHERE id=?", (int(user_id),))
        row = c.fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "is_super": int(row[2] or 0) == 1, "created_at": row[3]}
    finally:
        conn.close()


def create_user(username, password, *, is_super=False):
    un = str(username or "").strip()
    if not un:
        raise ValueError("missing_username")
    if un.lower() == "admin":
        raise ValueError("reserved_username")
    ts = int(time.time())
    ph = _hash_password(password)
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO users(username,password_hash,is_super,created_at) VALUES(?,?,?,?)",
            (un, ph, 1 if is_super else 0, ts),
        )
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()


def delete_user(username):
    un = str(username or "").strip()
    if not un:
        return 0
    if un.lower() == "admin":
        return 0
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (un,))
        row = c.fetchone()
        if not row:
            return 0
        uid = int(row[0])
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        c.execute("DELETE FROM user_positions_json WHERE user_id=?", (uid,))
        c.execute("DELETE FROM user_positions_daily WHERE user_id=?", (uid,))
        c.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()
        return 1
    finally:
        conn.close()


def authenticate(username, password):
    u = get_user_by_username(username)
    if not u:
        return None
    if not _verify_password(password, u.get("password_hash")):
        return None
    return {"id": u.get("id"), "username": u.get("username"), "is_super": u.get("is_super")}


def create_session(user_id):
    tok = secrets.token_urlsafe(32)
    ts = int(time.time())
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO sessions(token,user_id,created_at,last_seen) VALUES(?,?,?,?)", (tok, int(user_id), ts, ts))
        conn.commit()
    finally:
        conn.close()
    return tok


def delete_session(token):
    tok = str(token or "").strip()
    if not tok:
        return 0
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE token=?", (tok,))
        conn.commit()
        return c.rowcount or 0
    finally:
        conn.close()


def get_user_by_session(token):
    tok = str(token or "").strip()
    if not tok:
        return None
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT user_id FROM sessions WHERE token=?", (tok,))
        row = c.fetchone()
        if not row:
            return None
        uid = int(row[0])
        c.execute("UPDATE sessions SET last_seen=? WHERE token=?", (int(time.time()), tok))
        conn.commit()
        u = get_user_by_id(uid)
        if not u:
            return None
        return {"id": u.get("id"), "username": u.get("username"), "is_super": u.get("is_super")}
    finally:
        conn.close()


def get_user_positions_json(user_id):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT code,fund_name,amount,earnings_yesterday,total_earnings,return_rate,notes,updated_at "
            "FROM user_positions_json WHERE user_id=? ORDER BY updated_at DESC",
            (int(user_id),),
        )
        items = []
        for cd, nm, amt, ey, te, rr, nt, ts in c.fetchall():
            items.append({"code": cd, "fund_name": nm, "amount": amt, "earnings_yesterday": ey, "total_earnings": te, "return_rate": rr, "notes": nt, "updated_at": ts})
        return items
    finally:
        conn.close()


def upsert_user_positions_json(user_id, items):
    if not items:
        return
    ts = int(time.time())
    conn = _connect()
    try:
        c = conn.cursor()
        for it in items:
            c.execute(
                "INSERT INTO user_positions_json(user_id,code,fund_name,amount,earnings_yesterday,total_earnings,return_rate,notes,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(user_id,code) DO UPDATE SET "
                "fund_name=excluded.fund_name,amount=excluded.amount,earnings_yesterday=excluded.earnings_yesterday,total_earnings=excluded.total_earnings,return_rate=excluded.return_rate,notes=excluded.notes,updated_at=excluded.updated_at",
                (int(user_id), it.get("code"), it.get("fund_name"), it.get("amount"), it.get("earnings_yesterday"), it.get("total_earnings"), it.get("return_rate"), it.get("notes"), ts),
            )
        conn.commit()
    finally:
        conn.close()


def delete_user_position_json(user_id, code):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM user_positions_json WHERE user_id=? AND code=?", (int(user_id), str(code or "").strip()))
        conn.commit()
        return c.rowcount or 0
    finally:
        conn.close()


def clear_user_positions_json(user_id):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM user_positions_json WHERE user_id=?", (int(user_id),))
        conn.commit()
        return c.rowcount or 0
    finally:
        conn.close()


def upsert_user_positions_daily(user_id, items, date, time_slot):
    if not items:
        return
    ts = int(time.time())
    conn = _connect()
    try:
        c = conn.cursor()
        for it in items:
            c.execute(
                "INSERT INTO user_positions_daily(user_id,date,time_slot,code,fund_name,amount,return_rate,profit,ts) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(user_id,date,time_slot,code) DO UPDATE SET fund_name=excluded.fund_name,amount=excluded.amount,return_rate=excluded.return_rate,profit=excluded.profit,ts=excluded.ts",
                (int(user_id), date, time_slot, it.get("code"), it.get("fund_name"), it.get("amount"), it.get("return_rate"), it.get("profit"), ts),
            )
        conn.commit()
    finally:
        conn.close()


def get_user_positions_daily(user_id, date=None):
    conn = _connect()
    try:
        c = conn.cursor()
        if date:
            c.execute(
                "SELECT date,time_slot,code,fund_name,amount,return_rate,profit,ts FROM user_positions_daily "
                "WHERE user_id=? AND date=? ORDER BY time_slot",
                (int(user_id), date),
            )
        else:
            c.execute(
                "SELECT date,time_slot,code,fund_name,amount,return_rate,profit,ts FROM user_positions_daily "
                "WHERE user_id=? ORDER BY date DESC, time_slot DESC LIMIT 500",
                (int(user_id),),
            )
        items = []
        for d, t, cd, nm, amt, rr, pf, ts in c.fetchall():
            items.append({"date": d, "time_slot": t, "code": cd, "fund_name": nm, "amount": amt, "return_rate": rr, "profit": pf, "ts": ts})
        return items
    finally:
        conn.close()


def sum_daily_profit_by_code(user_id, date):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT code, SUM(profit) FROM user_positions_daily WHERE user_id=? AND date=? GROUP BY code",
            (int(user_id), str(date or "")),
        )
        mp = {}
        for cd, sm in c.fetchall():
            mp[str(cd)] = float(sm or 0.0)
        return mp
    finally:
        conn.close()


def list_user_ids(include_admin=True):
    conn = _connect()
    try:
        c = conn.cursor()
        if include_admin:
            c.execute("SELECT id FROM users ORDER BY id ASC")
        else:
            c.execute("SELECT id FROM users WHERE username<>? ORDER BY id ASC", ("admin",))
        return [int(x[0]) for x in c.fetchall()]
    finally:
        conn.close()


def purge_non_admin_users():
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", ("admin",))
        row = c.fetchone()
        admin_id = int(row[0]) if row else None
        if admin_id is None:
            return {"ok": False, "error": "admin_missing", "deleted_users": 0, "deleted_sessions": 0, "deleted_positions": 0, "deleted_daily": 0}

        c.execute("SELECT id FROM users WHERE username<>?", ("admin",))
        other_ids = [int(x[0]) for x in c.fetchall()]
        if not other_ids:
            return {"ok": True, "deleted_users": 0, "deleted_sessions": 0, "deleted_positions": 0, "deleted_daily": 0}

        q_marks = ",".join(["?"] * len(other_ids))
        c.execute(f"DELETE FROM sessions WHERE user_id IN ({q_marks})", other_ids)
        deleted_sessions = c.rowcount or 0
        c.execute(f"DELETE FROM user_positions_json WHERE user_id IN ({q_marks})", other_ids)
        deleted_positions = c.rowcount or 0
        c.execute(f"DELETE FROM user_positions_daily WHERE user_id IN ({q_marks})", other_ids)
        deleted_daily = c.rowcount or 0
        c.execute(f"DELETE FROM users WHERE id IN ({q_marks})", other_ids)
        deleted_users = c.rowcount or 0
        conn.commit()
        return {
            "ok": True,
            "deleted_users": deleted_users,
            "deleted_sessions": deleted_sessions,
            "deleted_positions": deleted_positions,
            "deleted_daily": deleted_daily,
        }
    finally:
        conn.close()
