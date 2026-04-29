import os
import sys
import glob
from pathlib import Path
from typing import List, Dict, Any

try:
    from nudenet import NudeDetector
    from tqdm import tqdm
except ImportError:
    print("Error: Missing required libraries. Please run: pip install nudenet tqdm")
    sys.exit(1)

"""
NSFW Object Detection Prototype (NudeNet / YOLOv8 based)
======================================================
- Library: NudeNet (uses YOLOv8 internally)
- Usage: python object_detection_nsfw.py <image_directory>
"""

def analyze_directory_yolo(image_dir: str, min_score: float = 0.5):
    image_paths = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
        image_paths.extend(glob.glob(os.path.join(image_dir, ext)))
    
    image_paths.sort()
    
    if not image_paths:
        print(f"Directory empty or no images found in: {image_dir}")
        return

    print(f"Found {len(image_paths)} images. Loading YOLOv8 Detector model...")
    # NudeNet의 NudeDetector 초기화 (첫 실행 시 모델 다운로드)
    detector = NudeDetector()
    
    print(f"Detecting objects in images...")
    results = []
    
    # 모델에 분류할 클래스 정보가 포함되어 있음
    # 예: FEMALE_GENITALIA_EXPOSED, FEMALE_BREAST_EXPOSED, BUTTOCK_EXPOSED 등
    
    for path in tqdm(image_paths):
        try:
            # detect()는 리스트를 반환: [{'box': [x, y, w, h], 'score': 0.9, 'class': '...', ...}]
            detections = detector.detect(path)
            
            # 최소 점수 이상의 결과만 필터링
            valid_detections = [d for d in detections if d['score'] >= min_score]
            
            if valid_detections:
                results.append({
                    "name": os.path.basename(path),
                    "detections": valid_detections
                })
        except Exception as e:
            print(f"Error processing {os.path.basename(path)}: {e}")

    print("\n" + "="*50)
    print("  OBJECT DETECTION SUMMARY REPORT")
    print("="*50)
    
    if not results:
        print(f"No objects detected with score >= {min_score}")
    else:
        # 발견된 모든 클래스 통계 계산
        class_stats = {}
        for item in results:
            for d in item['detections']:
                cls = d['class']
                class_stats[cls] = class_stats.get(cls, 0) + 1
        
        print(f"Total images with detections: {len(results)} / {len(image_paths)}")
        print("\n[Found Classes Statistics]")
        for cls, count in sorted(class_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {cls:30}: {count} times")
            
        print("\n[Detection Timeline Highlights]")
        # 10개 이미지만 샘플로 보여줌 (너무 많을 수 있으므로)
        for item in results[:20]:
            classes = [d['class'] for d in item['detections']]
            # 중복 클래스 제거 및 요약
            cls_summary = ", ".join(set(classes))
            print(f"  {item['name']}: {cls_summary}")
            
        if len(results) > 20:
            print(f"  ... and {len(results) - 20} more images.")

    print("\nDetection Finished.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python object_detection_nsfw.py <image_directory>")
        target = input("\nEnter images directory path: ").strip().replace('"', '')
        if target:
            analyze_directory_yolo(target)
    else:
        analyze_directory_yolo(sys.argv[1])
