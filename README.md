# PDF2MOV

将 PDF 文件转换为可播放的视频文件。

## 依赖软件

 * ImageMagick

## 使用方法

 1. 将 PDF 讲稿放到当前目录
 1. 修改 `config.yaml` 文件，设置文件输入输出目录
 1. 完善每一页的文字讲稿
 1. 设置讯飞 APPID 等信息（或改用本地 Qwen 引擎, 见下）
 1. 执行 `tts_xunfei.py` 生成讲稿音频（或 `tts_qwen.py` 本地 Qwen3-TTS）
 1. 执行 `pdf2mov.py` 将 PDF 页面和音频整合为视频

## 本地 Qwen 配音 (tts_qwen.py)

用本地 Qwen3-TTS 模型逐页合成讲稿音频（无需讯飞账号/联网），输出 `audio_dir/{page}.{format}`，
与讯飞版输出兼容，之后同样执行 `python pdf2mov.py` 合成视频。

**依赖**: 需要一个装有 `qwen_tts`（Qwen3-TTS 源码包）、`torch`、`transformers` 的 Python
环境（安装方法见 Qwen3-TTS 官方仓库 README），并提前下载模型权重。模型可在 ModelScope /
HuggingFace 官方仓库获取：`Qwen3-TTS-12Hz-1.7B-CustomVoice`（内置音色）与
`Qwen3-TTS-12Hz-1.7B-Base`（语音克隆）。在 ROCm 平台上建议使用 bf16，脚本会自动关闭
不可用的 flash/mem-efficient SDPA kernel。

**指定模型路径**（三选一，优先级从高到低）：

```bash
# 1) 命令行参数（示例路径替换为你的实际目录）
python tts_qwen.py --model /path/to/Qwen3-TTS-12Hz-1.7B-CustomVoice

# 2) 环境变量（自定义音色 / 语音克隆分别设置, 两条命令按需执行）
export QWEN3_TTS_MODEL_CUSTOM=/path/to/Qwen3-TTS-12Hz-1.7B-CustomVoice
export QWEN3_TTS_MODEL_BASE=/path/to/Qwen3-TTS-12Hz-1.7B-Base
```

```yaml
# 3) config.yaml 增加可选的 qwen: 段（模型目录请写入你自己的本机配置, 勿提交到仓库）
qwen:
  model_custom: /path/to/Qwen3-TTS-12Hz-1.7B-CustomVoice
  model_base:   /path/to/Qwen3-TTS-12Hz-1.7B-Base
  speaker:      Uncle_Fu          # CustomVoice 内置音色名
  instruct:     语速中等，适合用来作为教学配音。
  language:     Chinese           # CustomVoice 默认 Chinese / 克隆默认 Auto
  ref_wav:      /path/to/ref.wav  # 提供后自动进入语音克隆模式
  ref_txt:      /path/to/ref.txt  # 参考音频文字稿（ICL 模式用）
  x_vector_only: false            # true 则只取说话人嵌入, 不需要 ref_txt
  device:       cuda:0
```

**基本用法**：

```bash
# 默认：CustomVoice 内置音色 Uncle_Fu + 教学风格指令
python tts_qwen.py
python tts_qwen.py --speaker serena --instruct "语速中等，适合用来作为教学配音。"

# 语音克隆（Base 模型, 传 --ref-wav 自动切换）
python tts_qwen.py --ref-wav /path/to/ref.wav --ref-txt /path/to/ref.txt

# 只合成某几页 / 跳过已生成文件
python tts_qwen.py --pages "1,3,5-9" --skip-existing
```

常用参数：`--speaker`（CustomVoice 9 音色: serena / vivian / uncle_fu / ryan / aiden /
ono_anna / sohee / eric / dylan）、`--instruct`（风格指令）、`--language`、
`--ref-wav/--ref-txt`（克隆模式）、`--x-vector-only`（仅说话人嵌入克隆，免文字稿）、
`--device`、`--max-new-tokens`、`--max-text-chars`（超长文本按句切分阈值，默认 500，0 关闭）。
