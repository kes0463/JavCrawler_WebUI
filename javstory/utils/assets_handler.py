import os
import httpx
from pathlib import Path
from typing import Optional
import asyncio
from urllib.parse import urlparse

from javstory.config.app_config import E_MEDIA_ROOT, MEDIA_ROOT, WESERV_IMAGE_PROXY

class MetadataAssetsHandler:
    """
    크롤링된 메타데이터 자산(표지 이미지 등)을 로컬로 다운로드하고 관리하는 클래스.
    """
    def __init__(self):
        # 0. 미디어 루트 디렉토리 생성 (신규 HDD 루트 우선)
        try:
            E_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
            self._root = E_MEDIA_ROOT
        except Exception:
            MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
            self._root = MEDIA_ROOT

    async def download_cover_image(self, url: str, product_code: str) -> Optional[str]:
        """
        주어진 URL에서 표지 이미지를 다운로드하여 data/media/{product_code}/cover.jpg로 저장.
        성공 시 로컬 절대 경로를 반환, 실패 시 None 반환.
        """
        if not url or url == "이미지 누락":
            return None

        # 1. 대상 디렉토리 준비
        target_dir = Path(self._root) / product_code.upper()
        target_dir.mkdir(parents=True, exist_ok=True)
        
        save_path = target_dir / "cover.jpg"
        
        # [신규] 파일이 이미 존재하면 다운로드 스킵
        if save_path.is_file() and save_path.stat().st_size > 0:
            print(f"[Assets] 표지 이미지가 이미 존재합니다: {save_path}")
            return str(save_path)
        
        # 2. 다운로드 전략 수립 (Referer 동시 생성)
        parsed_url = urlparse(url)
        referer = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }

        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True, verify=False) as client:
            try:
                # [전략 1] 직접 다운로드 시도
                print(f"[Assets] 직접 다운로드 시도: {url}")
                response = await client.get(url, headers=headers)
                
                # [전략 2] 직접 다운로드 실패 시 Weserv 프록시 시도
                if response.status_code != 200:
                    proxy_url = f"{WESERV_IMAGE_PROXY}?url={url}&n=-1"
                    print(f"[Assets] 직접 다운로드 실패({response.status_code}), 프록시 사용: {proxy_url}")
                    response = await client.get(proxy_url, headers=headers)

                if response.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(response.content)
                    print(f"[Assets] 표지 다운로드 성공: {save_path}")
                    return str(save_path)
                else:
                    print(f"[Assets] 이미지 다운로드 최종 실패 (상태 코드: {response.status_code})")
                    return None
            except Exception as e:
                print(f"[Assets] 다운로드 중 오류 발생: {e}")
                return None

if __name__ == "__main__":
    # 독립 테스트용
    async def test():
        handler = MetadataAssetsHandler()
        url = "https://fourhoi.com/dass-026/cover-n.jpg"
        path = await handler.download_cover_image(url, "DASS-026")
        print(f"결과 경로: {path}")

    asyncio.run(test())
