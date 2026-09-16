#!/usr/bin/env python
# coding=utf-8
"""PDF2MOV: 将 PDF 每页与对应音频合成为视频。

讲稿内容保存在 config.yaml 中 trans 指向的讲稿 YAML 文件里, 可用 --trans 覆盖。
所有参数都能在命令行给出, 不依赖 config.yaml 也能一次完成转换:

    python pdf2mov.py --pdf input.pdf --trans trans.yaml --audio-dir audio -o output.mp4

也可以只用命令行覆盖部分参数, 其余读取 config.yaml:

    python pdf2mov.py -o output.mp4
"""
import argparse
import os
import subprocess
import sys

import cv2
import moviepy as mp

from common import DEFAULT_CONFIG, load_config, load_slides

TEMP_DIR = "temp_images"


def parse_args():
    parser = argparse.ArgumentParser(
        description="将 PDF 页面与音频合成为视频 (参数缺省时读取 config.yaml)")
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help="配置文件路径 (默认 config.yaml, 不存在则只使用命令行参数)")
    parser.add_argument("--trans", default=None, help="讲稿 YAML 文件 (覆盖 config 的 trans)")
    parser.add_argument("--pdf", default=None, help="PDF 文件 (默认 config 的 pdf / input.pdf)")
    parser.add_argument("--audio-dir", default=None,
                        help="音频输入目录 (默认 config 的 audio_dir / audio)")
    parser.add_argument("-o", "--output", default=None,
                        help="输出视频文件名 (默认 config 的 video.output)")
    parser.add_argument("--fps", type=int, default=None,
                        help="视频帧率 (默认 config 的 video.fps / 24)")
    parser.add_argument("--silent-padding", type=float, default=None,
                        help="每页前后静音时长秒 (默认 config 的 video.silent_padding / 0.5)")
    parser.add_argument("--format", dest="fmt", default=None,
                        help="音频扩展名 (默认 config 的 voice.format / wav)")
    parser.add_argument("--density", type=int, default=None, help="PDF 转图像 DPI (默认 300)")
    return parser.parse_args()


def discover_slides(audio_dir, fmt):
    """没有讲稿时, 从音频目录的文件名 (数字) 推断页码"""
    pages = set()
    if os.path.isdir(audio_dir):
        for name in os.listdir(audio_dir):
            stem, ext = os.path.splitext(name)
            if ext.lstrip(".").lower() == fmt.lstrip(".").lower() and stem.isdigit():
                pages.add(int(stem))
    return [{"page": p, "text": ""} for p in sorted(pages)]


def build_options(args):
    """合并 config.yaml 与命令行参数"""
    data = load_config(args.config) if os.path.exists(args.config) else {}
    if args.trans:
        data["trans"] = args.trans
        data.pop("slides", None)
    if args.pdf:
        data["pdf"] = args.pdf
    if args.audio_dir:
        data["audio_dir"] = args.audio_dir
    data = load_config(args.config, data)  # 解析 trans -> slides

    video = data.get("video") or {}
    return {
        "pdf": args.pdf or data.get("pdf") or "input.pdf",
        "audio_dir": args.audio_dir or data.get("audio_dir") or "audio",
        "output": args.output or video.get("output") or "output.mp4",
        "fps": args.fps or video.get("fps") or 24,
        "silent_padding": args.silent_padding if args.silent_padding is not None
                          else video.get("silent_padding", 0.5),
        "fmt": args.fmt or (data.get("voice") or {}).get("format") or "wav",
        "density": args.density or 300,
        "slides": load_slides(data),
    }


def main():
    args = parse_args()
    opts = build_options(args)

    if not opts["slides"]:
        opts["slides"] = discover_slides(opts["audio_dir"], opts["fmt"])
    if not opts["slides"]:
        print(f"错误: 没有讲稿, 也未在 '{opts['audio_dir']}' 找到 *.{opts['fmt']} 音频")
        print("请用 --trans 指定讲稿文件, 或用 --audio-dir / --format 指定音频")
        sys.exit(1)
    if not os.path.exists(opts["pdf"]):
        print(f"错误: 找不到 PDF 文件 '{opts['pdf']}'")
        sys.exit(1)

    os.makedirs(TEMP_DIR, exist_ok=True)
    temp_videos = []

    for slide in opts["slides"]:
        page = int(slide["page"])
        text = slide.get("text", "")
        audio_file = os.path.join(opts["audio_dir"], f"{page}.{opts['fmt']}")
        if not os.path.exists(audio_file):
            print(f"错误: 缺少第 {page} 页音频 '{audio_file}'")
            sys.exit(1)

        # 使用 convert 命令将 PDF 页面转换为图像
        image_file = os.path.join(TEMP_DIR, f"{page}.png")
        subprocess.run(["convert", "-density", str(opts["density"]),
                        f"{opts['pdf']}[{page - 1}]", image_file], check=True)

        # 读取图像文件
        image = cv2.imread(image_file)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # 转换为 RGB 颜色空间

        # 获取音频时长
        audio_clip = mp.AudioFileClip(audio_file)
        audio_len = audio_clip.duration

        temp_videos.append(mp.ImageClip(image).with_duration(opts["silent_padding"]))

        # 将图像和音频合并为视频文件
        clip = mp.ImageClip(image).with_duration(audio_len).with_audio(audio_clip)

        # 添加字幕
        #txt_clip = mp.TextClip(text=text, font_size=24, color='white', bg_color='black')
        #txt_clip = txt_clip.with_position(('center', 0.8)).with_duration(audio_len)
        #clip = mp.CompositeVideoClip([clip, txt_clip])

        temp_videos.append(clip)
        temp_videos.append(mp.ImageClip(image).with_duration(opts["silent_padding"]))

    # 串联所有临时视频文件
    final_clip = mp.concatenate_videoclips(temp_videos)

    # 写入最终输出视频文件
    final_clip.write_videofile(opts["output"], codec="libx264", audio_codec="aac",
                               temp_audiofile="temp-audio.m4a", remove_temp=True,
                               fps=opts["fps"])
    print(f"完成: {opts['output']}")


if __name__ == "__main__":
    main()
