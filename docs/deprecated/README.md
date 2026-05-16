# Deprecated 설정 파일 (아카이브)

루트에 있던 레거시 JSON/INI입니다. **현재 코드베이스에서 읽지 않습니다** (2026-05 grep 기준 Python/QML 참조 0건).

## 대체 SoT

| 레거시 | 현재 |
|--------|------|
| `config.json` (Whisper/LLM/SceneDetect) | `javstory/config/app_config.py`, `.env`, `javstory/config/secrets_manager.py` |
| `javstory_player.ini` (`[Player] volume`) | QML 플레이어·`PlayerModel` (별도 ini 미사용) |

## 이 폴더 파일

| 파일 | 설명 |
|------|------|
| `config.json.example` | 예전 faster-whisper·LLM 기본값 샘플 (참고용) |
| `javstory_player.ini.example` | 예전 플레이어 볼륨 ini (참고용) |

신규 설정은 위 SoT에만 추가하세요.
