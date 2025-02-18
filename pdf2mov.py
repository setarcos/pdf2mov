import yaml
import cv2
import moviepy.editor as mp
import os
import subprocess

# 加载配置文件
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# 创建临时图像文件夹
os.makedirs('temp_images', exist_ok=True)

# 创建临时视频文件列表
temp_videos = []

for slide in config['slides']:
    page = slide['page']
    text = slide['text']
    audio_file = os.path.join(config['audio_dir'], f"{page}.{config['voice']['format']}")

    # 使用 convert 命令将 PDF 页面转换为图像
    image_file = os.path.join('temp_images', f'{page}.png')
    subprocess.run(['convert', '-density', '300', f'input.pdf[{page-1}]', image_file])

    # 读取图像文件
    image = cv2.imread(image_file)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # 转换为 RGB 颜色空间

    # 获取音频时长
    audio_clip = mp.AudioFileClip(audio_file)
    audio_len = audio_clip.duration

    clip_img = mp.ImageClip(image).set_duration(config['video']['silent_padding'])
    temp_videos.append(clip_img)

    # 将图像和音频合并为视频文件
    clip_img = mp.ImageClip(image).set_duration(audio_len)
    clip = clip_img.set_audio(audio_clip)

    # 添加字幕
    #txt_clip = mp.TextClip(text, fontsize=24, color='white', bg_color='black')
    #txt_clip = txt_clip.set_position(('center', 0.8)).set_duration(audio_len)
    #clip = mp.CompositeVideoClip([clip, txt_clip])

    # 添加到临时视频列表
    temp_videos.append(clip)

    clip_img = mp.ImageClip(image).set_duration(config['video']['silent_padding'])
    temp_videos.append(clip_img)

# 串联所有临时视频文件
final_clip = mp.concatenate_videoclips(temp_videos)

# 写入最终输出视频文件
final_clip.write_videofile(config['video']['output'], codec='libx264',
                           audio_codec='aac', temp_audiofile='temp-audio.m4a',
                           remove_temp=True, fps=config['video']['fps'])
