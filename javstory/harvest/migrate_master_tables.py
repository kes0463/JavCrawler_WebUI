
import sqlite3
import shutil
import os
from pathlib import Path

# 경로 설정
src_db = r"d:\App\JAVSTORY\jav_database.db"
dst_db = r"d:\App\JAVSTORY\data\db\jav_database.db"
backup_db = dst_db + ".bak"

def migrate():
    # 1. 파일 존재 확인
    if not os.path.exists(src_db):
        print(f"Error: 원본 DB를 찾을 수 없습니다: {src_db}")
        return
    if not os.path.exists(dst_db):
        print(f"Error: 대상 DB를 찾을 수 없습니다: {dst_db}")
        return

    # 2. 백업 생성
    print(f"[*] 백업 생성 중: {backup_db}")
    shutil.copy2(dst_db, backup_db)

    # 3. 데이터 병합 (SQLite ATTACH 기능 사용)
    conn = sqlite3.connect(dst_db)
    cursor = conn.cursor()
    
    try:
        # 원본 DB를 'source'라는 별칭으로 연결
        cursor.execute(f"ATTACH DATABASE '{src_db}' AS source")
        
        tables = ["actresses", "genres", "makers"]
        
        for table in tables:
            print(f"[*] '{table}' 테이블 병합 중...")
            
            # 테이블 컬럼 정보 가져오기 (컬럼 불일치 대비)
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in cursor.fetchall() if row[1] != 'id'] # ID는 자동생성이므로 제외
            
            col_names = ", ".join(cols)
            
            # INSERT OR REPLACE를 사용하여 일본어 원문(Unique Key)이 겹치면 원본 DB 값으로 덮어씀
            # 참고: 각 테이블은 japanese 컬럼 등에 UNIQUE 제약조건이 있어야 함
            # 만약 제약조건이 없다면 단순히 중복될 수 있으므로 주의
            
            # 1. 존재하는지 확인 후 데이터 이동
            query = f"INSERT OR REPLACE INTO {table} ({col_names}) SELECT {col_names} FROM source.{table}"
            cursor.execute(query)
            
            affected = cursor.rowcount
            print(f"    -> {affected}개의 항목이 성공적으로 반영되었습니다.")

        conn.commit()
        print("\n[!] 모든 테이블 병합이 완료되었습니다!")
        
    except Exception as e:
        print(f"\n[X] 에러 발생: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
