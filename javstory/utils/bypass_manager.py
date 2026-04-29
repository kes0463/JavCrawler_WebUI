import subprocess
import sys
from pathlib import Path

class BypassManager:
    """GoodbyeDPI를 백그라운드에서 실행하고 관리하는 클래스"""
    def __init__(self, tools_dir=None):
        if tools_dir is None:
            self.root_dir = Path(__file__).resolve().parent.parent.parent
            self.tools_dir = self.root_dir / "tools" / "goodbyedpi"
        else:
            self.tools_dir = Path(tools_dir)
            
        self.process = None
        self.is_running = False

    def _get_executable_path(self):
        arch = "x86_64" if sys.maxsize > 2**32 else "x86"
        exe_path = self.tools_dir / arch / "goodbyedpi.exe"
        return exe_path

    def _is_external_process_running(self):
        """윈도우 프로세스 목록에서 goodbyedpi.exe가 있는지 확인"""
        try:
            # tasklist 명령어로 확인 (강력하고 외부 라이브러리 불필요)
            output = subprocess.check_output(
                'tasklist /FI "IMAGENAME eq goodbyedpi.exe" /NH',
                shell=True,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000
            ).decode('cp949', errors='ignore')
            return "goodbyedpi.exe" in output.lower()
        except Exception:
            return False

    def start(self):
        """서비스로 구동되므로 상태 확인만 수행"""
        self.is_running = self._is_external_process_running()
        return self.is_running

    def stop(self):
        """서비스 종료는 관여하지 않음"""
        pass

# 싱글톤 인스턴스
manager = BypassManager()
