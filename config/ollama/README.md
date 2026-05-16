# Ollama 로컬 번역 모델 (Modelfile)

JAVSTORY는 OpenRouter·Ollama 등을 [`javstory/llm/engine.py`](../../javstory/llm/engine.py)에서 호출합니다.  
본 Modelfile은 **로컬 Ollama**에 일본어→한국어 AV 자막 스타일 커스텀 모델을 올릴 때 사용합니다.

## 사전 조건

- [Ollama](https://ollama.com/) 설치 및 실행 (`ollama serve`)
- 베이스 GGUF가 Ollama에 pull 되어 있거나, `FROM` URL 접근 가능

## 모델 생성

저장소 루트에서:

**Windows**

```bat
scripts\ollama_create_model.bat
```

**Linux / macOS**

```bash
chmod +x scripts/ollama_create_model.sh
./scripts/ollama_create_model.sh
```

수동:

```bash
ollama create javstory-ko-av -f config/ollama/Modelfile
```

기본 생성 이름: `javstory-ko-av` (스크립트에서 `JAVSTORY_OLLAMA_MODEL`로 변경 가능).

## 앱 연동

1. Settings → LLM에서 provider **Ollama** 선택
2. 모델 이름을 `javstory-ko-av`(또는 생성한 이름)로 맞춤
3. `OLLAMA_HOST` / `.env` — [INSTALL.md](../../INSTALL.md), [llm_troubleshooting.md](../../docs/llm_troubleshooting.md)

## Modelfile 수정

[`Modelfile`](Modelfile)의 `FROM`, `SYSTEM`, `PARAMETER`를 편집한 뒤:

```bash
ollama create javstory-ko-av -f config/ollama/Modelfile
```

동일 이름이면 기존 태그를 덮어씁니다.

## 루트 `Modelfile` (레거시)

이전에 루트에 두던 파일은 **`config/ollama/Modelfile`** 로 이전했습니다.
