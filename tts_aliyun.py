# coding=utf-8

import argparse
import os
import sys

import dashscope
from dashscope.audio.tts_v2 import *

from common import load_config, parse_pages

# 若没有将API Key配置到环境变量中，需将apiKey替换为自己的API Key
# dashscope.api_key = "apiKey"

model = "cosyvoice-v2"
voice = "longxiaocheng_v2"

#audio = synthesizer.call("arduino 的程序会保存为一个单独的目录，扩展名为 INO。Ardino 所使用的程序没有传统 C++ 里面的 IDE 函数")
#with open('output.mp3', 'wb') as f:
#    f.write(audio)


def main():
    parser = argparse.ArgumentParser(
        description="PDF2MOV 讲稿配音: 阿里云 CosyVoice 逐页合成 config 中 slides 的音频 (输出 mp3, "
                    "需将 voice.format 设为 mp3)")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径 (默认 config.yaml)")
    parser.add_argument("--trans", default=None,
                        help="讲稿 YAML 文件 (覆盖 config 的 trans, 相对路径按 config 所在目录解析)")
    parser.add_argument("--pages", default=None,
                        help="只合成指定页, 如 '1,3,5-9' (默认全部)")
    parser.add_argument("--audio-dir", default=None,
                        help="音频输出目录 (默认取 config 的 audio_dir)")
    parser.add_argument("--format", default=None, help="输出扩展名 (仅支持 mp3)")
    args = parser.parse_args()

    if args.format and args.format.lstrip(".").lower() != "mp3":
        print(f"错误: 阿里云引擎输出格式固定为 mp3, 不支持 '{args.format}'")
        sys.exit(1)

    config = load_config(args.config, trans=args.trans)
    audio_dir = args.audio_dir or config['audio_dir']
    pages = parse_pages(args.pages)

    os.makedirs(audio_dir, exist_ok=True)
    for slide in config['slides']:
        if pages is not None and int(slide['page']) not in pages:
            continue
        synthesizer = SpeechSynthesizer(model=model, voice=voice)
        audio = synthesizer.call(slide['text'])
        print('requestId: ', synthesizer.get_last_request_id())
        with open(f"{audio_dir}/{slide['page']}.mp3", 'wb') as f:
            f.write(audio)
            print(f"complete {slide['page']}.")


if __name__ == "__main__":
    main()
