#!/usr/bin/env python3
"""
快速自检脚本 - 验证maowise包导入
"""

import sys
import pathlib

# 确保能找到maowise包 - 添加项目根目录到sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def main():
    """验证maowise包导入"""
    print("=" * 50)
    print("MAO-Wise 包导入验证")
    print("=" * 50)
    
    # 显示当前工作目录
    current_dir = pathlib.Path().resolve()
    print(f"当前工作目录: {current_dir}")
    
    # 显示Python路径
    print(f"Python路径:")
    for i, path in enumerate(sys.path):
        print(f"  [{i}] {path}")
    
    # 显示Python版本
    print(f"Python版本: {sys.version}")
    
    print("\n" + "=" * 50)
    print("开始导入测试...")
    print("=" * 50)
    
    try:
        # 测试导入maowise主包
        print("1. 测试导入 maowise...")
        import maowise
        import inspect
        maowise_path = inspect.getfile(maowise)
        print(f"   ✅ OK maowise at: {maowise_path}")
        
        # 测试导入核心模块
        print("2. 测试导入核心模块...")
        
        # 配置模块
        try:
            from maowise.config import load_config
            print("   ✅ maowise.config - OK")
        except Exception as e:
            print(f"   ❌ maowise.config - FAILED: {e}")
        
        # 工具模块
        try:
            from maowise.utils.logger import logger
            from maowise.utils.config import load_config
            print("   ✅ maowise.utils - OK")
        except Exception as e:
            print(f"   ❌ maowise.utils - FAILED: {e}")
        
        # API模式
        try:
            from maowise.api_schemas import PredictIn, PredictOut
            print("   ✅ maowise.api_schemas - OK")
        except Exception as e:
            print(f"   ❌ maowise.api_schemas - FAILED: {e}")
        
        # 数据流模块
        try:
            from maowise.dataflow.ingest import main as ingest_main
            print("   ✅ maowise.dataflow - OK")
        except Exception as e:
            print(f"   ❌ maowise.dataflow - FAILED: {e}")
        
        # 知识库模块
        try:
            from maowise.kb.search import kb_search
            print("   ✅ maowise.kb - OK")
        except Exception as e:
            print(f"   ❌ maowise.kb - FAILED: {e}")
        
        # 模型模块
        try:
            from maowise.models.infer_fwd import predict_performance
            print("   ✅ maowise.models - OK")
        except Exception as e:
            print(f"   ❌ maowise.models - FAILED: {e}")
        
        # 优化模块
        try:
            from maowise.optimize.engines import recommend_solutions
            print("   ✅ maowise.optimize - OK")
        except Exception as e:
            print(f"   ❌ maowise.optimize - FAILED: {e}")
        
        # LLM模块
        try:
            from maowise.llm.client import llm_chat
            print("   ✅ maowise.llm - OK")
        except Exception as e:
            print(f"   ❌ maowise.llm - FAILED: {e}")
        
        # 专家系统模块
        try:
            from maowise.experts.clarify import generate_clarify_questions
            print("   ✅ maowise.experts - OK")
        except Exception as e:
            print(f"   ❌ maowise.experts - FAILED: {e}")
        
        print("\n" + "=" * 50)
        print("✅ 所有核心模块导入成功!")
        print("=" * 50)
        
        # 显示包信息
        print(f"\n包信息:")
        print(f"  - maowise包位置: {maowise_path}")
        print(f"  - 包目录: {pathlib.Path(maowise_path).parent}")
        
        # 检查是否为开发安装
        try:
            import pkg_resources
            try:
                dist = pkg_resources.get_distribution('maowise')
                print(f"  - 已安装版本: {dist.version}")
                print(f"  - 安装位置: {dist.location}")
                print(f"  - 开发模式: {'是' if dist.location.endswith('.egg-link') else '否'}")
            except pkg_resources.DistributionNotFound:
                print("  - 未通过pip安装（使用sys.path导入）")
        except ImportError:
            print("  - pkg_resources不可用")
        
        return True
        
    except Exception as e:
        print(f"\n❌ IMPORT_ERROR: {e}")
        print(f"错误类型: {type(e).__name__}")
        
        # 提供调试信息
        print("\n调试信息:")
        print("请检查以下可能的问题:")
        print("1. 确保在项目根目录运行此脚本")
        print("2. 确保maowise目录存在且包含__init__.py")
        print("3. 检查PYTHONPATH环境变量设置")
        print("4. 考虑运行: pip install -e .")
        
        raise

def check_repo_structure():
    """检查仓库结构"""
    print("\n" + "=" * 50)
    print("检查仓库结构...")
    print("=" * 50)
    
    current_dir = pathlib.Path().resolve()
    
    # 检查关键目录和文件
    required_paths = [
        "maowise/__init__.py",
        "maowise/config/__init__.py", 
        "maowise/utils/__init__.py",
        "maowise/api_schemas/__init__.py",
        "maowise/dataflow/__init__.py",
        "maowise/kb/__init__.py",
        "maowise/models/__init__.py",
        "maowise/optimize/__init__.py",
        "maowise/llm/__init__.py",
        "maowise/experts/__init__.py",
        "apps/api/main.py",
        "apps/ui/app.py"
    ]
    
    missing_files = []
    
    for path_str in required_paths:
        path = current_dir / path_str
        if path.exists():
            print(f"   ✅ {path_str}")
        else:
            print(f"   ❌ {path_str} - 缺失")
            missing_files.append(path_str)
    
    if missing_files:
        print(f"\n⚠️ 发现 {len(missing_files)} 个缺失文件:")
        for file in missing_files:
            print(f"   - {file}")
        return False
    else:
        print(f"\n✅ 所有必要文件都存在")
        return True

if __name__ == "__main__":
    print("MAO-Wise 包导入验证工具")
    print("=" * 50)
    
    # 检查仓库结构
    structure_ok = check_repo_structure()
    
    if structure_ok:
        # 执行导入测试
        import_ok = main()
        
        if import_ok:
            print("\n🎉 验证完成 - 所有测试通过!")
            sys.exit(0)
        else:
            print("\n💥 验证失败 - 导入测试未通过")
            sys.exit(1)
    else:
        print("\n💥 验证失败 - 仓库结构不完整")
        sys.exit(1)
