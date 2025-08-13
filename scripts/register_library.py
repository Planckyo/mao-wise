#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献库注册脚本 - 扫描PDF文件并生成manifest

用法:
    python scripts/register_library.py --library_dir /path/to/pdfs --output manifests/library_manifest.csv
"""

import argparse
import os
import sys
import pandas as pd
from pathlib import Path
from typing import List, Dict
import hashlib
from datetime import datetime

# 添加项目根目录到Python路径
REPO_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import setup_logger

def calculate_file_hash(file_path: str) -> str:
    """计算文件MD5哈希值"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return "unknown"

def scan_library(library_dir: str) -> List[Dict]:
    """
    扫描文献库目录，收集PDF文件信息
    
    Args:
        library_dir: 文献库根目录
        
    Returns:
        文件信息列表
    """
    logger = setup_logger(__name__)
    library_path = Path(library_dir)
    
    if not library_path.exists():
        raise ValueError(f"文献库目录不存在: {library_dir}")
    
    logger.info(f"开始扫描文献库: {library_dir}")
    
    files_info = []
    pdf_count = 0
    
    # 递归扫描PDF文件
    for pdf_file in library_path.rglob("*.pdf"):
        try:
            # 获取文件信息
            stat = pdf_file.stat()
            rel_path = pdf_file.relative_to(library_path)
            
            file_info = {
                "file_path": str(pdf_file.absolute()),
                "relative_path": str(rel_path),
                "filename": pdf_file.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "file_hash": calculate_file_hash(str(pdf_file)),
                "registered_at": datetime.now().isoformat()
            }
            
            files_info.append(file_info)
            pdf_count += 1
            
            if pdf_count % 100 == 0:
                logger.info(f"已扫描 {pdf_count} 个PDF文件...")
                
        except Exception as e:
            logger.warning(f"处理文件失败 {pdf_file}: {e}")
            continue
    
    logger.info(f"扫描完成，共发现 {pdf_count} 个PDF文件")
    return files_info

def export_manifest(files_info: List[Dict], output_path: str) -> None:
    """
    导出文件清单到CSV
    
    Args:
        files_info: 文件信息列表
        output_path: 输出CSV路径
    """
    logger = setup_logger(__name__)
    
    if not files_info:
        logger.warning("没有文件信息可导出")
        return
    
    # 创建输出目录
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 转换为DataFrame并导出
    df = pd.DataFrame(files_info)
    df.to_csv(output_path, index=False, encoding='utf-8')
    
    logger.info(f"文件清单已导出到: {output_path}")
    logger.info(f"总计 {len(df)} 个文件，总大小 {df['size_mb'].sum():.1f} MB")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="MAO-Wise 文献库注册工具",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "--library_dir",
        type=str,
        required=True,
        help="文献库根目录路径"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="输出manifest CSV文件路径"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logger(__name__)
    
    try:
        # 扫描文献库
        files_info = scan_library(args.library_dir)
        
        # 导出清单
        export_manifest(files_info, args.output)
        
        logger.info("文献库注册完成")
        
    except Exception as e:
        logger.error(f"文献库注册失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()