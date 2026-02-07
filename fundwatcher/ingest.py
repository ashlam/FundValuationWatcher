import sys
from .eastmoney import fetch_fund_profile, fetch_asset_allocation, fetch_top_holdings
from .db import init_db, upsert_fund_profile, upsert_asset_allocations, upsert_holdings

def ingest_codes(codes):
    init_db()
    for code in codes:
        prof = fetch_fund_profile(code)
        if prof:
            upsert_fund_profile(code, prof.get("name"), prof.get("type"), prof.get("company"), prof.get("managers"))
        allocs = fetch_asset_allocation(code)
        if allocs:
            upsert_asset_allocations(code, allocs)
        holds = fetch_top_holdings(code)
        if holds and holds.get("items"):
            upsert_holdings(code, holds.get("report_date"), holds.get("items"))

def main():
    if len(sys.argv) < 2:
        print("usage: python -m fundwatcher.ingest 110022,161039")
        return
    raw = sys.argv[1]
    codes = [x.strip() for x in raw.split(",") if x.strip()]
    ingest_codes(codes)
    print("done")

if __name__ == "__main__":
    main()
