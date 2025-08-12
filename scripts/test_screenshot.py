"""
简化的截图测试脚本 - 用于验证基本截图功能
"""

import time
import sys
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import requests

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent
REPORTS_DIR = ROOT_DIR / "reports"

def setup_chrome_driver():
    """设置Chrome驱动"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 无头模式
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--lang=zh-CN")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("✅ Chrome驱动启动成功")
        return driver
    except Exception as e:
        print(f"❌ Chrome驱动启动失败: {e}")
        return None

def check_service():
    """检查服务状态"""
    try:
        response = requests.get("http://127.0.0.1:8501", timeout=5)
        print(f"✅ Streamlit服务响应: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ Streamlit服务未响应: {e}")
        return False

def take_basic_screenshot(driver):
    """截取基本页面"""
    try:
        driver.get("http://127.0.0.1:8501")
        time.sleep(5)  # 等待页面加载
        
        screenshot_path = REPORTS_DIR / "test_screenshot.png"
        driver.save_screenshot(str(screenshot_path))
        print(f"✅ 测试截图已保存: {screenshot_path}")
        
        # 获取页面标题
        title = driver.title
        print(f"📄 页面标题: {title}")
        
        # 获取页面源码的前200个字符
        source_preview = driver.page_source[:200]
        print(f"📝 页面内容预览: {source_preview}...")
        
        return True
    except Exception as e:
        print(f"❌ 截图失败: {e}")
        return False

def main():
    """主函数"""
    print("🧪 开始截图功能测试...")
    
    # 确保reports目录存在
    REPORTS_DIR.mkdir(exist_ok=True)
    
    # 检查服务
    if not check_service():
        print("❌ 请先启动Streamlit服务: streamlit run apps/ui/app.py")
        return False
    
    # 设置驱动
    driver = setup_chrome_driver()
    if not driver:
        return False
    
    try:
        # 截图测试
        success = take_basic_screenshot(driver)
        return success
    finally:
        driver.quit()
        print("✅ Chrome驱动已关闭")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
