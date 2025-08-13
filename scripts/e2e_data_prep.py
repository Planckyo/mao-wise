#!/usr/bin/env python3
"""
端到端测试数据准备脚本
确保有足够的数据用于RAG和测试
"""

import sys
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maowise.utils.config import load_config
from maowise.utils.logger import logger


def check_corpus_availability():
    """检查语料库可用性"""
    corpus_path = Path("datasets/data_parsed/corpus.jsonl")
    min_corpus_path = Path("tests/fixtures/min_corpus.jsonl")
    
    logger.info("检查语料库数据...")
    
    # 检查主语料库
    if corpus_path.exists():
        with open(corpus_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        line_count = len([line for line in lines if line.strip()])
        logger.info(f"主语料库存在，包含 {line_count} 条记录")
        
        # 如果记录数量足够（>=2条），使用主语料库
        if line_count >= 2:
            logger.info("✅ 主语料库数据充足，使用现有数据")
            return True, "main_corpus", line_count
        else:
            logger.warning(f"主语料库记录数量不足（{line_count} < 2）")
    else:
        logger.warning("主语料库不存在")
    
    # 检查最小夹具
    if min_corpus_path.exists():
        # 验证最小夹具的条目数
        with open(min_corpus_path, 'r', encoding='utf-8') as f:
            min_lines = f.readlines()
        min_count = len([line for line in min_lines if line.strip()])
        logger.info(f"发现最小数据夹具，包含 {min_count} 条记录")
        logger.warning("⚠️  使用最小语料夹具作为兜底（适合测试，实际使用请提供更多文献数据）")
        return False, "min_fixture", min_count
    else:
        logger.error("最小数据夹具也不存在！")
        return False, "none", 0


def prepare_corpus_data():
    """准备语料库数据"""
    is_sufficient, source_type, count = check_corpus_availability()
    
    if source_type == "main_corpus":
        logger.info("使用现有主语料库")
        return True
    
    elif source_type == "min_fixture":
        # 复制最小夹具到主语料库位置
        corpus_path = Path("datasets/data_parsed/corpus.jsonl")
        min_corpus_path = Path("tests/fixtures/min_corpus.jsonl")
        
        # 确保目录存在
        corpus_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 复制文件
        shutil.copy2(min_corpus_path, corpus_path)
        logger.info(f"✅ 已复制最小数据夹具到 {corpus_path}")
        logger.warning("📝 当前使用最小测试数据，实际生产环境建议提供更多高质量文献数据")
        
        # 验证复制结果
        if corpus_path.exists():
            with open(corpus_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            line_count = len([line for line in lines if line.strip()])
            logger.info(f"语料库准备完成，包含 {line_count} 条记录（silicate/zirconate体系各有典型案例）")
            return True
        else:
            logger.error("语料库复制失败")
            return False
    
    else:
        logger.error("无法准备语料库数据")
        return False


def prepare_knowledge_base():
    """准备知识库索引"""
    logger.info("检查知识库索引...")
    
    index_dir = Path("datasets/index_store")
    
    if index_dir.exists() and any(index_dir.iterdir()):
        logger.info("✅ 知识库索引已存在")
        return True
    
    logger.info("知识库索引不存在，尝试构建...")
    
    try:
        from maowise.kb.build_index import build_index
        
        # 构建知识库索引
        build_index()
        
        # 验证构建结果
        if index_dir.exists() and any(index_dir.iterdir()):
            logger.info("✅ 知识库索引构建完成")
            return True
        else:
            logger.warning("知识库索引构建可能失败，但继续进行测试")
            return False
            
    except Exception as e:
        logger.warning(f"知识库索引构建失败: {e}")
        logger.info("将使用离线兜底模式进行测试")
        return False


def prepare_database():
    """准备数据库"""
    logger.info("检查数据库...")
    
    db_path = Path("conversations.sqlite")
    
    if db_path.exists():
        logger.info("✅ 数据库已存在")
        return True
    
    logger.info("数据库不存在，将在首次使用时自动创建")
    return True


def check_environment():
    """检查环境配置"""
    logger.info("检查环境配置...")
    
    import os
    
    env_status = {
        "OPENAI_API_KEY": "已设置" if os.getenv("OPENAI_API_KEY") else "未设置",
        "MAOWISE_LIBRARY_DIR": "已设置" if os.getenv("MAOWISE_LIBRARY_DIR") else "未设置",
        "DEBUG_LLM": os.getenv("DEBUG_LLM", "false"),
    }
    
    logger.info("环境变量状态:")
    for key, status in env_status.items():
        logger.info(f"  {key}: {status}")
    
    # 检查配置文件
    try:
        config = load_config()
        logger.info("✅ 配置文件加载成功")
        
        # 检查LLM配置
        llm_provider = config.get("llm", {}).get("provider", "local")
        logger.info(f"LLM提供商: {llm_provider}")
        
        if llm_provider == "local" or not os.getenv("OPENAI_API_KEY"):
            logger.info("将使用离线兜底模式")
        
        return True
        
    except Exception as e:
        logger.error(f"配置文件加载失败: {e}")
        return False


def create_reports_directory():
    """创建报告目录"""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    logger.info(f"✅ 报告目录准备完成: {reports_dir}")
    return True


def main():
    """主函数"""
    logger.info("🚀 开始端到端测试数据准备")
    logger.info("="*60)
    
    steps = [
        ("环境配置检查", check_environment),
        ("语料库数据准备", prepare_corpus_data),
        ("知识库索引准备", prepare_knowledge_base),
        ("数据库准备", prepare_database),
        ("报告目录创建", create_reports_directory),
    ]
    
    results = {}
    
    for step_name, step_func in steps:
        logger.info(f"\n📋 {step_name}...")
        try:
            results[step_name] = step_func()
        except Exception as e:
            logger.error(f"步骤失败: {e}")
            results[step_name] = False
    
    logger.info("\n" + "="*60)
    logger.info("📊 数据准备结果汇总")
    logger.info("="*60)
    
    success_count = 0
    total_count = len(steps)
    
    for step_name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        logger.info(f"{step_name:20} : {status}")
        if success:
            success_count += 1
    
    logger.info(f"\n总计: {success_count}/{total_count} 步骤成功")
    
    if success_count >= total_count - 1:  # 允许1个步骤失败
        logger.info("\n🎉 数据准备完成！可以开始端到端测试")
        
        logger.info("\n📋 准备就绪的组件:")
        if results.get("语料库数据准备"):
            logger.info("• 语料库数据 ✅")
        if results.get("知识库索引准备"):
            logger.info("• 知识库索引 ✅")
        else:
            logger.info("• 知识库索引 ❌ (将使用离线模式)")
        if results.get("数据库准备"):
            logger.info("• 数据库 ✅")
        if results.get("报告目录创建"):
            logger.info("• 报告目录 ✅")
        
        logger.info("\n🔧 测试模式:")
        import os
        if os.getenv("OPENAI_API_KEY"):
            logger.info("• LLM模式: 在线 (OpenAI)")
        else:
            logger.info("• LLM模式: 离线兜底")
        
        return True
    else:
        logger.error(f"\n❌ 数据准备失败，{total_count - success_count} 个关键步骤未完成")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
