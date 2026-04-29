import os
import sys
import glob
from pathlib import Path
from typing import List, Dict, Any

try:
    from PIL import Image
    from transformers import pipeline
    from tqdm import tqdm
    import torch
except ImportError:
    print("Error: Missing required libraries. Please run: pip install transformers Pillow tqdm torch torchvision")
    sys.exit(1)

"""
NSFW Scene Analyzer (Standalone Prototype)
==========================================
- Model: falconsai/nsfw_image_detection (ViT based, ~80MB)
- Usage: python nsfw_analyzer.py <image_directory> [threshold]
"""

def analyze_directory(image_dir: str, threshold: float = 0.8):
    image_paths = []
    # 스냅샷 폴더 내의 이미지 파일들 탐색
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
        image_paths.extend(glob.glob(os.path.join(image_dir, ext)))
    
    # 파일명 순서대로 정렬 (시간 순서 보존)
    image_paths.sort()
    
    if not image_paths:
        print(f"Directory empty or no images found in: {image_dir}")
        return

    print(f"Found {len(image_paths)} images. Loading AI model...")
    
    # GPU 사용 가능 여부 확인
    device = 0 if torch.cuda.is_available() else -1
    classifier = pipeline("image-classification", model="falconsai/nsfw_image_detection", device=device)
    
    print(f"Analyzing images on {'GPU' if device == 0 else 'CPU'}...")
    results = []
    
    for path in tqdm(image_paths):
        try:
            img = Image.open(path)
            # 분류 실행
            pred = classifier(img)
            # pred: [{'label': 'nsfw', 'score': 0.9}, {'label': 'normal', 'score': 0.1}] 형태
            nsfw_score = next((x['score'] for x in pred if x['label'] == 'nsfw'), 0.0)
            
            results.append({
                "path": path,
                "name": os.path.basename(path),
                "score": nsfw_score
            })
        except Exception as e:
            print(f"Error processing {os.path.basename(path)}: {e}")

    # 결과 분석: 액션 씬(연속된 고점수 구간) 탐지
    print("\n" + "="*50)
    print("  ACTION SCENE DETECTION REPORT")
    print("="*50)
    
    clusters = []
    current_cluster = []
    
    for item in results:
        if item['score'] >= threshold:
            current_cluster.append(item)
        else:
            if current_cluster:
                clusters.append(current_cluster)
                current_cluster = []
    if current_cluster:
        clusters.append(current_cluster)

    if not clusters:
        print(f"No active scenes found (threshold >= {threshold})")
    else:
        print(f"Detected {len(clusters)} potential action scene(s):\n")
        for i, cluster in enumerate(clusters, 1):
            start_name = cluster[0]['name']
            end_name = cluster[-1]['name']
            avg_score = sum(x['score'] for x in cluster) / len(cluster)
            print(f"Scene #{i}")
            print(f"  > Start Image: {start_name}")
            print(f"  > End Image  : {end_name}")
            print(f"  > Intensity  : {avg_score:.2f} (Avg)")
            print(f"  > Frame Count: {len(cluster)}")
            print("-" * 30)

    print("\nTotal Finished.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python nsfw_analyzer.py <image_directory> [threshold]")
        print("Example: python nsfw_analyzer.py \"C:\\Path\\To\\Snapshots\" 0.8")
        # 사용자 편의를 위해 직접 경로 입력을 받음
        target = input("\nEnter images directory path: ").strip().replace('"', '')
        if target:
            analyze_directory(target)
    else:
        threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 0.95
        analyze_directory(sys.argv[1], threshold)
