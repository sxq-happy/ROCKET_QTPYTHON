@echo off
chcp 65001
echo ========================================
echo 小火炬实验点火软件 - 打包工具
echo ========================================

echo.
echo 正在检查Python环境...
python --version
if errorlevel 1 (
    echo 错误：未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

echo.
echo 正在安装依赖包...
pip install -r requirements.txt
if errorlevel 1 (
    echo 错误：依赖包安装失败
    pause
    exit /b 1
)

echo.
echo 正在打包exe文件...
python build_exe.py
if errorlevel 1 (
    echo 错误：打包失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 打包完成！
echo exe文件位置：dist\小火炬实验点火软件.exe
echo ========================================
pause 