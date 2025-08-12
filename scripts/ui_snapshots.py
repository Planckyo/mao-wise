"""
UI自动截图脚本 - 使用Selenium自动截取Streamlit应用的关键页面
"""

import time
import os
import sys
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
    chrome_options.add_argument("--window-size=1920,1080")  # 设置窗口大小
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--lang=zh-CN")  # 设置中文
    
    try:
        # 使用webdriver-manager自动管理ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"Chrome驱动启动失败: {e}")
        print("请确保已安装Chrome浏览器")
        print("尝试手动安装ChromeDriver或检查网络连接")
        sys.exit(1)

def wait_for_streamlit_ready(driver, timeout=30):
    """等待Streamlit应用加载完成"""
    try:
        # 尝试多种Streamlit容器选择器
        selectors = [
            ".main .block-container",
            ".stApp",
            "[data-testid='stApp']",
            ".main",
            "div.main",
            "body"
        ]
        
        for selector in selectors:
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"✅ Streamlit应用已加载 (使用选择器: {selector})")
                return True
            except TimeoutException:
                continue
        
        # 如果所有选择器都失败，至少等待页面标题
        WebDriverWait(driver, timeout).until(
            lambda d: d.title and d.title != ""
        )
        print("✅ 页面已加载（基于标题）")
        return True
        
    except TimeoutException:
        print("❌ Streamlit应用加载超时")
        print(f"页面标题: {driver.title}")
        print(f"当前URL: {driver.current_url}")
        return False

def check_streamlit_service():
    """检查Streamlit服务是否运行"""
    try:
        response = requests.get("http://127.0.0.1:8501", timeout=5)
        if response.status_code == 200:
            print("✅ Streamlit服务正在运行")
            return True
        else:
            print(f"❌ Streamlit服务响应异常: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 无法连接到Streamlit服务: {e}")
        print("请确保运行了 start_services.ps1 或手动启动服务")
        return False

def take_screenshot(driver, filename, description):
    """截图并保存"""
    try:
        # 等待页面完全加载
        time.sleep(3)
        
        # 截图
        screenshot_path = REPORTS_DIR / filename
        driver.save_screenshot(str(screenshot_path))
        print(f"✅ {description} 截图已保存: {screenshot_path}")
        return True
    except Exception as e:
        print(f"❌ {description} 截图失败: {e}")
        return False

def click_element_safe(driver, selector, description):
    """安全地点击元素"""
    try:
        element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )
        driver.execute_script("arguments[0].click();", element)
        print(f"✅ 已点击: {description}")
        time.sleep(2)  # 等待UI更新
        return True
    except Exception as e:
        print(f"⚠️ 点击失败 {description}: {e}")
        return False

def expand_expander_safe(driver, text_content):
    """安全地展开折叠区域"""
    try:
        # 查找包含指定文本的展开器
        expanders = driver.find_elements(By.CSS_SELECTOR, "[data-testid='stExpander'] summary")
        for expander in expanders:
            if text_content in expander.text:
                if "true" not in expander.get_attribute("aria-expanded"):
                    driver.execute_script("arguments[0].click();", expander)
                    print(f"✅ 已展开折叠区域: {text_content}")
                    time.sleep(2)
                    return True
                else:
                    print(f"ℹ️ 折叠区域已展开: {text_content}")
                    return True
        
        print(f"⚠️ 未找到折叠区域: {text_content}")
        return False
    except Exception as e:
        print(f"⚠️ 展开折叠区域失败 {text_content}: {e}")
        return False

def navigate_to_page(driver, page_name):
    """导航到指定页面"""
    try:
        # 查找侧边栏中的页面链接
        sidebar_links = driver.find_elements(By.CSS_SELECTOR, ".sidebar .stSelectbox select option")
        for link in sidebar_links:
            if page_name in link.text:
                link.click()
                time.sleep(3)
                print(f"✅ 已导航到: {page_name}")
                return True
        
        # 尝试通过页面选择器导航
        try:
            page_selector = driver.find_element(By.CSS_SELECTOR, ".sidebar .stSelectbox select")
            options = page_selector.find_elements(By.TAG_NAME, "option")
            for option in options:
                if page_name in option.text:
                    option.click()
                    time.sleep(3)
                    print(f"✅ 已导航到: {page_name}")
                    return True
        except:
            pass
        
        print(f"⚠️ 未找到页面: {page_name}")
        return False
    except Exception as e:
        print(f"❌ 导航失败 {page_name}: {e}")
        return False

