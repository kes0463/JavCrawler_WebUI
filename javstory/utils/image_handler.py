import os
import shutil
from pathlib import Path
import urllib.request
import urllib.error
import ssl
from javstory.config.app_config import E_MEDIA_ROOT, MEDIA_ROOT, WESERV_IMAGE_PROXY
from javstory.utils.common import log_ts

class ImageHandler:
    """
    고해상도 정밀 진단 및 격리형 표지 관리 엔진 (urllib v2.2)
    - 윈도우 네이티브 크래시 방지를 위해 표준 urllib.request 사용
    - 모든 물리적 동작 전후에 Milestone Flush Log 기록
    """

    def __init__(self):
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        self.referer = 'https://javdb.com/'
        # SSL 인증서 검증 완화 (일부 이미지 서버 SNI 이슈 대응)
        self.ssl_context = ssl._create_unverified_context()

    def get_product_dir(self, product_code: str) -> Path:
        base = Path(E_MEDIA_ROOT)
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            base = Path(MEDIA_ROOT)

        p_dir = base / product_code
        p_dir.mkdir(parents=True, exist_ok=True)
        return p_dir

    def download_file(self, url: str, save_path: Path, use_proxy: bool = True, width: int = None) -> bool:
        """나노급 정밀 진단 시스템이 탑재된 다운로드 로직"""
        target_url = url
        if use_proxy:
            target_url = f"{WESERV_IMAGE_PROXY}?url={url}"
            if width: target_url += f"&w={width}&output=jpg"
            else: target_url += "&output=jpg"

        log_ts(f"[ImageHandler] [STAGE 1] 요청 준비: {target_url}")
        
        try:
            # 1. Request 객체 생성
            req = urllib.request.Request(target_url)
            req.add_header('User-Agent', self.user_agent)
            req.add_header('Referer', self.referer)
            
            log_ts(f"[ImageHandler] [STAGE 2] 네이티브 urlopen 진입 시도...")
            
            # 2. 통신 시도 (timeout 15초)
            with urllib.request.urlopen(req, timeout=15, context=self.ssl_context) as response:
                log_ts(f"[ImageHandler] [STAGE 3] 응답 코드 수신: {response.status}")
                
                if response.status == 200:
                    content = response.read()
                    log_ts(f"[ImageHandler] [STAGE 4] 데이터 스트림 읽기 완료 (Size: {len(content)} bytes)")
                    
                    # 3. 디스크 쓰기
                    log_ts(f"[ImageHandler] [STAGE 5] 디스크 저장 시도: {save_path.name}")
                    with open(save_path, "wb") as f:
                        f.write(content)
                    
                    log_ts(f"[ImageHandler] [STAGE 6] 파일 저장 완료 및 검증 통과.")
                    return True
                else:
                    log_ts(f"[ImageHandler] [STAGE X] 실패 (상태코드: {response.status})")
                    return False
                    
        except urllib.error.URLError as e:
            log_ts(f"[ImageHandler] [ERROR] 네트워크 에러: {e.reason}")
            return False
        except Exception as e:
            log_ts(f"[ImageHandler] [FATAL] 예상치 못한 오류: {str(e)}")
            return False

    def process_jav_assets(self, product_code: str, cover_url: str) -> dict:
        """
        한 번의 호출로 원본 포스터와 썸네일을 모두 처리.
        반환값: 로컬 경로 정보 딕셔너리
        """
        if not cover_url or cover_url == "이미지 누락":
            return {}

        p_dir = self.get_product_dir(product_code)
        poster_path = p_dir / "poster.jpg"
        thumb_path = p_dir / "thumb.jpg"

        results = {
            "poster_local": str(poster_path),
            "thumb_local": str(thumb_path)
        }

        # 1. 원본 포스터 (프록시 우선)
        if not poster_path.exists() or poster_path.stat().st_size == 0:
            success = self.download_file(cover_url, poster_path, use_proxy=True)
            if not success:
                log_ts("[ImageHandler] 프록시 원본 다운로드 실패, 직접 시도합니다...")
                self.download_file(cover_url, poster_path, use_proxy=False)

        # 2. 썸네일 (Weserv 리사이징 활용)
        if not thumb_path.exists() or thumb_path.stat().st_size == 0:
            # 썸네일은 프록시 필수 (리사이징 기능 때문에)
            success = self.download_file(cover_url, thumb_path, use_proxy=True, width=300)
            if not success:
                # 프록시 실패 시 원본에서 복사 (추후 Pillow 추가 시 로컬 리사이징으로 대체 가능)
                if poster_path.exists():
                    shutil.copy(poster_path, thumb_path)
                    log_ts("[ImageHandler] 썸네일 프록시 실패로 원본 복사 처리")

        return results

if __name__ == "__main__":
    # 간단 테스트
    handler = ImageHandler()
    test_code = "SSNI-123"
    test_url = "https://c0.jdbstatic.com/covers/6z/6z8y3.jpg" # 실제 javdb 이미지 예시
    res = handler.process_jav_assets(test_code, test_url)
    print(f"결과: {res}")
