import os
import ssl
import sys
import json
import base64
import argparse
import wave
import websocket
from datetime import datetime
from time import mktime
import hashlib
import hmac
from wsgiref.handlers import format_date_time
from urllib.parse import urlencode

from common import load_config, parse_pages


class Ws_Param:
    def __init__(self, APPID, APIKey, APISecret):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret

    def create_url(self):
        url = 'wss://tts-api.xfyun.cn/v2/tts'
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = f"host: ws-api.xfyun.cn\ndate: {date}\nGET /v2/tts HTTP/1.1"
        signature_sha = hmac.new(self.APISecret.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode('utf-8')

        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')

        v = {
            "authorization": authorization,
            "date": date,
            "host": "ws-api.xfyun.cn"
        }

        return url + '?' + urlencode(v)


class WebSocketClient:
    def __init__(self, config):
        self.slides = config['slides']
        self.audio_dir = config['audio_dir']
        self.wsParam = Ws_Param(
            APPID=config['xunfei']['appid'],
            APISecret=config['xunfei']['apisec'],
            APIKey=config['xunfei']['apikey']
        )

    def create_message(self, text):
        """Create JSON payload with text encoding."""
        return json.dumps({
            "common": {"app_id": self.wsParam.APPID},
            "business": {"aue": "raw", "auf": "audio/L16;rate=16000", "vcn": "x4_lingfeizhe_zl", "tte": "utf8", "speed": 60},
            "data": {"status": 2, "text": str(base64.b64encode(text.encode('utf-8')), "utf-8")}
        })

    def save_pcm_to_wav(self, pcm_data, filename):
        """Convert PCM data to WAV format."""
        os.makedirs(self.audio_dir, exist_ok=True)
        wav_filename = f"{self.audio_dir}/{filename}.wav"
        with wave.open(wav_filename, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono audio
            wav_file.setsampwidth(2)  # 16-bit (2 bytes per sample)
            wav_file.setframerate(16000)  # 16 kHz sample rate
            wav_file.writeframes(pcm_data)

        print(f"Saved WAV file: {wav_filename}")

    def process_slide(self, slide):
        """Process a single slide: open connection, send text, receive response, save as WAV."""
        audio_buffer = b""

        def on_message(ws, message):
            """Handles responses from WebSocket."""
            nonlocal audio_buffer
            try:
                message = json.loads(message)
                code = message["code"]
                sid = message["sid"]
                audio = base64.b64decode(message["data"]["audio"])
                status = message["data"]["status"]

                if code != 0:
                    print(f"sid:{sid} error:{message['message']} code:{code}")
                    return

                # Append audio data to buffer
                audio_buffer += audio

                if status == 2:  # Final response, close connection
                    ws.close()

            except Exception as e:
                print("Error processing message:", e)

        def on_error(ws, error):
            print("### Error:", error)

        def on_close(ws, close_status_code, close_msg):
            print(f"WebSocket closed: {close_status_code}, {close_msg}")
            # Save PCM to WAV after connection closes
            slide_page = slide['page']
            self.save_pcm_to_wav(audio_buffer, f"{slide_page}")

        def on_open(ws):
            """Sends the text when connection is opened."""
            print(f"Sending: {slide['text']}")
            ws.send(self.create_message(slide['text']))

        # Create a new WebSocket connection for this message
        ws_url = self.wsParam.create_url()
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        ws.on_open = on_open
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})  # Blocking call

    def run(self, pages=None):
        """逐页处理 (pages 为 None 时处理全部), 每页重新建立连接"""
        for slide in self.slides:
            if pages is not None and int(slide['page']) not in pages:
                continue
            self.process_slide(slide)


def main():
    parser = argparse.ArgumentParser(
        description="PDF2MOV 讲稿配音: 讯飞在线 TTS 逐页合成 config 中 slides 的音频 (输出 wav)")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径 (默认 config.yaml)")
    parser.add_argument("--trans", default=None,
                        help="讲稿 YAML 文件 (覆盖 config 的 trans, 相对路径按 config 所在目录解析)")
    parser.add_argument("--pages", default=None,
                        help="只合成指定页, 如 '1,3,5-9' (默认全部)")
    parser.add_argument("--audio-dir", default=None,
                        help="音频输出目录 (默认取 config 的 audio_dir)")
    parser.add_argument("--format", default=None, help="输出扩展名 (仅支持 wav)")
    args = parser.parse_args()

    if args.format and args.format.lstrip(".").lower() != "wav":
        print(f"错误: 讯飞引擎输出格式固定为 wav, 不支持 '{args.format}'")
        sys.exit(1)

    config = load_config(args.config, trans=args.trans)
    if args.audio_dir:
        config['audio_dir'] = args.audio_dir

    client = WebSocketClient(config)
    client.run(parse_pages(args.pages))


if __name__ == "__main__":
    main()
