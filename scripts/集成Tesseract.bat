@echo off
:: 将本地 Tesseract OCR 复制到项目中
set SRC=F:\工具\tesseract-ocr
set DST=%~dp0tesseract

if not exist "%SRC%\tesseract.exe" (
  echo Tesseract 未安装在 %SRC%，请先安装
  pause
  exit /b 1
)

echo 从 %SRC% 复制到 %DST% ...
xcopy "%SRC%\*" "%DST%\" /E /I /Y /Q
echo 完成！Tesseract 已集成到项目中
pause
