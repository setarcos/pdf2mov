# coding=utf-8

import dashscope
from dashscope.audio.tts_v2 import *
import yaml

# 若没有将API Key配置到环境变量中，需将apiKey替换为自己的API Key
# dashscope.api_key = "apiKey"

model = "cosyvoice-v2"
voice = "longxiaocheng_v2"

#audio = synthesizer.call("arduino 的程序会保存为一个单独的目录，扩展名为 INO。Ardino 所使用的程序没有传统 C++ 里面的 IDE 函数")
#with open('output.mp3', 'wb') as f:
#    f.write(audio)
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)
for slide in config['slides']:
    synthesizer = SpeechSynthesizer(model=model, voice=voice)
    audio = synthesizer.call(slide['text'])
    print('requestId: ', synthesizer.get_last_request_id())
    with open(f"{config['audio_dir']}/{slide['page']}.mp3", 'wb') as f:
        f.write(audio)
        print(f"complete {slide['page']}.")
