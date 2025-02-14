# PDF2MOV

将 PDF 文件转换为可播放的视频文件。

## 依赖软件

 * ImageMagick

## 使用方法

 1. 将 PDF 讲稿放到当前目录
 1. 修改 `config.yaml` 文件，设置文件输入输出目录
 1. 完善每一页的文字讲稿
 1. 设置讯飞 APPID 等信息
 1. 执行 `tts_xunfei.py` 生成讲稿音频
 1. 执行 `pdf2mov.py` 将 PDF 页面和音频整合为视频文件
