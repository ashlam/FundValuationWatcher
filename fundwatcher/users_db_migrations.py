MIGRATIONS = [
    (
        1,
        [
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE,password_hash TEXT,is_super INTEGER,created_at INTEGER)",
            "CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY,user_id INTEGER,created_at INTEGER,last_seen INTEGER)",
            "CREATE TABLE IF NOT EXISTS user_positions_json (user_id INTEGER,code TEXT,fund_name TEXT,amount REAL,earnings_yesterday REAL,total_earnings REAL,return_rate REAL,notes TEXT,updated_at INTEGER,PRIMARY KEY(user_id, code))",
            "CREATE TABLE IF NOT EXISTS user_positions_daily (user_id INTEGER,date TEXT,time_slot TEXT,code TEXT,fund_name TEXT,amount REAL,return_rate REAL,profit REAL,ts INTEGER,PRIMARY KEY(user_id, date, time_slot, code))",
            "CREATE TABLE IF NOT EXISTS user_favorites (user_id INTEGER,code TEXT,fund_name TEXT,note TEXT,created_at INTEGER,updated_at INTEGER,PRIMARY KEY(user_id, code))",
        ],
    ),
    (
        2,
        [
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_positions_json_user_updated ON user_positions_json(user_id, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_user_positions_daily_user_date ON user_positions_daily(user_id, date)",
            "CREATE INDEX IF NOT EXISTS idx_user_favorites_user_updated ON user_favorites(user_id, updated_at)",
        ],
    ),
]

LATEST_VERSION = MIGRATIONS[-1][0] if MIGRATIONS else 0

