# coding=utf-8
"""config.yaml 与讲稿文件 (trans) 的加载工具。

config.yaml 不再保存逐页讲稿, 只保存 trans 指向的讲稿 YAML 文件路径和
audio_dir 音频目录等设置; 讲稿文件沿用 slides 结构:

    slides:
      - page: 1
        text: "你好"
"""
import os

import yaml

DEFAULT_CONFIG = "config.yaml"


def load_config(path=DEFAULT_CONFIG, data=None):
    """读取配置并合并 trans 讲稿, 返回 dict。

    - data 非 None 时直接使用该 dict (不再读取 path), 但 trans 仍按 path 所在目录解析
    - trans 指向的讲稿 YAML 合并为 data['slides']
    - audio_dir 为音频目录, 缺省为 audio
    """
    base_dir = os.path.dirname(os.path.abspath(path)) if path else os.getcwd()
    if data is None:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

    trans = data.get("trans")
    if trans and "slides" not in data:
        trans_path = trans if os.path.isabs(trans) else os.path.join(base_dir, trans)
        with open(trans_path, "r", encoding="utf-8") as f:
            slides = yaml.safe_load(f) or {}
        if isinstance(slides, dict):
            slides = slides.get("slides", [])
        data["slides"] = slides
        data["trans"] = trans_path

    if not data.get("audio_dir"):
        data["audio_dir"] = "audio"
    return data


def load_slides(config):
    """返回按页码排序的讲稿列表, 无讲稿时返回 []"""
    slides = config.get("slides") or []
    return sorted(slides, key=lambda s: int(s.get("page", 0)))
