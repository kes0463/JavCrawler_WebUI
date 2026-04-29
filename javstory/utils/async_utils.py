import asyncio


async def await_coro(coro, *, timeout: float | None = None):
    """
    async 컨텍스트에서 코루틴을 await한다.
    - `timeout`이 있으면 `asyncio.wait_for`로 상한을 둔다.
    - 부모 `asyncio.Task`가 취소되면 `wait_for`가 하위 코루틴에 취소를 전파한다
      (`asyncio.shield`를 쓰지 않음).
    """
    if timeout is None:
        return await coro
    return await asyncio.wait_for(coro, timeout=timeout)


def run_coroutine_sync(coro, *, timeout: float | None = None):
    """
    동기 컨텍스트에서 코루틴을 끝까지 실행해 결과를 반환한다.

    타임아웃
    - `timeout`(초)를 주면 `asyncio.wait_for`로 상한을 둔다. 기본 `None`은 무제한 대기다.
      장시간 작업(로컬 LLM 등)은 호출부에서 필요한 만큼 큰 값을 명시하는 것이 안전하다.

    취소·Ctrl+C
    - 동기 함수라 호출자의 `Task.cancel()`은 이 블로킹 호출에는 닿지 않는다.
      async 워커 안에서 취소 가능하게 하려면 `await await_coro(coro, timeout=...)`를 쓴다.
    - `asyncio.run` 동안 메인 스레드에서 Ctrl+C(KeyboardInterrupt)가 나면,
      CPython 3.11+에서는 루프가 정리되며 진행 중 코루틴도 취소 경로로 들어가는 경우가 많다
      (버전/플랫폼마다 완전하지 않을 수 있음).

    이미 이벤트 루프가 도는 스레드에서는 호출할 수 없다(BlockingError 대신 RuntimeError).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "run_coroutine_sync()는 실행 중인 asyncio 이벤트 루프 스레드에서 호출될 수 없습니다. "
            "이 호출은 UI/서버 루프를 블로킹(프리징)할 수 있습니다. "
            "호출 측에서 `await await_coro(...)` 또는 executor/thread로 우회하세요."
        )

    async def _run():
        if timeout is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=timeout)

    return asyncio.run(_run())


async def to_thread_with_timeout(func, /, *args, timeout: float | None = None, **kwargs):
    """
    `asyncio.to_thread`로 동기 함수를 워커 스레드에서 실행한다.
    `timeout`이 있으면 `asyncio.wait_for`로 await 상한을 둔다.

    주의: 타임아웃은 이벤트 루프 쪽 대기만 끊는다. 워커 스레드 안의
    동기 코드(예: LLM HTTP, 서브프로세스)는 즉시 중단되지 않을 수 있다.
    """
    inner = asyncio.to_thread(func, *args, **kwargs)
    if timeout is None:
        return await inner
    return await asyncio.wait_for(inner, timeout=timeout)
