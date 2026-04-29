import cv2
import os
import re
import json
import subprocess
import shutil
import tkinter as tk
from tkinter import filedialog
from ollama import generate

class NSFWHighlightJoiner:
    def __init__(self, model_name='blaifa/InternVL3', min_score=90):
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
            title="분석할 영상을 선택하세요",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov")]
        )
        if not file_path: return False
        self.video_path = file_path
        print(f"\n--- 대상 파일: {os.path.basename(self.video_path)} ---")
        return True

    def extract_frames_gpu(self):
        # AI 분석용 해상도 (이전 대화에서 설정한 840*640 적용)
        target_res = "1280x720"
        print(f"\n--- [GPU 가속] 프레임 추출 시작 (대상: {target_res}) ---")
        
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0: return []
        duration = total_frames / fps
        cap.release()

        # 인트로 30% 제외 및 엔딩 1분 제외 샘플링
        start_time = duration * 0.15 
        interval = (duration - start_time - 60) / self.max_frames
        frame_data = []

        for i in range(1, self.max_frames + 1):
            target_time = start_time + ((i-1) * interval)
            frame_filename = os.path.join(self.temp_dir, f"f_{i:03d}.jpg")
            
            cmd = [
                'ffmpeg', '-y', '-hwaccel', 'cuda', '-ss', f"{target_time:.2f}", 
                '-i', self.video_path, '-vframes', '1', 
                '-s', target_res, '-f', 'image2', 
                frame_filename
            ]
            
            # 프로세스 실행
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            frame_data.append({"path": frame_filename, "time": round(target_time, 2)})
            
            # [로그 추가] 10장 단위 혹은 매 장마다 진행 상황 출력
            if i % 10 == 0 or i == self.max_frames:
                percent = (i / self.max_frames) * 100
                print(f" > 진행도: {percent:5.1f}% | 추출 완료: {i:3d}/{self.max_frames} 장 (지점: {round(target_time, 1)}s)")

        print(f"--- 추출 프로세스 완료! (총 {len(frame_data)}장 저장됨) ---\n")
        return frame_data

    def analyze_chunks(self, frame_data, chunk_size=30):
        all_results = []
        num_chunks = len(frame_data) // chunk_size
        
        for i in range(num_chunks):
            start_idx = i * chunk_size
            end_idx = start_idx + chunk_size
            chunk = frame_data[start_idx:end_idx]
            
            print(f"\n[구간 {i+1}/{num_chunks}] 분석 중... (시작점: {chunk[0]['time']}s)")
            
            # 파일 읽기 및 바이트 변환
            images_bytes = [open(d['path'], "rb").read() for d in chunk]
            time_labels = [f"T:{d['time']}s" for d in chunk]

            # analyze_chunks 메서드 내부 프롬프트 부분만 교체
            prompt = f"""You are a strict JAV penetration detector specialized in mechanical action recognition.

                You are given {len(chunk)} frames in strict chronological order with timestamps.

                TIMESTAMPS: {", ".join(time_labels)}

                TASK:
                Detect ONLY clear vaginal or anal penetration scenes with visible rhythmic piston thrusting.

                STRICT RULES (never break these):
                1. Must see the penis clearly **inserted** into vagina or anus + continuous back-and-forth piston movement.
                2. If insertion is not clearly visible for most of the sequence, score below 30.
                3. Oral sex, blowjob, handjob, fingering, kissing, tit play, teasing without insertion → score 0~25.
                4. Score 90+ only when thrusting is fast, deep, continuous, and shows visible body impact or recoil.

                Analyze ALL frames from first to last. Do not focus only on early frames.

                Return **ONLY** a valid JSON array. No explanation, no markdown, no extra text.
                If no qualifying scene, return [].

                Correct format:
                [
                  {{"start": 3420, "end": 3455, "score": 96, "reason": "fast deep vaginal penetration with strong piston impact"}},
                  {{"start": 3780, "end": 3812, "score": 91, "reason": "intense continuous anal piston thrusting"}}
                ]
                """

            try:
                # AI 생성 요청
                response = generate(model=self.model_name, prompt=prompt, images=images_bytes, stream=False, format="json")
                raw_text = response['response'].strip()
                
                if not raw_text:
                    print(f" > [주의] AI가 응답을 거부했거나 빈 값을 보냈습니다.")
                    continue

                data = json.loads(raw_text)
                found_list = []
                
                # 유연한 파싱 로직
                if isinstance(data, list):
                    found_list = data
                elif isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, list): found_list.extend(v)
                    if not found_list and 'start' in data:
                        found_list = [data]

                print(f"--- AI 분석 의견 ({len(found_list)}건 발견) ---")
                for item in found_list:
                    if not isinstance(item, dict): continue
                    score = item.get('score', 0)
                    if score >= 90:
                        print(f"-> [발견] {item.get('start')}s (점수:{score}): {item.get('reason', '')}")
                    all_results.append(item)

            # [핵심 수정] 에러가 발생했을 때 처리할 블록 추가
            except Exception as e:
                print(f" > [구간 {i+1} 에러] 분석 실패: {e}")
                continue # 에러 난 구간은 포기하고 다음 구간으로 진행
        
        # 모든 반복문이 끝난 뒤 최종 리스트 반환 (for 문과 줄 맞춤)
        return all_results

    def process_and_merge(self, results):
        import re
        if not results: return

        def clean_float(val):
            """T:4530ss 같은 지저분한 문자열에서 숫자만 추출"""
            if isinstance(val, (int, float)): return float(val)
            if isinstance(val, str):
                match = re.search(r"[-+]?\d*\.\d+|\d+", val)
                if match: return float(match.group())
            return 0.0

        print(f"\n--- [종합 분석 결과] ---")
        valid_segments = []
        for res in results:
            if not isinstance(res, dict) or 'start' not in res: continue
            
            score = res.get('score', 0)
            start = clean_float(res.get('start', 0))
            end = clean_float(res.get('end', 0))
            
            # 엑기스 밀도를 위해 최대 30초로 제한
            if (end - start) > 30: end = start + 30
            
            if score >= self.min_score and start < end:
                valid_segments.append({'start': start, 'end': end, 'score': score})

        # 발견된 구간 출력
        for i, seg in enumerate(valid_segments, 1):
            print(f"[{i}] {round(seg['start'], 1)}s ~ {round(seg['end'], 1)}s | 점수: {seg['score']}")

        if not valid_segments:
            print(f"--- 기준({self.min_score})을 넘는 하이라이트가 없습니다. ---")
            return

        # 여기서부터 인코딩 로그가 찍혀야 정상입니다
        print(f"\n--- {len(valid_segments)}개 구간 인코딩 시작 (840x640 / HEVC) ---")
        temp_dir_abs = os.path.abspath(self.temp_dir)
        concat_list_path = os.path.join(temp_dir_abs, "concat.txt")
        
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(valid_segments):
                # 파일명에 특수문자가 많으므로 경로를 안전하게 처리
                temp_segment_path = os.path.join(temp_dir_abs, f"seg_{i}.mp4").replace("\\", "/")
                
                print(f" > [{i+1}/{len(valid_segments)}] 구간 처리 중...")
                
                cmd = [
                    'ffmpeg', '-y', '-ss', str(seg['start']), '-i', self.video_path,
                    '-t', str(seg['end'] - seg['start']),
                    '-vf', 'scale=840:640',
                    '-c:v', 'hevc_nvenc', '-preset', 'p6', '-rc', 'vbr', '-cq', '25', '-b:v', '0',
                    '-c:a', 'aac', '-b:a', '128k', 
                    temp_segment_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                f.write(f"file '{temp_segment_path}'\n")

        # 최종 병합 파일명 설정
        output_filename = "FINAL_HIGHLIGHT_840x640.mp4"
        output_path = os.path.join(os.path.dirname(self.video_path), output_filename)
        
        print(f"--- 모든 구간 병합 중... ---")
        merge_cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_path,
            '-c', 'copy', output_path
        ]
        
        subprocess.run(merge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        
        if os.path.exists(output_path):
            print(f"\n--- [완료] 저장 성공! ---")
            print(f"파일 위치: {output_path}")
        else:
            print("\n--- [오류] 최종 파일 생성에 실패했습니다. FFmpeg 로그를 확인하세요. ---")

    def run(self):
        if not self.select_file(): return
        frames = self.extract_frames_gpu()
        if not frames: return
        # 분할 분석 모드 실행
        results = self.analyze_chunks(frames)
        self.process_and_merge(results)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

if __name__ == "__main__":
    extractor = NSFWHighlightJoiner(min_score=70)
    extractor.run()