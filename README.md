# Maona

自用 AI 桌面助手，支持接入 DeepSeek、GLM 等任意 OpenAI 兼容 API。

## 使用

从 [Releases](https://github.com/Maosna/Agent_maona/releases) 下载 `Maona-vX.X.X-win-x64.zip`，解压后双击 `Maona.exe`。

首次启动在设置里配好 API 地址和 Key 就能用了。

## 开发

**环境要求：** Node.js 22+ / Python 3.13+ / Windows 10/11

```bash
npm install
pip install -r backend/requirements.txt
npm start
```

打包：

```bash
npm run build
```

产物在 `dist/`。

## License

MIT
