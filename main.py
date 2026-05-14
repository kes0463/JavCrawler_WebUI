import sys
import os
import traceback
import warnings
import logging
from pathlib import Path

_ROOT_GUI = Path(__file__).resolve().parent
if str(_ROOT_GUI) not in sys.path:
    sys.path.insert(0, str(_ROOT_GUI))

from javstory.transcription.venv_bootstrap import reexec_with_project_venv_if_needed

reexec_with_project_venv_if_needed()

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ["QT_LOGGING_RULES"] = "qt.qpa.drawing=false;*.debug=false;*.info=false"

warnings.filterwarnings("ignore", category=UserWarning, module="onnxruntime")
warnings.filterwarnings("ignore", message=".*setPointSize.*")
logging.getLogger("onnxruntime").setLevel(logging.ERROR)

from javstory.utils.dll_patcher import apply_dll_patch
apply_dll_patch()
from javstory.utils.ffmpeg_path import bootstrap_path_env
bootstrap_path_env()

if __name__ == "__main__":
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt

        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        from PySide6.QtGui import QSurfaceFormat
        surface_format = QSurfaceFormat()
        surface_format.setAlphaBufferSize(8)
        QSurfaceFormat.setDefaultFormat(surface_format)

        print("[System] QApplication 인스턴스 생성 중...")
        app = QApplication(sys.argv)
        app.setApplicationName("JAVSTORY Pro")
        app.setOrganizationName("JAVSTORY")

        print("[System] QML 엔진 및 모델 초기화 시작...")
        from gui.app import create_engine
        engine = create_engine(app)

        print("[System] JAVSTORY Pro QML UI가 시작되었습니다.")
        sys.exit(app.exec())

    except Exception as e:
        print("\n" + "=" * 50)
        print("[CRITICAL ERROR] 프로그램 실행 중 치명적인 오류가 발생했습니다.")
        print("=" * 50)
        traceback.print_exc()

        log_dir = _ROOT_GUI / "logs"
        log_dir.mkdir(exist_ok=True)
        with open(log_dir / "crash_report.txt", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())

        print("\n상세 오류 내용이 'logs/crash_report.txt'에 저장되었습니다.")
        input("종료하시려면 엔터키를 누르세요...")
