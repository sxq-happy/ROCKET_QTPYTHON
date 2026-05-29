#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小火炬实验点火软件 - 打包脚本
使用PyInstaller将Python程序打包成exe文件
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def check_pyinstaller():
    """检查PyInstaller是否已安装"""
    try:
        import PyInstaller
        print("✅ PyInstaller已安装")
        return True
    except ImportError:
        print("❌ PyInstaller未安装，正在安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("✅ PyInstaller安装成功")
            return True
        except subprocess.CalledProcessError:
            print("❌ PyInstaller安装失败")
            return False

def clean_dist():
    """清理dist目录"""
    dist_path = Path("dist")
    if dist_path.exists():
        print("🧹 清理dist目录...")
        shutil.rmtree(dist_path)
    dist_path.mkdir(exist_ok=True)
    print("✅ dist目录已清理")

def build_exe():
    """构建exe文件"""
    print("🔨 开始构建exe文件...")
    
    # 使用用户安装的PyInstaller路径
    user_pyinstaller = os.path.expanduser("~/AppData/Roaming/Python/Python39/Scripts/pyinstaller.exe")
    if os.path.exists(user_pyinstaller):
        pyinstaller_cmd = user_pyinstaller
        print(f"使用用户安装的PyInstaller: {pyinstaller_cmd}")
    else:
        # 尝试其他可能的路径
        possible_paths = [
            os.path.expanduser("~/AppData/Roaming/Python/Python39/Scripts/pyinstaller.exe"),
            os.path.expanduser("~/AppData/Local/Programs/Python/Python39/Scripts/pyinstaller.exe"),
            "pyinstaller.exe"
        ]
        
        pyinstaller_cmd = None
        for path in possible_paths:
            if os.path.exists(path):
                pyinstaller_cmd = path
                print(f"找到PyInstaller: {pyinstaller_cmd}")
                break
        
        if pyinstaller_cmd is None:
            print("❌ 未找到PyInstaller可执行文件")
            return False
    
    # PyInstaller命令参数
    cmd = [pyinstaller_cmd]
    cmd.extend([
        "--onefile",                    # 打包成单个exe文件
        "--windowed",                   # 无控制台窗口
        "--name=喷注器实验软件",      # 指定exe文件名
        "--icon=logo_white.png",        # 设置图标
        "--add-data=logo_white.png;.",  # 添加资源文件
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtWidgets", 
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=cv2",
        "--hidden-import=serial",
        "--hidden-import=struct",
        "--hidden-import=datetime",
        "--hidden-import=time",
        "--hidden-import=threading",
        "--clean",                      # 清理临时文件
        "main.py"                       # 主程序文件
    ])
    
    try:
        # 执行PyInstaller命令
        print(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ exe文件构建成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ exe文件构建失败: {e}")
        print(f"错误输出: {e.stderr}")
        return False

def copy_docs():
    """复制文档到dist目录"""
    print("📚 复制文档文件...")
    
    docs = [
        "小火炬实验点火软件-使用说明书.md",
        "命令速查表.md", 
        "通信协议技术规格.md",
        "README.md",
        "紧急停止修复说明.md"
    ]
    
    for doc in docs:
        if os.path.exists(doc):
            shutil.copy2(doc, "dist/")
            print(f"✅ 已复制: {doc}")
        else:
            print(f"⚠️  文件不存在: {doc}")

def create_readme():
    """创建dist目录的README文件"""
    readme_content = """喷注器实验软件 V1.0

使用说明：
1. 双击"喷注器实验软件.exe"运行程序
2. 首次运行可能需要等待几秒钟
3. 如遇到问题，请查看相关文档

文档说明：
- 小火炬实验点火软件-使用说明书.md: 详细使用指南
- 命令速查表.md: 快速命令参考
- 通信协议技术规格.md: 技术实现细节
- README.md: 项目概述
- 紧急停止修复说明.md: 问题修复记录

技术支持：冕巢航天
版本：V1.0
更新日期：2024年12月
"""
    
    with open("dist/README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("✅ 已创建README.txt")

def main():
    """主函数"""
    print("=" * 50)
    print("喷注器实验软件 - 打包工具")
    print("=" * 50)
    
    # 检查PyInstaller
    if not check_pyinstaller():
        return False
    
    # 清理dist目录
    clean_dist()
    
    # 构建exe文件
    if not build_exe():
        return False
    
    # 复制文档
    copy_docs()
    
    # 创建README
    create_readme()
    
    print("=" * 50)
    print("🎉 打包完成！")
    print("📁 exe文件位置: dist/喷注器实验软件.exe")
    print("📚 文档文件已复制到dist目录")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1) 