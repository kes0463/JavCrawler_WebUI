# Ollama CPU 최적화 설정

## 문제
로컬 AI 번역 시 CPU 90%까지 상승

## 해결方案

### 1. 환경변수 설정 (.env 파일에 추가)

```bash
# Ollama CPU 스레드 제한
OLLAMA_NUM_THREAD=2
OLLAMA_THREADS=2

# 동시성 제한
JAVSTORY_TRANSLATION_CONCURRENCY=1
```

### 2. Ollama 서버 시작 시 옵션

```bash
# CPU 코어 2개로 제한하여 실행
ollama serve --num-thread 2
```

### 3. 코드에서 제한 (translator.py 수정)

```python
# 번역 요청 시 동시성 1로 제한
async def translate_metadata_batch(...):
    # 기존 코드...
    
    # 동시성 제한 추가
    if hasattr(self.router, 'set_concurrency'):
        self.router.set_concurrency(1)
```

### 4. 권장 모델 변경

| 현재 모델 | 권장 변경 | CPU 감소 |
|-----------|----------|---------|
| llama3.1:8b | llama3.1:4b | ~50% |
| llama3.1:8b | gemma2:2b | ~70% |

```bash
ollama pull llama3.1:4b
```

### 5. 실행 명령어

```powershell
# 환경변수와 함께 실행
$env:OLLAMA_NUM_THREAD="2"
python -m javstory.harvest.coordinator
```

---

**가장 간단한 해결**: `.env` 파일에 `OLLAMA_NUM_THREAD=2` 추가