def capture_predict_page(driver):
    """截取预测页面"""
    print("\n📸 开始截取预测页面...")
    
    try:
        # 导航到预测页面
        driver.get("http://127.0.0.1:8501")
        
        # 等待页面加载，但不严格要求特定元素
        time.sleep(8)
        print("✅ 页面已加载，开始截图")
        
        # 尝试与页面交互（可选）
        try:
            # 查找输入框
            inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea")
            if inputs:
                sample_text = "AZ91镁合金基体；硅酸盐电解液：Na2SiO3 12 g/L, KOH 3 g/L"
                inputs[0].clear()
                inputs[0].send_keys(sample_text)
                print("✅ 已输入示例文本")
                time.sleep(2)
                
                # 查找按钮
                buttons = driver.find_elements(By.CSS_SELECTOR, "button")
                for button in buttons:
                    if button.is_displayed() and button.is_enabled():
                        try:
                            button.click()
                            print("✅ 已点击按钮")
                            time.sleep(3)
                            break
                        except:
                            continue
        except Exception as e:
            print(f"⚠️ 页面交互失败，继续截图: {e}")
        
        # 滚动到页面顶部
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        return take_screenshot(driver, "ui_predict.png", "预测页面")
        
    except Exception as e:
        print(f"❌ 预测页面截图失败: {e}")
        # 尝试基础截图
        try:
            return take_screenshot(driver, "ui_predict.png", "预测页面（基础版本）")
        except:
            return False

def capture_recommend_page(driver):
    """截取优化页面"""
    print("\n📸 开始截取优化页面...")
    
    try:
        # 导航到页面
        driver.get("http://127.0.0.1:8501")
        time.sleep(5)
        
        # 尝试切换到优化页面（如果有页面选择器）
        try:
            selects = driver.find_elements(By.CSS_SELECTOR, "select")
            for select in selects:
                options = select.find_elements(By.TAG_NAME, "option")
                for option in options:
                    if any(keyword in option.text.lower() for keyword in ['优化', '推荐', 'recommend']):
                        option.click()
                        time.sleep(3)
                        print("✅ 已切换到优化页面")
                        break
        except Exception as e:
            print(f"⚠️ 页面切换失败: {e}")
        
        # 尝试输入目标值
        try:
            number_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='number']")
            if len(number_inputs) >= 2:
                number_inputs[0].clear()
                number_inputs[0].send_keys("0.25")
                number_inputs[1].clear()
                number_inputs[1].send_keys("0.85")
                print("✅ 已设置目标值")
                time.sleep(2)
        except Exception as e:
            print(f"⚠️ 目标值设置失败: {e}")
        
        # 滚动到页面顶部
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        return take_screenshot(driver, "ui_recommend.png", "优化页面")
        
    except Exception as e:
        print(f"❌ 优化页面截图失败: {e}")
        try:
            return take_screenshot(driver, "ui_recommend.png", "优化页面（基础版本）")
        except:
            return False

def capture_expert_page(driver):
    """截取专家指导页面"""
    print("\n📸 开始截取专家指导页面...")
    
    try:
        # 导航到页面
        driver.get("http://127.0.0.1:8501")
        time.sleep(5)
        
        # 尝试切换到专家页面
        try:
            selects = driver.find_elements(By.CSS_SELECTOR, "select")
            for select in selects:
                options = select.find_elements(By.TAG_NAME, "option")
                for option in options:
                    if any(keyword in option.text.lower() for keyword in ['专家', '指导', 'expert', 'qa']):
                        option.click()
                        time.sleep(3)
                        print("✅ 已切换到专家页面")
                        break
        except Exception as e:
            print(f"⚠️ 页面切换失败: {e}")
        
        # 尝试输入问题
        try:
            text_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], textarea")
            if text_inputs:
                sample_question = "如何优化AZ91镁合金的微弧氧化工艺参数？"
                text_inputs[0].clear()
                text_inputs[0].send_keys(sample_question)
                print("✅ 已输入示例问题")
                time.sleep(2)
        except Exception as e:
            print(f"⚠️ 问题输入失败: {e}")
        
        # 滚动到页面顶部
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        return take_screenshot(driver, "ui_expert.png", "专家指导页面")
        
    except Exception as e:
        print(f"❌ 专家指导页面截图失败: {e}")
        try:
            return take_screenshot(driver, "ui_expert.png", "专家指导页面（基础版本）")
        except:
            return False

def main():
    """主函数"""
    print("🚀 开始UI自动截图...")
    
    # 确保reports目录存在
    REPORTS_DIR.mkdir(exist_ok=True)
    
    # 检查Streamlit服务
    if not check_streamlit_service():
        print("❌ 请先启动Streamlit服务")
        sys.exit(1)
    
    # 设置浏览器驱动
    driver = None
    try:
        driver = setup_chrome_driver()
        print("✅ Chrome驱动已启动")
        
        # 截取各个页面
        success_count = 0
        
        if capture_predict_page(driver):
            success_count += 1
        
        if capture_recommend_page(driver):
            success_count += 1
        
        if capture_expert_page(driver):
            success_count += 1
        
        print(f"\n📊 截图完成统计:")
        print(f"✅ 成功: {success_count}/3")
        print(f"📁 保存位置: {REPORTS_DIR}")
        
        # 列出生成的文件
        screenshots = list(REPORTS_DIR.glob("ui_*.png"))
        if screenshots:
            print(f"\n📸 生成的截图:")
            for screenshot in screenshots:
                size_mb = screenshot.stat().st_size / (1024 * 1024)
                print(f"  - {screenshot.name} ({size_mb:.1f} MB)")
        
        return success_count == 3
        
    except Exception as e:
        print(f"❌ 截图过程发生错误: {e}")
        return False
    
    finally:
        if driver:
            driver.quit()
            print("✅ Chrome驱动已关闭")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
