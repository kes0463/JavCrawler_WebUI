
import sqlite3
from pathlib import Path

db_path = r"D:\App\JAVSTORY\data\db\jav_database.db"

def check_genre():
    if not Path(db_path).exists():
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. '내사정'이 한국어로 설정된 매핑 찾기
        print("--- '내사정' 한국어 매핑 조회 ---")
        cursor.execute("SELECT * FROM genres WHERE korean = '내사정'")
        rows = cursor.fetchall()
        for row in rows:
            print(f"ID: {row[0]}, JP: {row[1]}, KO: {row[2]}, EN: {row[3]}, Review: {row[4]}")
        
        # 2. '나카다시(中出し)' 일본어가 어떻게 등록되어 있는지 확인
        print("\n--- '中出し' 일본어 매핑 조회 ---")
        cursor.execute("SELECT * FROM genres WHERE japanese LIKE '%中出し%'")
        rows = cursor.fetchall()
        for row in rows:
            print(f"ID: {row[0]}, JP: {row[1]}, KO: {row[2]}, EN: {row[3]}, Review: {row[4]}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_genre()
