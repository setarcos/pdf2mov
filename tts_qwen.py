#!/usr/bin/env python
# coding=utf-8
"""PDF2MOV 讲稿配音工具 —— 本地 Qwen3-TTS 引擎 (与 tts_xunfei.py / tts_aliyun.py 并列)

读取 config.yaml 中每个 slide 的 text, 逐页用本地 Qwen3-TTS 模型合成讲稿音频,
输出到 audio_dir/{page}.{format}, 供 pdf2mov.py 合并为视频。

两种模式 (传 --ref-wav 自动切换):
  * 默认 —— 自定义音色 (Qwen3-TTS-12Hz-1.7B-CustomVoice):
      内置 9 种音色 + 自然语言风格指令, 无需任何参考音频。
      音色: serena / vivian / uncle_fu / ryan / aiden / ono_anna / sohee / eric / dylan
      例: python tts_qwen.py --speaker serena --instruct "语速中等，适合用来作为教学配音。"
  * 传 --ref-wav —— 语音克隆 (Qwen3-TTS-12Hz-1.7B-Base):
      用 3 秒参考音频克隆音色。
      - 同时提供参考文字稿 (--ref-txt 文件 或 --ref-text 内联): ICL 模式, 效果最好
      - 或加 --x-vector-only: 仅用说话人嵌入, 无需文字稿, 效果略差

运行环境: 需要已安装 qwen_tts (Qwen3-TTS 源码包)、torch、transformers 的 python 环境
(安装方法见 Qwen3-TTS 官方仓库 README), 模型权重需提前下载 (ModelScope / HuggingFace 官方仓库)。

用法示例 (模型路径请替换为你本地的实际目录):

    python tts_qwen.py                                             # 默认: Uncle_Fu 教学风格
    python tts_qwen.py --model /path/to/Qwen3-TTS-12Hz-1.7B-CustomVoice
    python tts_qwen.py --ref-wav /path/to/ref.wav \
                       --ref-txt /path/to/ref.txt                  # 语音克隆 (Base 模型)

模型路径可用以下任一方式指定 (优先级从高到低):
  1. 命令行 --model <路径> (指定当前模式所用模型)
  2. config.yaml 的 qwen: 段: model_custom (自定义音色) / model_base (语音克隆)
  3. 环境变量: QWEN3_TTS_MODEL_CUSTOM / QWEN3_TTS_MODEL_BASE

config.yaml 可选的 qwen: 段示例 (命令行参数优先):

    qwen:
      model_custom: /path/to/Qwen3-TTS-12Hz-1.7B-CustomVoice
      model_base:   /path/to/Qwen3-TTS-12Hz-1.7B-Base
      speaker:      Uncle_Fu        # CustomVoice 内置音色名
      instruct:     语速中等，适合用来作为教学配音。
      language:     Chinese         # CustomVoice 默认 Chinese / 克隆默认 Auto
      ref_wav:      /path/to/ref.wav    # 提供后自动进入语音克隆模式
      ref_txt:      /path/to/ref.txt    # 参考音频文字稿(ICL 模式用)
      x_vector_only: false          # true 则只取说话人嵌入, 不需要 ref_txt
      device:       cuda:0
      max_new_tokens: 8192          # 生成最大 token 数(默认取模型 generation_config)
      max_text_chars: 500           # 超过该长度的整页文本按句切分后合成再拼接; 0 = 不切分
"""
import argparse
import os
import re
import sys
import time


# 模型路径 按以下顺序解析:
#   命令行 --model > config 的 qwen: 段 > 环境变量 > 报错提示
ENV_MODEL_CUSTOM = "QWEN3_TTS_MODEL_CUSTOM"   # 自定义音色模型 (CustomVoice)
ENV_MODEL_BASE = "QWEN3_TTS_MODEL_BASE"       # 语音克隆模型 (Base)

DEFAULT_SPEAKER = "Uncle_Fu"
DEFAULT_INSTRUCT = "语速中等，适合用来作为教学配音。"
SPEAKERS = ["serena", "vivian", "uncle_fu", "ryan", "aiden",
            "ono_anna", "sohee", "eric", "dylan"]  # CustomVoice 内置 9 音色

# 注: 部分 ROCm 平台上 flash/mem-efficient SDPA 的融合 kernel 不可用
# (报 hipErrorInvalidValue), 因此加载前强制使用兼容性最好的 math SDP (见 load_model)


