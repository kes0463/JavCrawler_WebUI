import cv2
import os
import re
import json
import subprocess
import shutil
import tkinter as tk
from tkinter import filedialog
import ollama

class NSFWHighlightJoiner:
    def __init__(self, model_name='minicpm-v', min_score=70):
        self.model_name = model_name
        self.temp_dir = "temp_processing"
        self.max_frames = 240
        self.min_score = min_score
        self.video_path = ""

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir)

    def select_file(self):
        root = tk.Tk(); root.withdraw()
        file_path = filedialog.askopenfilename(
            title="분석할 JAV 영상을 선택하세요",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov")]
        )
        root.destroy()
        if not file_path: return False
        self.video_path = file_path
        print(f"\n--- 대상 파일: {os.path.basename(self.video_path)} ---")
        return True

    def extract_frames_gpu(self):
        target_res = "1280x720"
        print(f"\n--- [GPU 가속] 프레임 추출 시작 ({target_res}) ---")
       
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 7200
        cap.release()

        start_time = duration * 0.15
        interval = (duration - start_time - 60) / self.max_frames
        
        frame_data = []
        for i in range(1, self.max_frames + 1):
            target_time = start_time + ((i-1) * interval)
            frame_filename = os.path.join(self.temp_dir, f"f_{i:03d}.jpg")
           
            cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-ss', f"{target_time:.2f}",
                   '-i', self.video_path, '-vframes', '1', '-s', target_res, frame_filename]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            
            frame_data.append({"path": frame_filename, "time": round(target_time, 2)})
            
            if i % 10 == 0 or i == self.max_frames:
                print(f" > 진행도: {(i/self.max_frames*100):5.1f}% | {i:3d}/{self.max_frames}장 ({round(target_time,1)}s)")
        
        print(f"--- 프레임 추출 완료! 총 {len(frame_data)}장 ---\n")
        return frame_data

    def analyze_chunks(self, frame_data, chunk_size=8):
        all_results = []
        num_chunks = (len(frame_data) + chunk_size - 1) // chunk_size

        for i in range(num_chunks):
            start_idx = i * chunk_size
            end_idx = min(start_idx + chunk_size, len(frame_data))
            chunk = frame_data[start_idx:end_idx]
            
            print(f"\n[구간 {i+1}/{num_chunks}] 분석 중... ({chunk[0]['time']}s ~ {chunk[-1]['time']}s)")

            images_bytes = [open(d['path'], "rb").read() for d in chunk]
            time_labels = [f"T:{d['time']}s" for d in chunk]

            # 1. 프롬프트 개선: 숫자만 출력하도록 강력하게 지시
            prompt = f"""You are a strict video analyzer. Output ONLY a JSON array.

TIMESTAMPS: {", ".join(time_labels)}

Task: Find ONLY vaginal or anal penetration with clear rhythmic piston thrusting.

Rules:
- Return ONLY valid JSON.
- "start" and "end" values MUST be pure numbers (e.g., 2013.41). Do NOT include 'T' or 's'.
- Must see penis visibly inserted + continuous thrusting to give score > 50.
- Oral, blowjob, handjob, fingering, kissing = score 0~20.
- Fast, deep, continuous thrusting = 90~100.

Format:
[
  {{"start": 2013.41, "end": 2079.78, "score": 90, "reason": "description"}}
]

If no qualifying scene, return exactly: []
"""

            try:
                response = ollama.chat(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt, "images": images_bytes}],
                    options={"temperature": 0.0, "num_predict": 700}
                )

                raw_text = response['message']['content'].strip()

                print(f"--- Raw Output (구간 {i+1}) ---")
                print(repr(raw_text[:700]))

                if not raw_text:
                    print(" > 빈 응답")
                    continue

                # 2. 강력한 정규식 클리닝
                # '[' 와 ']' 사이의 모든 문자열(배열)만 추출
                match = re.search(r'\[[\s\S]*\]', raw_text)
                
                if match:
                    json_str = match.group(0)
                    
                    # AI가 T:123.4s 형태로 출력한 것을 123.4 로 강제 치환
                    json_str = re.sub(r'T:([\d.]+)\s*s?', r'\1', json_str)
                    
                    try:
                        data = json.loads(json_str)

                        if isinstance(data, dict):
                            data = [data] if 'start' in data else []

                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    try:
                                        score = int(float(item.get('score', 0)))
                                    except:
                                        score = 0
                                    
                                    if score >= self.min_score:
                                        # 값들이 문자열로 들어왔을 경우를 대비해 float 변환 유지
                                        start = float(item.get('start', 0))
                                        end = float(item.get('end', start + 15))
                                        reason = item.get('reason', '')
                                        print(f"-> [발견] {start}s ~ {end}s | score: {score} | {reason}")
                                        all_results.append({'start': start, 'end': end, 'score': score})

                    except json.JSONDecodeError as e:
                        print(f" > JSON 파싱 실패: {e}")
                        print(f" > 문제의 문자열: {json_str}") # 디버깅용 출력
                else:
                    print(" > JSON 배열 형식을 찾을 수 없습니다.")

            except Exception as e:
                print(f" > [구간 {i+1} 에러] {e}")

        return all_results

    def process_and_merge(self, results):
        if not results:
            print("--- 하이라이트가 발견되지 않았습니다. ---")
            return

        valid_segments = []
        for res in results:
            if not isinstance(res, dict) or 'start' not in res: continue
            score = res.get('score', 0)
            start = float(res.get('start', 0))
            end = float(res.get('end', start + 15))
            if (end - start) > 30: end = start + 30
            if score >= self.min_score and start < end:
                valid_segments.append({'start': start, 'end': end})

        if not valid_segments:
            print("--- 기준 점수를 넘는 구간이 없습니다. ---")
            return

        print(f"\n--- {len(valid_segments)}개 구간 인코딩 시작 ---")
        temp_dir_abs = os.path.abspath(self.temp_dir)
        concat_list_path = os.path.join(temp_dir_abs, "concat.txt")

        with open(concat_list_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(valid_segments):
                temp_segment_path = os.path.join(temp_dir_abs, f"seg_{i}.mp4").replace("\\", "/")
                cmd = [
                    'ffmpeg', '-y', '-ss', str(seg['start']), '-i', self.video_path,
                    '-t', str(seg['end'] - seg['start']),
                    '-vf', 'scale=840:640',
                    '-c:v', 'hevc_nvenc', '-preset', 'p6', '-rc', 'vbr', '-cq', '25',
                    '-c:a', 'aac', '-b:a', '128k',
                    temp_segment_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                f.write(f"file '{temp_segment_path}'\n")

        output_path = os.path.join(os.path.dirname(self.video_path), "FINAL_HIGHLIGHT_840x640.mp4")
        merge_cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_path, '-c', 'copy', output_path]
        subprocess.run(merge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

        if os.path.exists(output_path):
            print(f"\n--- 완료! FINAL_HIGHLIGHT_840x640.mp4 생성됨 ---")
            print(f"경로: {output_path}")
        else:
            print("--- 최종 파일 생성 실패 ---")

    def run(self):
        if not self.select_file(): return
        frames = self.extract_frames_gpu()
        if not frames: return
        results = self.analyze_chunks(frames, chunk_size=8)
        self.process_and_merge(results)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


if __name__ == "__main__":
    extractor = NSFWHighlightJoiner(model_name='minicpm-v', min_score=50)
    extractor.run()