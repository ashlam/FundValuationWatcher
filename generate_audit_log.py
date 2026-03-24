import sqlite3
import json
from datetime import datetime

def generate_log():
    conn = sqlite3.connect('fundwatcher/users.sqlite')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 获取用户 (假设取最新活跃的用户，或者有持仓的用户)
    c.execute("SELECT DISTINCT user_id FROM user_positions_json")
    users = c.fetchall()
    
    for u in users:
        uid = u['user_id']
        print(f"=== 用户 ID: {uid} 的持仓审计日志 ===\n")
        
        c.execute("SELECT * FROM user_positions_json WHERE user_id=?", (uid,))
        positions = c.fetchall()
        
        for pos in positions:
            code = pos['code']
            fund_name = pos['fund_name']
            amt = pos['amount']
            current_te = pos['total_earnings']
            
            print(f"基金: {fund_name} ({code})")
            print(f"  录入本金: {amt}")
            print(f"  当前记录的持有收益: {current_te}")
            
            c.execute("SELECT * FROM user_positions_daily WHERE user_id=? AND code=? ORDER BY date ASC, time_slot ASC", (uid, code))
            daily_records = c.fetchall()
            
            if not daily_records:
                print("  (无历史净值日记录)\n")
                continue
                
            print("  [每日明细]")
            print(f"  {'日期':<12} | {'净值涨跌':<8} | {'当日盈亏':<10} | {'期末市值':<12} | {'累计收益':<10}")
            
            cur_val = amt or 0.0
            total_prof = 0.0
            for rec in daily_records:
                d = rec['date']
                pct = rec['return_rate']
                prof = rec['profit']
                
                # 重新验证计算逻辑
                expected_prof = cur_val * (pct / 100.0) if pct is not None else 0.0
                cur_val += prof
                total_prof += prof
                
                print(f"  {d:<12} | {f'{pct}%':<8} | {prof:<10.2f} | {cur_val:<12.2f} | {total_prof:<10.2f}")
                
            print(f"  -> 审计校验: 累加盈亏={total_prof:.2f}, 当前记录盈亏={current_te}\n")

if __name__ == '__main__':
    generate_log()
