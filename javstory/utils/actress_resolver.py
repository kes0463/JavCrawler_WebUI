from javstory.harvest.database import get_db_session, Actress

class ActressResolver:
    """
    메인 데이터베이스(jav_database.db)의 actresses 테이블을 사용하여 
    배우의 다국어(JA, KO, Romaji) 이름을 매핑하는 클래스.
    """
    def __init__(self):
        pass

    def resolve_names(self, japanese_names: list[str] | str) -> dict[str, list[str]]:
        """
        일본어 이름 리스트(또는 쉼표 구분 문자열)를 받아 각 언어별 리스트로 반환.
        매핑 데이터가 없으면 원본 일본어 이름을 보관하여 추후 수동 수정을 지원함.
        """
        if isinstance(japanese_names, str):
            japanese_names = [n.strip() for n in japanese_names.split(",") if n.strip()]

        ja_list = []
        ko_list = []
        ro_list = []
        zh_cn_list = []
        zh_tw_list = []

        if not japanese_names:
            return {"ja": [], "ko": [], "romaji": [], "zh_cn": [], "zh_tw": []}

        session = get_db_session()
        try:
            for name in japanese_names:
                name = name.strip()
                if not name:
                    continue
                
                # 메인 DB의 actresses 테이블에서 조회
                row = session.query(Actress).filter_by(japanese=name).first()
                
                if row:
                    ja_val = row.japanese or name
                    ko_val = row.korean or name   # None이면 일본어 원문으로 폴백
                    ro_val = row.romaji or name   # None이면 일본어 원문으로 폴백
                else:
                    # [Pending 추가] DB에 없는 배우 발견 → korean/romaji는 NULL 유지
                    # 사용자가 수동 수정 후 resync 버튼으로 jav_metadata에 반영
                    new_actress = Actress(
                        japanese=name,
                        korean=None,        # 미입력 상태 명시
                        romaji=None,        # 미입력 상태 명시
                        needs_review=True   # 수동 확인 필요 표시
                    )
                    session.add(new_actress)
                    session.commit()
                    ja_val, ko_val, ro_val = name, name, name  # 폴백: 일본어 원문 사용
                
                ja_list.append(ja_val)
                ko_list.append(ko_val)
                ro_list.append(ro_val)
                
                # 중문 매핑 (요청에 따라 Romaji/English로 대체)
                zh_cn_list.append(ro_val)
                zh_tw_list.append(ro_val)
        except Exception as e:
            print(f"[ActressResolver] Error: {e}")
            # 에러 발생 시 원본 리스트를 모든 필드에 반환
            return {
                "ja": japanese_names, "ko": japanese_names, "romaji": japanese_names,
                "zh_cn": japanese_names, "zh_tw": japanese_names
            }
        finally:
            session.close()

        return {
            "ja": ja_list, "ko": ko_list, "romaji": ro_list, "zh_cn": zh_cn_list, "zh_tw": zh_tw_list
        }

if __name__ == "__main__":
    # 테스트
    resolver = ActressResolver()
    test_names = ["三上悠亜", "白石茉莉奈"]
    result = resolver.resolve_names(test_names)
    print(f"매핑 결과: {result}")
