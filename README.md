# PDF2MOV

将 PDF 文件转换为可播放的视频文件。

## 依赖软件

 * ImageMagick

## 使用方法

 1. 将 PDF 文件放到当前目录
 1. 编辑讲稿文件 `trans.yaml`，逐页填写该页的朗读文本
 1. 修改 `config.yaml`，设置 `trans`（讲稿文件）、`audio_dir`（音频目录）、`pdf`（PDF 文件）及视频参数
 1. 在 `config.yaml` 中设置 `voice.engine` 及对应引擎的参数（讯飞 APPID / 本地 Qwen 模型路径等, 见下）
 1. 执行 `pdf2mov.py` 将 PDF 页面和音频整合为视频；缺少音频的页会自动调用 `voice.engine`
    指定的引擎补生成（也可先手动执行 `tts_xunfei.py` / `tts_qwen.py` / `tts_aliyun.py`）

## 讲稿文件 (`trans`)

逐页讲稿与其它设置分开存放在 YAML 文件中，由 `config.yaml` 的 `trans` 指定
（默认 `trans.yaml`）。`page` 为 PDF 页码（从 1 开始），`text` 为该页朗读文本：

```yaml
slides:
  - page: 1
    text: "你好"
  - page: 2
    text: "再见"
```

## config.yaml

```yaml
trans: trans.yaml   # 讲稿文件（可用 pdf2mov.py --trans 覆盖）
audio_dir: audio    # 音频目录，也是 pdf2mov.py 默认的音频输入目录
pdf: input.pdf      # PDF 文件（可用 pdf2mov.py --pdf 覆盖）

video:
  resolution: (1280, 720)
  fps: 24
  output: output.mp4
  silent_padding: 0.5
voice:
  engine: xunfei
  format: wav       # 音频扩展名，需与 TTS 输出一致

dictionary:         # 自定义词典（可选，见下）
  UNO: woono
```

## 自定义词典（控制发音）

TTS 常把缩写、专有名词读错。可在 `config.yaml` 的 `dictionary` 段自定义替换规则，
讲稿发送给 TTS 引擎之前会先按词典替换，从而控制发音。例如讲稿里写 `UNO`，
合成时按 `woono` 发音：

```yaml
dictionary:
  UNO: woono
  INO: "I N O"
```

- 对所有引擎（`qwen` / `xunfei` / `aliyun`）都生效；
- 区分大小写，按原词的**字面**匹配；
- 多个词条按**长词优先**依次替换，避免短词先命中长词的一部分；
- 只影响合成，讲稿文件（`trans`）内容不变（字幕等仍显示原文）。

## 音频缺失时自动配音

`pdf2mov.py` 启动时逐页检查 `audio_dir/{page}.{format}`，一旦有缺失，就调用 `voice.engine`
对应的配音脚本，只补生成缺失的页（已有音频不会重新生成）：

| voice.engine | 脚本 | 输出格式 |
| --- | --- | --- |
| `qwen` | `tts_qwen.py` | 由 `voice.format` 决定（默认 wav） |
| `xunfei` | `tts_xunfei.py` | 固定 wav |
| `aliyun` | `tts_aliyun.py` | 固定 mp3（`voice.format` 需设为 mp3） |

`pdf2mov.py` 会把 `--config`、`--trans`、`--audio-dir`、`--format`、`--pages`（缺失页）
转发给配音脚本，等价于：

```bash
python tts_qwen.py --config config.yaml --trans trans/trans.yaml \
    --audio-dir audio --format wav --pages 1,3-5
```

即使 `config.yaml` 里没有 `trans:` 键、讲稿只在命令行用 `pdf2mov.py --trans` 给出，
转发的也是已解析的讲稿路径，引擎不会再报“配置缺少讲稿”。

引擎执行失败、或未输出对应文件时，`pdf2mov.py` 会报错退出并提示缺失页，此时可先手动
运行上面的脚本排查。`voice.format` 必须与引擎输出一致，否则会提示“未生成第 N 页音频”。

## pdf2mov.py 命令行

所有参数都可在命令行指定，不依赖 `config.yaml` 也能一次完成转换：

```bash
# 全部参数由命令行给出
python pdf2mov.py --pdf input.pdf --trans trans.yaml --audio-dir audio -o output.mp4

# 只覆盖部分参数，其余读取 config.yaml
python pdf2mov.py -o output.mp4
```

常用参数：`--pdf`（PDF 文件）、`--audio-dir`（音频输入目录，默认取 `audio_dir`）、
`-o/--output`（输出视频文件名）、`--trans`（讲稿文件）、`--fps`、`--silent-padding`、
`--format`（音频扩展名，同时作为自动配音的输出格式）、`--density`（PDF 转图像 DPI，默认 300）。
未提供讲稿时，会按音频目录中的数字文件名自动推断页码顺序。

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
