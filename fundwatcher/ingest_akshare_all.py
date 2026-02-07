from .akshare import fetch_all_funds_basic
from .db import init_db, upsert_fund_profile

def main(limit=0, offset=0):
    init_db()
    items = fetch_all_funds_basic()
    if offset > 0:
        items = items[offset:]
    if limit and limit > 0:
        items = items[:limit]
    cnt = 0
    for it in items:
        code = str(it.get("code") or "").strip()
        if not code:
            continue
        name = it.get("name")
        type_ = it.get("type")
        upsert_fund_profile(code, name, type_, None, None)
        cnt += 1
    print(cnt)

if __name__ == "__main__":
    main()
