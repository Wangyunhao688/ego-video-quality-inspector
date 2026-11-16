import cv2
import os
import pandas as pd  # 【新增】引入 Pandas 库

# 1. 读取视频
video_path = "test.mp4"
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("错误：无法打开视频！")
else:
    print("视频读取成功，开始抽帧、质检并生成结构化报告...")
    
    save_folder = "frames"
    if not os.path.exists(save_folder):
        os.makedirs(save_folder)
        
    frame_count = 0
    blur_count = 0 
    
    # 【新增】准备两个空列表，用来装数据
    all_data = []   
    blur_data = []  
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_name = f"frame_{frame_count:04d}.jpg"
        frame_path = os.path.join(save_folder, frame_name)
        
        cv2.imwrite(frame_path, frame)
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # 【新增】把每一帧的名字和分数存进字典，再放进总列表
        row_data = {"帧文件名": frame_name, "清晰度分数": variance}
        all_data.append(row_data)
        
        # 如果模糊，不仅打印，还要存进模糊专属列表
        if variance < 50:
            print(f"警告：发现模糊帧 -> {frame_name} (清晰度分数: {variance:.2f})")
            blur_data.append(row_data)
            blur_count += 1
            
        frame_count += 1

    cap.release()
    
    # 【新增】用 Pandas 把列表变成表格 (DataFrame) 并导出 CSV
    df_all = pd.DataFrame(all_data)
    df_all.to_csv("quality_report.csv", index=False, encoding="utf-8-sig")
    
    # 只有当存在模糊帧时，才生成模糊报表
    if len(blur_data) > 0:
        df_blur = pd.DataFrame(blur_data)
        df_blur.to_csv("blur_frames.csv", index=False, encoding="utf-8-sig")
    else:
        print("完美！没有发现模糊帧，不生成 blur_frames.csv")
        
    print(f"处理完成！共处理 {frame_count} 帧。质量报告 quality_report.csv 已生成！")