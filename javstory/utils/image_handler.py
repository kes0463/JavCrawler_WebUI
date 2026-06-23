import urllib.request
import urllib.error
import ssl
from pathlib import Path
import shutil
from javstory.config.app_config import E_MEDIA_ROOT, MEDIA_ROOT, WESERV_IMAGE_PROXY


class ImageHandler:
    """표지·썸네일 다운로드 (urllib 기반)."""

    def __init__(self):
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        self.referer = 'https://javdb.com/'
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
        target_url = url
        if use_proxy:
            target_url = f"{WESERV_IMAGE_PROXY}?url={url}"
            if width:
                target_url += f"&w={width}&output=jpg"
            else:
                target_url += "&output=jpg"

        try:
            req = urllib.request.Request(target_url)
            req.add_header('User-Agent', self.user_agent)
            req.add_header('Referer', self.referer)

            with urllib.request.urlopen(req, timeout=15, context=self.ssl_context) as response:
                if response.status != 200:
                    return False
                content = response.read()
                with open(save_path, "wb") as f:
                    f.write(content)
                return True
        except urllib.error.URLError:
            return False
        except Exception:
            return False

    def process_jav_assets(self, product_code: str, cover_url: str) -> dict:
        """원본 포스터와 썸네일을 한 번에 처리."""
        if not cover_url or cover_url == "이미지 누락":
            return {}

        p_dir = self.get_product_dir(product_code)
        poster_path = p_dir / "poster.jpg"
        thumb_path = p_dir / "thumb.jpg"

        results = {
            "poster_local": str(poster_path),
            "thumb_local": str(thumb_path)
        }

        if not poster_path.exists() or poster_path.stat().st_size == 0:
            success = self.download_file(cover_url, poster_path, use_proxy=True)
            if not success:
                self.download_file(cover_url, poster_path, use_proxy=False)

        if not thumb_path.exists() or thumb_path.stat().st_size == 0:
            success = self.download_file(cover_url, thumb_path, use_proxy=True, width=300)
            if not success and poster_path.exists():
                shutil.copy(poster_path, thumb_path)

        return results
