import cv2
import os

# 1. 读取视频
video_path = "test.mp4"
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("错误：无法打开视频！")
else:
    print("视频读取成功，开始抽帧并质检...")
    
    # ================= 就是这两行，负责自动建文件夹 =================
    save_folder = "frames"
    if not os.path.exists(save_folder):
        os.makedirs(save_folder)
    # ================================================================
        
    frame_count = 0
    blur_count = 0 
    
    # 2. 循环读取每一帧
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # 3. 给这帧图片起名字
        frame_name = f"frame_{frame_count:04d}.jpg"
        frame_path = os.path.join(save_folder, frame_name)
        
        # 4. 把图片保存到 frames 文件夹
        cv2.imwrite(frame_path, frame)
        
        # 5. 计算清晰度
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # 这里我已经帮你改回 50 了
        if variance < 50:
            print(f"警告：发现模糊帧 -> {frame_name} (清晰度分数: {variance:.2f})")
            blur_count += 1
            
        frame_count += 1

    cap.release()
    print(f"处理完成！共切出 {frame_count} 张图，发现 {blur_count} 张模糊图，已自动保存在 frames 文件夹中。")