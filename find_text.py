#!/usr/bin/env python
# coding=utf-8
"""在讲稿中查找包含指定词的页, 可选删除这些页的音频。

讲稿与音频目录取自 config.yaml (trans / audio_dir / voice.format), 也可用命令行覆盖:

    python find_text.py UNO                        # 列出讲稿中含 UNO 的页
    python find_text.py UNO --delete               # 并删除这些页的音频
    python find_text.py uno -i                     # 忽略大小写
    python find_text.py UNO --trans trans.yaml --audio-dir audio
"""
import argparse
import os
import sys

from common import load_config

DEFAULT_CONFIG = "config.yaml"


def parse_args():
    parser = argparse.ArgumentParser(
        description="查找讲稿中包含指定词的页 (加 --delete 同时删除这些页的音频)")
    parser.add_argument("word", help="要查找的词 (按字面匹配, 区分大小写)")
    parser.add_argument("-i", "--ignore-case", action="store_true", help="查找时忽略大小写")
    parser.add_argument("--delete", action="store_true",
                        help="删除匹配页对应的音频文件")
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help="配置文件路径 (默认 config.yaml)")
    parser.add_argument("--trans", default=None,
                        help="讲稿 YAML 文件 (覆盖 config 的 trans)")
    parser.add_argument("--audio-dir", default=None,
                        help="音频目录 (默认取 config 的 audio_dir / audio)")
    parser.add_argument("--format", dest="fmt", default=None,
                        help="音频扩展名 (默认取 config 的 voice.format / wav)")
    return parser.parse_args()


def find_pages(slides, word, ignore_case):
    """返回讲稿中含 word 的页码列表 (按讲稿顺序)"""
    needle = word.lower() if ignore_case else word
    pages = []
    for slide in slides:
        text = str(slide.get("text", ""))
        if ignore_case:
            text = text.lower()
        if needle in text:
            pages.append(int(slide["page"]))
    return pages


def delete_audio(audio_dir, fmt, pages):
    """删除这些页的音频文件, 返回实际删除的个数"""
    removed = 0
    for page in pages:
        path = os.path.join(audio_dir, f"{page}.{fmt}")
        if os.path.exists(path):
            os.remove(path)
            print(f"已删除 {path}")
            removed += 1
        else:
            print(f"未找到 {path} (跳过)")
    return removed


def main():
    args = parse_args()
    try:
        config = load_config(args.config, trans=args.trans)
    except Exception as e:
        print(f"错误: 读取讲稿失败 - {e}")
        sys.exit(1)

    slides = config.get("slides") or []
    if not slides:
        print(f"错误: 配置缺少讲稿 (trans 指向的 slides 段): {args.config}")
        sys.exit(1)

    pages = find_pages(slides, args.word, args.ignore_case)
    if not pages:
        print(f"讲稿中没有包含 '{args.word}' 的页")
        return

    page_spec = ", ".join(str(p) for p in pages)
    print(f"包含 '{args.word}' 的页: {page_spec}")
    if not args.delete:
        print("(加 --delete 可删除这些页的音频)")
        return

    audio_dir = args.audio_dir or config.get("audio_dir", "audio")
    fmt = args.fmt or (config.get("voice") or {}).get("format", "wav")
    removed = delete_audio(audio_dir, fmt, pages)
    print(f"共删除 {removed} 个音频文件 (第 {page_spec} 页, 格式 {fmt})")


if __name__ == "__main__":
    main()
