#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理打包过程中产生的无用文件
只保留必要的源代码和生成的exe文件
"""

import os
import shutil
import glob

def cleanup_build_files():
    """清理构建相关文件"""
    print("清理构建文件...")
    
    # 要删除的目录
    dirs_to_remove = [
        'build',           # PyInstaller构建临时目录
        '__pycache__',     # Python缓存目录
        '.pytest_cache',   # pytest缓存
        'logs',           # 日志文件（如果不需要的话）
    ]
    
    removed_dirs = []
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                removed_dirs.append(dir_name)
                print(f"✅ 已删除目录: {dir_name}")
            except Exception as e:
                print(f"❌ 删除目录失败 {dir_name}: {e}")
    
    return removed_dirs

def cleanup_spec_files():
    """清理spec文件"""
    print("清理spec文件...")
    
    spec_files = glob.glob("*.spec")
    removed_files = []
    
    for spec_file in spec_files:
        try:
            os.remove(spec_file)
            removed_files.append(spec_file)
            print(f"✅ 已删除spec文件: {spec_file}")
        except Exception as e:
            print(f"❌ 删除spec文件失败 {spec_file}: {e}")
    
    return removed_files

def cleanup_temp_files():
    """清理临时文件"""
    print("清理临时文件...")
    
    # 要删除的文件模式
    file_patterns = [
        "*.pyc",           # Python编译文件
        "*.pyo",           # Python优化文件
        "*.pyd",           # Python动态库
        "*~",              # 备份文件
        "*.tmp",           # 临时文件
        "*.log",           # 日志文件（在根目录的）
        "version_info.txt", # 版本信息文件
        "test_report.md",   # 测试报告
    ]
    
    removed_files = []
    for pattern in file_patterns:
        files = glob.glob(pattern)
        for file in files:
            try:
                os.remove(file)
                removed_files.append(file)
                print(f"✅ 已删除文件: {file}")
            except Exception as e:
                print(f"❌ 删除文件失败 {file}: {e}")
    
    return removed_files

def cleanup_build_scripts():
    """清理打包脚本（可选）"""
    print("清理打包脚本...")
    
    # 打包相关的脚本文件（如果不再需要的话）
    build_scripts = [
        'build_exe.py',
        'simple_build.py',
        'quick_build.py',
        'create_icon.py',
        'test_build.py',
        'memory_diagnostic.py',
        'test_command_fix.py',
        'test_motor_fix.py',
        'test_serial_fix.py',
        'fix_crash_issue.py',
        'quick_fix.py',
        'find_exe.py',
    ]
    
    # 批处理文件
    batch_files = [
        'build_exe.bat',
        'build_program.bat',
        'build_simple.bat',
        'install_pyinstaller.bat',
        'find_exe.bat',
        '打包程序.bat',
        '一键打包.bat',
        '安全启动.bat',
    ]
    
    # 文档文件
    doc_files = [
        'requirements_build.txt',
        '打包说明.md',
        '打包故障排除.md',
        '修复总结.md',
        '电机控制修复总结.md',
        '指令发送修复说明.md',
        '故障排除指南.md',
    ]
    
    all_files = build_scripts + batch_files + doc_files
    
    print("以下文件可以删除（打包脚本和文档）:")
    for i, file in enumerate(all_files, 1):
        if os.path.exists(file):
            file_size = os.path.getsize(file) / 1024  # KB
            print(f"  {i:2d}. {file} ({file_size:.1f} KB)")
    
    print("\n是否删除这些文件？")
    print("1. 全部删除")
    print("2. 保留所有")
    print("3. 选择性删除")
    
    try:
        choice = input("请选择 (1/2/3): ").strip()
        
        removed_files = []
        if choice == "1":
            # 全部删除
            for file in all_files:
                if os.path.exists(file):
                    try:
                        os.remove(file)
                        removed_files.append(file)
                        print(f"✅ 已删除: {file}")
                    except Exception as e:
                        print(f"❌ 删除失败 {file}: {e}")
        
        elif choice == "3":
            # 选择性删除
            print("\n输入要删除的文件编号（用空格分隔，如: 1 3 5）:")
            indices_input = input("编号: ").strip()
            if indices_input:
                try:
                    indices = [int(x) - 1 for x in indices_input.split()]
                    for i in indices:
                        if 0 <= i < len(all_files):
                            file = all_files[i]
                            if os.path.exists(file):
                                try:
                                    os.remove(file)
                                    removed_files.append(file)
                                    print(f"✅ 已删除: {file}")
                                except Exception as e:
                                    print(f"❌ 删除失败 {file}: {e}")
                except ValueError:
                    print("❌ 输入格式错误")
        
        return removed_files
        
    except KeyboardInterrupt:
        print("\n用户取消操作")
        return []

def show_remaining_files():
    """显示保留的文件"""
    print("\n保留的重要文件:")
    
    # 核心程序文件
    core_files = [
        'main.py',
        'serial_components.py',
        'control_components.py',
        'video_components.py',
    ]
    
    # 生成的文件
    generated_files = [
        'dist/小火炬实验点火软件.exe',
        'dist/使用说明.txt',
        'dist/README.txt',
    ]
    
    print("\n核心程序文件:")
    for file in core_files:
        if os.path.exists(file):
            file_size = os.path.getsize(file) / 1024  # KB
            print(f"  📄 {file} ({file_size:.1f} KB)")
    
    print("\n生成的可执行文件:")
    for file in generated_files:
        if os.path.exists(file):
            file_size = os.path.getsize(file) / (1024 * 1024)  # MB
            print(f"  🎯 {file} ({file_size:.1f} MB)")
    
    # 检查dist目录大小
    if os.path.exists('dist'):
        total_size = 0
        for root, dirs, files in os.walk('dist'):
            for file in files:
                file_path = os.path.join(root, file)
                total_size += os.path.getsize(file_path)
        
        print(f"\ndist目录总大小: {total_size / (1024 * 1024):.1f} MB")

def main():
    """主函数"""
    print("=" * 60)
    print("清理打包文件工具")
    print("=" * 60)
    print()
    
    print("这个工具将清理打包过程中产生的无用文件")
    print("保留核心源代码和生成的exe文件")
    print()
    
    try:
        # 1. 清理构建文件
        removed_dirs = cleanup_build_files()
        print()
        
        # 2. 清理spec文件
        removed_specs = cleanup_spec_files()
        print()
        
        # 3. 清理临时文件
        removed_temps = cleanup_temp_files()
        print()
        
        # 4. 清理打包脚本（可选）
        removed_scripts = cleanup_build_scripts()
        print()
        
        # 5. 显示保留的文件
        show_remaining_files()
        
        # 总结
        print("\n" + "=" * 60)
        print("清理完成!")
        print("=" * 60)
        
        total_removed = len(removed_dirs) + len(removed_specs) + len(removed_temps) + len(removed_scripts)
        print(f"共删除 {total_removed} 个文件/目录")
        
        if removed_dirs:
            print(f"删除目录: {', '.join(removed_dirs)}")
        if removed_specs:
            print(f"删除spec文件: {', '.join(removed_specs)}")
        if removed_temps:
            print(f"删除临时文件: {len(removed_temps)} 个")
        if removed_scripts:
            print(f"删除脚本文件: {len(removed_scripts)} 个")
        
        print("\n现在您的目录更加整洁了！")
        print("重要文件都已保留，可以正常使用程序。")
        
    except Exception as e:
        print(f"❌ 清理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
    input("\n按回车键退出...")
