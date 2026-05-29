#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全启动版本的主程序
包含完整的异常处理和内存保护机制
"""

import sys
import os
import traceback
import logging
import signal
from datetime import datetime

# 设置异常处理
def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理器"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logging.critical(f"未捕获的异常: {error_msg}")
    print(f"程序发生严重错误: {exc_value}")
    print("详细错误信息已保存到日志文件")

# 设置全局异常处理器
sys.excepthook = handle_exception

def setup_logging():
    """设置日志系统"""
    os.makedirs('logs', exist_ok=True)
    
    log_filename = f'logs/safe_main_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return log_filename

def check_environment():
    """检查运行环境"""
    print("检查运行环境...")
    
    # 检查Python版本
    if sys.version_info < (3, 8):
        print("错误: 需要Python 3.8或更高版本")
        return False
    
    print(f"✓ Python版本: {sys.version}")
    
    # 检查必要的模块
    required_modules = {
        'PySide6': 'PySide6界面库',
        'serial': '串口通信库',
        'cv2': 'OpenCV视频处理库'
    }
    
    missing_modules = []
    for module, description in required_modules.items():
        try:
            __import__(module)
            print(f"✓ {description}")
        except ImportError:
            print(f"✗ {description} - 未安装")
            missing_modules.append(module)
    
    if missing_modules:
        print(f"\n缺少必要模块: {', '.join(missing_modules)}")
        print("请运行: pip install PySide6 pyserial opencv-python")
        return False
    
    return True

def setup_signal_handlers():
    """设置信号处理器"""
    def signal_handler(signum, frame):
        print(f"\n收到信号 {signum}，正在安全退出...")
        logging.info(f"收到信号 {signum}，开始清理资源")
        
        # 清理资源
        try:
            if 'app' in globals():
                app.quit()
        except:
            pass
        
        sys.exit(0)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

def create_application():
    """创建QApplication实例"""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        
        # 设置应用程序信息
        app.setApplicationName("小火炬实验点火软件")
        app.setApplicationVersion("1.1")
        app.setOrganizationName("冕巢航天")
        
        return app
        
    except Exception as e:
        logging.error(f"创建应用程序失败: {e}")
        return None

def create_main_window():
    """创建主窗口"""
    try:
        from main import RocketGroundStation
        
        window = RocketGroundStation()
        
        # 设置窗口属性
        window.setWindowTitle("小火炬实验点火软件 V1.1 (安全模式)")
        
        return window
        
    except Exception as e:
        logging.error(f"创建主窗口失败: {e}")
        traceback.print_exc()
        return None

def main():
    """主函数"""
    print("=" * 60)
    print("小火炬实验点火软件 V1.1 - 安全启动模式")
    print("=" * 60)
    
    # 设置日志
    log_filename = setup_logging()
    logging.info("程序启动")
    
    # 设置信号处理器
    setup_signal_handlers()
    
    # 检查环境
    if not check_environment():
        input("\n按回车键退出...")
        return 1
    
    # 创建应用程序
    print("\n创建应用程序...")
    app = create_application()
    if not app:
        print("创建应用程序失败")
        input("按回车键退出...")
        return 1
    
    # 创建主窗口
    print("创建主窗口...")
    window = create_main_window()
    if not window:
        print("创建主窗口失败")
        input("按回车键退出...")
        return 1
    
    try:
        # 显示窗口
        window.show()
        
        print("程序启动成功")
        print(f"日志文件: {log_filename}")
        print("如果程序出现问题，请检查日志文件")
        
        logging.info("程序界面显示成功，进入事件循环")
        
        # 运行事件循环
        result = app.exec()
        
        logging.info(f"程序正常退出，返回码: {result}")
        return result
        
    except Exception as e:
        error_msg = f"程序运行时发生错误: {e}"
        print(error_msg)
        logging.error(error_msg)
        traceback.print_exc()
        
        # 尝试清理资源
        try:
            if window:
                window.close()
            if app:
                app.quit()
        except:
            pass
        
        input("\n按回车键退出...")
        return 1
    
    finally:
        # 最终清理
        try:
            logging.info("程序结束，清理资源")
        except:
            pass

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"程序启动失败: {e}")
        traceback.print_exc()
        input("按回车键退出...")
        sys.exit(1)