# ---------------------------------------------------------------- 通用小工具
def log(msg):
    print(msg, flush=True)


def load_text_file(path):
    """读取文本文件内容 (UTF-8)"""
    path = os.path.expanduser(path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def split_long_text(text, max_chars):
    """把过长的一页文本按句末标点切成若干小段, 每段尽量不超过 max_chars。

    逐段合成再拼接, 可避免超长输入被截断; 在句号/感叹号等自然停顿处切分,
    对朗读韵律影响很小。max_chars<=0 表示不切分。
    """
    text = text.strip()
    if not text or max_chars <= 0 or len(text) <= max_chars:
        return [text]

    # 按句末标点切分(标点保留在句尾); 换行也视为分隔
    pieces = [p for p in re.split(r"(?<=[。！？!?；;\n])", text) if p.strip()]

    segs, buf = [], ""
    for p in pieces:
        while len(p) > max_chars:          # 罕见情况: 单句超长, 优先在逗号处软切
            cut = p.rfind("，", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if buf:
                segs.append(buf)
                buf = ""
            segs.append(p[:cut])
            p = p[cut:]
        if buf and len(buf) + len(p) > max_chars:
            segs.append(buf)
            buf = ""
        buf += p
    if buf.strip():
        segs.append(buf)
    return [s.strip() for s in segs if s.strip()]


def parse_pages(spec):
    """解析 --pages '1,3,5-9' 为页码列表; None 表示全部"""
    if spec is None:
        return None
    pages = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return pages


# ---------------------------------------------------------------- 模型加载
def load_model(model_path, device):
    """加载 Qwen3-TTS 模型 (惰性 import, 保证 --help 等在无 torch 环境下可用)"""
    try:
        import torch
        from qwen_tts import Qwen3TTSModel
    except ImportError as e:
        log(f"错误: 缺少 Qwen3-TTS 运行依赖 ({e})")
        log("请先在当前 python 环境安装 qwen_tts、torch、transformers")
        log("(安装方法见 Qwen3-TTS 官方仓库 README), 再用该环境运行本脚本")
        sys.exit(1)

    model_path = os.path.expanduser(model_path)
    if not os.path.isdir(model_path):
        log(f"错误: 找不到模型目录 '{model_path}'")
        log("请检查模型路径, 可用 --model / config 的 qwen: 段 / 环境变量指定")
        sys.exit(1)

    # 部分 ROCm 平台: flash/mem-efficient SDPA 融合 kernel 报 hipErrorInvalidValue,
    # 强制用 math SDP; flash_attention_2 需要 CUDA 版 flash-attn, ROCm 下不可用
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)

    if device.startswith("cuda") and not torch.cuda.is_available():
        log(f"警告: {device} 不可用, 回退到 CPU (速度会慢很多)")
        device = "cpu"

    log(f"正在加载模型: {model_path}")
    log(f"  设备: {device}, dtype: bfloat16")
    t0 = time.time()
    tts = Qwen3TTSModel.from_pretrained(
        model_path,
        device_map="cpu" if device == "cpu" else device,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    log(f"模型加载完成: {time.time() - t0:.1f}s")
    return tts, device


# ---------------------------------------------------------------- 合成
def _sync(device):
    """CUDA/ROCm 下同步, 使计时不包含异步队列"""
    if device.startswith("cuda"):
        import torch
        torch.cuda.synchronize()


def _concat_and_write(segs_wav, sr, out_path):
    """拼接分段音频(段间加 0.2s 停顿), 以 16bit PCM 写入 wav"""
    import numpy as np
    import soundfile as sf

    if len(segs_wav) == 1:
        audio = segs_wav[0]
    else:
        gap = np.zeros(int(0.2 * sr), dtype=np.float32)
        parts = []
        for i, w in enumerate(segs_wav):
            if i:
                parts.append(gap)
            parts.append(w.astype(np.float32, copy=False))
        audio = np.concatenate(parts)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sf.write(out_path, audio, sr, subtype="PCM_16")
    return audio.shape[0] / sr


def run(config, args):
    """主流程: 加载模型 -> 逐页合成"""
    q = config.get("qwen") or {}

    def pick(cli_val, cfg_key, default):
        if cli_val is not None:
            return cli_val
        return q.get(cfg_key, default)

    # ---- 模式与参数 ----
    ref_wav = pick(args.ref_wav, "ref_wav", None)
    clone_mode = bool(ref_wav)
    ref_wav = os.path.expanduser(ref_wav) if ref_wav else None
    if clone_mode and not str(ref_wav).startswith(("http://", "https://", "data:")) \
            and not os.path.exists(ref_wav):
        log(f"错误: 找不到参考音频 '{ref_wav}'")
        sys.exit(1)
    ref_txt_path = pick(args.ref_txt, "ref_txt", None)
    ref_text = pick(args.ref_text, "ref_text", None)
    x_vector_only = bool(pick(args.x_vector_only, "x_vector_only", False))

    # 模型路径解析: --model > config qwen 段 > 环境变量 (不内置本地默认路径)
    cfg_key = "model_base" if clone_mode else "model_custom"
    env_name = ENV_MODEL_BASE if clone_mode else ENV_MODEL_CUSTOM
    model_path = args.model or q.get(cfg_key) or os.environ.get(env_name)
    if not model_path:
        log(f"错误: 未指定{'语音克隆(Base)' if clone_mode else 'CustomVoice'}模型路径")
        log(f"可通过 --model <路径>、config.yaml 的 qwen.{cfg_key}、或环境变量 {env_name} 指定")
        sys.exit(1)

    speaker = pick(args.speaker, "speaker", DEFAULT_SPEAKER)
    instruct = pick(args.instruct, "instruct", DEFAULT_INSTRUCT)
    language = pick(args.language, "language", None)  # None = 模式默认
    device = pick(args.device, "device", "cuda:0")
    max_new_tokens = pick(args.max_new_tokens, "max_new_tokens", None)
    max_text_chars = int(pick(args.max_text_chars, "max_text_chars", 500) or 0)
    audio_dir = args.audio_dir or config.get("audio_dir", "audio")
    fmt = args.format or (config.get("voice") or {}).get("format", "wav")

    if not clone_mode and speaker.lower() not in {s.lower() for s in SPEAKERS}:
        log(f"错误: 未知音色 '{speaker}', 可选: {', '.join(SPEAKERS)}")
        sys.exit(1)

    if clone_mode:
        if not x_vector_only and not ref_text and not ref_txt_path:
            log("错误: 语音克隆模式需要提供参考文字稿 (--ref-txt 或 --ref-text), "
                "或使用 --x-vector-only 仅用说话人嵌入")
            sys.exit(1)
        if x_vector_only:
            log("克隆方式: x-vector only (仅说话人嵌入)")
        if ref_txt_path and not ref_text:
            ref_text = load_text_file(ref_txt_path)
    if language is None:
        language = "Auto" if clone_mode else "Chinese"

    slides = config.get("slides", [])
    if not slides:
        log("错误: config 中没有任何 slides")
        sys.exit(1)
    want_pages = parse_pages(args.pages)

    # ---- 预先过滤出待合成列表 (避免无任务时仍加载模型) ----
    jobs = []
    skipped = []
    for slide in slides:
        page, text = slide["page"], str(slide.get("text", "")).strip()
        out_path = os.path.join(audio_dir, f"{page}.{fmt}")
        if not text:
            skipped.append((page, "无文本"))
        elif want_pages is not None and page not in want_pages:
            skipped.append((page, "不在 --pages 范围"))
        elif args.skip_existing and os.path.exists(out_path):
            skipped.append((page, "已存在"))
        else:
            jobs.append((page, text, out_path))

    # ---- 打印计划 ----
    mode_name = "语音克隆 (Base 模型)" if clone_mode else "自定义音色 (CustomVoice 模型)"
    log(f"模式: {mode_name}")
    log(f"模型: {model_path}")
    if clone_mode:
        log(f"参考音频: {ref_wav}")
        log(f"参考文字稿: {(ref_text or '(无)')[:80]}")
    else:
        log(f"音色: {speaker} | 指令: {instruct}")
    log(f"语言: {language} | 输出目录: {audio_dir} | 格式: {fmt}")
    log(f"待合成页数: {len(jobs)} / 总页数: {len(slides)}")
    if skipped:
        for page, why in skipped:
            log(f"  跳过页 {page} ({why})")
    if not jobs:
        log("没有需要合成的页面, 退出")
        return

    # ---- 加载模型 ----
    tts, device = load_model(model_path, device)
    gen_kwargs = {}
    if max_new_tokens:
        gen_kwargs["max_new_tokens"] = int(max_new_tokens)

    # ---- 逐页合成 ----
    failures, total_t0 = [], time.time()
    for i, (page, text, out_path) in enumerate(jobs, 1):
        segs = split_long_text(text, max_text_chars)
        log(f"[{i}/{len(jobs)}] 页 {page}: 合成 {len(segs)} 段, 文本 {len(text)} 字 ...")
        t0 = time.time()
        try:
            if clone_mode:
                wavs, sr = tts.generate_voice_clone(
                    text=segs, language=language,
                    ref_audio=ref_wav, ref_text=ref_text if not x_vector_only else None,
                    x_vector_only_mode=x_vector_only, **gen_kwargs)
            else:
                wavs, sr = tts.generate_custom_voice(
                    text=segs, language=language,
                    speaker=speaker, instruct=instruct, **gen_kwargs)
            _sync(device)
            dur = _concat_and_write(wavs, sr, out_path)
            log(f"  -> {out_path} | 语音 {dur:.1f}s | 耗时 {time.time() - t0:.1f}s"
                f" | RTF {((time.time() - t0) / dur if dur else 0):.2f}x")
        except Exception as e:
            log(f"  页 {page} 合成失败: {e}")
            failures.append((page, str(e)))

    # ---- 汇总 ----
    log("")
    if failures:
        for page, err in failures:
            log(f"失败: 页 {page} -> {err}")
        log(f"共 {len(failures)} 页失败, 总耗时 {time.time() - total_t0:.0f}s")
        sys.exit(1)
    log(f"全部完成, 总耗时 {time.time() - total_t0:.0f}s")
    log("下一步: python pdf2mov.py  (将 audio/ 下音频与 PDF 页合并为视频)")


# ---------------------------------------------------------------- CLI
def main():
    parser = argparse.ArgumentParser(
        description="PDF2MOV 讲稿配音: 本地 Qwen3-TTS 逐页合成 config 中 slides 的音频 "
                    "(默认 CustomVoice 内置音色; 传 --ref-wav 自动切换语音克隆)")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径 (默认 config.yaml)")
    parser.add_argument("--pages", default=None,
                        help="只合成指定页, 如 '1,3,5-9' (默认全部)")
    parser.add_argument("--audio-dir", default=None, help="音频输出目录 (默认取 config 的 audio_dir)")
    parser.add_argument("--format", default=None, help="输出扩展名 (默认取 config 的 voice.format / wav)")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已存在的输出文件")
    # 模型/合成
    parser.add_argument("--model", default=None,
                        help="模型路径覆盖 (默认: 克隆模式用 Base, 否则用 CustomVoice 模型)")
    parser.add_argument("--device", default=None, help="运行设备 (默认 cuda:0)")
    parser.add_argument("--max-new-tokens", type=int, default=None,
                        help="生成最大 token 数 (默认取模型 generation_config)")
    parser.add_argument("--max-text-chars", type=int, default=None,
                        help="整页文本超过该长度时按句切分合成(默认 500; 0 = 不切分)")
    # CustomVoice 参数
    parser.add_argument("--speaker", default=None,
                        help=f"CustomVoice 音色 (默认 {DEFAULT_SPEAKER}; 可选: {', '.join(SPEAKERS)})")
    parser.add_argument("--instruct", default=None,
                        help=f"CustomVoice 风格指令 (默认 \"{DEFAULT_INSTRUCT}\")")
    parser.add_argument("--language", default=None,
                        help="合成语言 (默认: 自定义音色 Chinese / 语音克隆 Auto)")
    # 语音克隆参数
    parser.add_argument("--ref-wav", default=None,
                        help="参考音频路径, 提供后启用语音克隆 (Base 模型)")
    parser.add_argument("--ref-txt", default=None, help="参考音频文字稿文件路径 (ICL 模式)")
    parser.add_argument("--ref-text", default=None, help="参考音频文字稿内联文本 (与 --ref-txt 二选一)")
    parser.add_argument("--x-vector-only", action="store_true",
                        help="仅用说话人嵌入克隆, 无需参考文字稿 (效果略差)")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        log(f"错误: 找不到配置文件 '{args.config}' (请在包含 config.yaml 的目录下运行)")
        sys.exit(1)

    try:
        import yaml
        with open(args.config, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        log(f"错误: 读取配置失败 - {e}")
        sys.exit(1)

    if not config or "slides" not in config:
        log(f"错误: 配置缺少 slides 段: {args.config}")
        sys.exit(1)

    run(config, args)


if __name__ == "__main__":
    main()
