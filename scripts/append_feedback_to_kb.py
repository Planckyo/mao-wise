#!/usr/bin/env python3
"""
增量向量库更新脚本
将实验反馈数据追加到现有知识库中，无需重建
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional, Set

import pandas as pd
import numpy as np

# 确保能找到maowise包
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    EMBED_AVAILABLE = True
except ImportError:
    EMBED_AVAILABLE = False

logger = logging.getLogger(__name__)


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


class FeedbackVectorUpdater:
    """实验反馈向量库更新器"""
    
    def __init__(self, index_dir: Path, min_delta: int = 1):
        self.index_dir = Path(index_dir)
        self.min_delta = min_delta
        
        # 核心文件路径
        self.faiss_path = self.index_dir / "index.faiss"
        self.numpy_path = self.index_dir / "embeddings.npy"
        self.idmap_path = self.index_dir / "idmap.csv"
        self.meta_path = self.index_dir / "meta.json"
        self.corpus_path = REPO_ROOT / "datasets" / "data_parsed" / "corpus.jsonl"
        
        # 状态变量
        self.meta_info = None
        self.existing_ids = set()
        self.embed_model = None
        self.index = None
        self.embeddings = None
        self.backend = None
    
    def load_meta_info(self) -> bool:
        """加载索引元信息"""
        if not self.meta_path.exists():
            logger.error(f"元信息文件不存在: {self.meta_path}")
            return False
        
        try:
            with open(self.meta_path, 'r', encoding='utf-8') as f:
                self.meta_info = json.load(f)
            
            logger.info(f"已加载元信息: model={self.meta_info.get('embed_model')}, "
                       f"dim={self.meta_info.get('dim')}, backend={self.meta_info.get('backend')}")
            return True
            
        except Exception as e:
            logger.error(f"加载元信息失败: {e}")
            return False
    
    def load_existing_ids(self) -> bool:
        """加载现有向量ID集合"""
        if not self.idmap_path.exists():
            logger.info("ID映射文件不存在，将创建新文件")
            self.existing_ids = set()
            return True
        
        try:
            df_idmap = pd.read_csv(self.idmap_path)
            if 'id' in df_idmap.columns:
                self.existing_ids = set(df_idmap['id'].tolist())
                logger.info(f"已加载 {len(self.existing_ids)} 个现有向量ID")
            else:
                logger.warning("ID映射文件缺少id列，将创建新映射")
                self.existing_ids = set()
            return True
            
        except Exception as e:
            logger.error(f"加载现有ID失败: {e}")
            return False
    
    def load_embedding_model(self) -> bool:
        """加载嵌入模型"""
        if not EMBED_AVAILABLE:
            logger.error("sentence-transformers不可用，请安装: pip install sentence-transformers")
            return False
        
        model_name = self.meta_info.get('embed_model', 'BAAI/bge-m3')
        
        try:
            logger.info(f"正在加载嵌入模型: {model_name}")
            self.embed_model = SentenceTransformer(model_name)
            
            # 验证维度一致性
            test_embedding = self.embed_model.encode(["test"], normalize_embeddings=True)
            actual_dim = test_embedding.shape[1]
            expected_dim = self.meta_info.get('dim')
            
            if expected_dim and actual_dim != expected_dim:
                logger.error(f"维度不匹配: 期望{expected_dim}, 实际{actual_dim} - 需要重建索引")
                return False
            
            logger.info(f"嵌入模型加载成功，维度: {actual_dim}")
            return True
            
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {e}")
            return False
    
    def load_vector_backend(self) -> bool:
        """加载向量后端（FAISS或NumPy）"""
        backend = self.meta_info.get('backend', 'faiss')
        
        if backend == 'faiss' and FAISS_AVAILABLE and self.faiss_path.exists():
            try:
                self.index = faiss.read_index(str(self.faiss_path))
                self.backend = 'faiss'
                logger.info(f"FAISS索引加载成功，现有向量数: {self.index.ntotal}")
                return True
            except Exception as e:
                logger.warning(f"FAISS索引加载失败: {e}, 尝试NumPy后端")
        
        # 回退到NumPy后端
        if self.numpy_path.exists():
            try:
                self.embeddings = np.load(self.numpy_path)
                self.backend = 'numpy'
                logger.info(f"NumPy向量加载成功，现有向量数: {self.embeddings.shape[0]}")
                return True
            except Exception as e:
                logger.error(f"NumPy向量加载失败: {e}")
                return False
        
        # 如果都不存在，创建新的空向量集
        if backend == 'faiss' and FAISS_AVAILABLE:
            dim = self.meta_info.get('dim', 1024)
            self.index = faiss.IndexFlatIP(dim)  # 使用内积索引
            self.backend = 'faiss'
            logger.info(f"创建新FAISS索引，维度: {dim}")
        else:
            self.embeddings = np.empty((0, self.meta_info.get('dim', 1024)), dtype=np.float32)
            self.backend = 'numpy'
            logger.info(f"创建新NumPy向量集，维度: {self.meta_info.get('dim', 1024)}")
        
        return True
    
    def get_current_vector_count(self) -> int:
        """获取当前向量数量"""
        if self.backend == 'faiss':
            return self.index.ntotal
        elif self.backend == 'numpy':
            return self.embeddings.shape[0]
        else:
            return 0
    
    def load_feedback_data(self, experiments_path: Path) -> pd.DataFrame:
        """加载实验反馈数据"""
        if not experiments_path.exists():
            logger.error(f"实验数据文件不存在: {experiments_path}")
            return pd.DataFrame()
        
        try:
            df = pd.read_parquet(experiments_path)
            logger.info(f"已加载实验数据: {len(df)} 条记录")
            
            # 筛选lab_feedback记录
            if 'source' in df.columns:
                feedback_mask = df['source'].str.contains('lab_feedback', na=False)
                df_feedback = df[feedback_mask].copy()
                logger.info(f"找到 {len(df_feedback)} 条lab_feedback记录")
            else:
                logger.warning("数据中缺少source列，无法筛选lab_feedback")
                df_feedback = df.copy()
            
            return df_feedback
            
        except Exception as e:
            logger.error(f"加载实验数据失败: {e}")
            return pd.DataFrame()
    
    def generate_document_id(self, row: pd.Series) -> str:
        """生成稳定的文档ID"""
        # 提取关键字段，处理缺失值
        batch_id = str(row.get('batch_id', ''))
        if not batch_id or batch_id == 'nan':
            # 如果没有batch_id，使用source或日期
            source = str(row.get('source', ''))
            if 'lab_feedback_' in source:
                batch_id = source
            else:
                batch_id = f"lab_feedback_{datetime.now().strftime('%Y%m%d')}"
        
        system = str(row.get('system', 'unknown'))
        step = str(row.get('step', 'single'))
        time_min = f"{row.get('time_min', row.get('oxidation_time_min', 0)):.1f}"
        thickness = f"{row.get('thickness_um', 0):.1f}"
        alpha = f"{row.get('measured_alpha', row.get('alpha', 0)):.3f}"
        epsilon = f"{row.get('measured_epsilon', row.get('epsilon', 0)):.3f}"
        
        doc_id = f"lab:{batch_id}:{system}:{step}:{time_min}:{thickness}:{alpha}:{epsilon}"
        return doc_id
    
    def generate_rag_text(self, row: pd.Series) -> str:
        """生成RAG友好的文本片段"""
        # 提取日期
        source = str(row.get('source', ''))
        if 'lab_feedback_' in source:
            date = source.replace('lab_feedback_', '')[:8]
        else:
            date = datetime.now().strftime('%Y%m%d')
        
        # 提取核心参数
        system = str(row.get('system', 'unknown'))
        step = str(row.get('step', 'single'))
        time_min = row.get('time_min', row.get('oxidation_time_min', 0))
        thickness = row.get('thickness_um', 0)
        alpha = row.get('measured_alpha', row.get('alpha', 0))
        epsilon = row.get('measured_epsilon', row.get('epsilon', 0))
        
        # 工艺参数
        mode = str(row.get('mode', 'CC'))
        current = row.get('current_density_Adm2', row.get('current_A', 0))
        frequency = row.get('frequency_Hz', 0)
        duty = row.get('duty_cycle_pct', row.get('duty_percent', 0))
        
        # 备注
        notes = str(row.get('notes', '')).strip()
        if not notes or notes == 'nan':
            notes = 'NA'
        
        # 生成文本
        text = (f"[LAB-FEEDBACK-{date}] system={system}; step={step}; "
               f"t={time_min:.1f}min; thickness={thickness:.1f}um; "
               f"alpha={alpha:.3f}; epsilon={epsilon:.3f}; "
               f"params: mode={mode}, current={current:.1f}A, "
               f"freq={frequency:.0f}Hz, duty={duty:.1f}%; notes={notes}")
        
        return text
    
    def filter_new_records(self, df_feedback: pd.DataFrame) -> Tuple[List[str], List[str]]:
        """筛选出尚未入库的记录"""
        new_ids = []
        new_texts = []
        
        for idx, row in df_feedback.iterrows():
            doc_id = self.generate_document_id(row)
            
            if doc_id not in self.existing_ids:
                text = self.generate_rag_text(row)
                new_ids.append(doc_id)
                new_texts.append(text)
        
        logger.info(f"筛选出 {len(new_ids)} 条新记录待追加")
        return new_ids, new_texts
    
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """批量嵌入文本"""
        if not texts:
            return np.empty((0, self.meta_info.get('dim', 1024)), dtype=np.float32)
        
        normalize = self.meta_info.get('normalize_embeddings', True)
        
        try:
            logger.info(f"正在嵌入 {len(texts)} 条文本...")
            embeddings = self.embed_model.encode(
                texts,
                batch_size=32,
                show_progress_bar=True,
                normalize_embeddings=normalize
            ).astype(np.float32)
            
            logger.info(f"嵌入完成，形状: {embeddings.shape}")
            return embeddings
            
        except Exception as e:
            logger.error(f"文本嵌入失败: {e}")
            return np.empty((0, self.meta_info.get('dim', 1024)), dtype=np.float32)
    
    def append_vectors(self, new_embeddings: np.ndarray, new_ids: List[str]) -> bool:
        """追加新向量到后端"""
        if len(new_embeddings) == 0:
            logger.info("无新向量需要追加")
            return True
        
        old_count = self.get_current_vector_count()
        
        try:
            if self.backend == 'faiss':
                # FAISS后端
                self.index.add(new_embeddings)
                faiss.write_index(self.index, str(self.faiss_path))
                logger.info(f"FAISS索引已更新: {old_count} -> {self.index.ntotal}")
                
            elif self.backend == 'numpy':
                # NumPy后端
                if self.embeddings.shape[0] == 0:
                    self.embeddings = new_embeddings
                else:
                    self.embeddings = np.vstack([self.embeddings, new_embeddings])
                
                np.save(self.numpy_path, self.embeddings)
                logger.info(f"NumPy向量已更新: {old_count} -> {self.embeddings.shape[0]}")
            
            # 更新ID映射
            self.update_idmap(old_count, new_ids)
            return True
            
        except Exception as e:
            logger.error(f"向量追加失败: {e}")
            return False
    
    def update_idmap(self, start_offset: int, new_ids: List[str]) -> bool:
        """更新ID映射文件"""
        try:
            # 创建新的映射行
            new_rows = []
            for i, doc_id in enumerate(new_ids):
                new_rows.append({
                    'vector_offset': start_offset + i,
                    'id': doc_id
                })
            
            df_new = pd.DataFrame(new_rows)
            
            # 追加到现有文件或创建新文件
            if self.idmap_path.exists():
                df_new.to_csv(self.idmap_path, mode='a', header=False, index=False, encoding='utf-8')
            else:
                df_new.to_csv(self.idmap_path, index=False, encoding='utf-8')
            
            logger.info(f"ID映射已更新，新增 {len(new_ids)} 条")
            return True
            
        except Exception as e:
            logger.error(f"ID映射更新失败: {e}")
            return False
    
    def append_to_corpus(self, new_ids: List[str], new_texts: List[str]) -> bool:
        """追加到corpus.jsonl文件"""
        if not new_ids:
            return True
        
        try:
            # 确保目录存在
            self.corpus_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 追加到文件
            with open(self.corpus_path, 'a', encoding='utf-8') as f:
                for doc_id, text in zip(new_ids, new_texts):
                    doc = {
                        'id': doc_id,
                        'text': text,
                        'source': 'lab_feedback',
                        'page': None,
                        'url': None
                    }
                    f.write(json.dumps(doc, ensure_ascii=False) + '\n')
            
            logger.info(f"已追加 {len(new_ids)} 条记录到corpus.jsonl")
            return True
            
        except Exception as e:
            logger.error(f"corpus.jsonl追加失败: {e}")
            return False
    
    def update_metadata(self):
        """更新元信息"""
        try:
            if self.meta_info is None:
                self.meta_info = {}
            
            self.meta_info['last_updated'] = datetime.now().isoformat()
            self.meta_info['total_vectors'] = self.get_current_vector_count()
            
            with open(self.meta_path, 'w', encoding='utf-8') as f:
                json.dump(self.meta_info, f, indent=2, ensure_ascii=False)
            
            logger.info("元信息已更新")
            
        except Exception as e:
            logger.error(f"元信息更新失败: {e}")
    
    def process_feedback(self, experiments_path: Path, dry_run: bool = False) -> Tuple[int, int, int]:
        """处理实验反馈数据"""
        # 1. 加载反馈数据
        df_feedback = self.load_feedback_data(experiments_path)
        if df_feedback.empty:
            logger.warning("未找到有效的实验反馈数据")
            return 0, 0, 0
        
        # 2. 筛选新记录
        new_ids, new_texts = self.filter_new_records(df_feedback)
        
        old_count = self.get_current_vector_count()
        new_count = len(new_ids)
        
        # 3. 检查最小增量
        if new_count < self.min_delta:
            logger.info(f"新片段数量 {new_count} 小于最小要求 {self.min_delta}，无需更新")
            return old_count, 0, old_count
        
        # 4. 显示示例
        if new_ids:
            logger.info("示例新记录:")
            for i in range(min(2, len(new_ids))):
                logger.info(f"  ID: {new_ids[i]}")
                logger.info(f"  文本: {new_texts[i][:100]}...")
        
        if dry_run:
            logger.info(f"[DRY RUN] 将追加 {new_count} 条新向量")
            return old_count, new_count, old_count + new_count
        
        # 5. 嵌入新文本
        new_embeddings = self.embed_texts(new_texts)
        if len(new_embeddings) != new_count:
            logger.error("嵌入失败或数量不匹配")
            return old_count, 0, old_count
        
        # 6. 追加向量
        if not self.append_vectors(new_embeddings, new_ids):
            return old_count, 0, old_count
        
        # 7. 追加到corpus
        if not self.append_to_corpus(new_ids, new_texts):
            logger.warning("corpus.jsonl追加失败，但向量已更新")
        
        # 8. 更新元信息
        self.update_metadata()
        
        total_count = self.get_current_vector_count()
        logger.info(f"向量库更新完成: {old_count} -> {total_count} (+{new_count})")
        
        return old_count, new_count, total_count


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="增量向量库更新脚本 - 将实验反馈追加到现有知识库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 标准追加
  python scripts/append_feedback_to_kb.py

  # 设置最小增量要求
  python scripts/append_feedback_to_kb.py --min_delta 5

  # 试运行模式
  python scripts/append_feedback_to_kb.py --dry_run

返回码:
  0: 成功完成
  1: 一般错误
  2: 需要重建索引
        """
    )
    
    parser.add_argument("--experiments", 
                       type=str,
                       default="datasets/experiments/experiments.parquet",
                       help="实验数据文件路径")
    parser.add_argument("--index_dir",
                       type=str, 
                       default="datasets/index_store",
                       help="索引目录路径")
    parser.add_argument("--min_delta",
                       type=int,
                       default=1,
                       help="最少追加条数，不足则退出")
    parser.add_argument("--dry_run",
                       action="store_true",
                       help="试运行模式，不实际修改文件")
    
    args = parser.parse_args()
    
    setup_logging()
    
    try:
        # 检查输入文件
        experiments_path = Path(args.experiments)
        if not experiments_path.exists():
            logger.error(f"实验数据文件不存在: {experiments_path}")
            return 1
        
        index_dir = Path(args.index_dir)
        if not index_dir.exists():
            logger.error(f"索引目录不存在: {index_dir}")
            return 1
        
        # 创建更新器
        updater = FeedbackVectorUpdater(index_dir, args.min_delta)
        
        # 加载必要组件
        if not updater.load_meta_info():
            logger.error("加载元信息失败，可能需要重建索引")
            return 2
        
        if not updater.load_existing_ids():
            return 1
        
        if not updater.load_embedding_model():
            logger.error("嵌入模型加载失败或不兼容，需要重建索引")
            return 2
        
        if not updater.load_vector_backend():
            logger.error("向量后端加载失败，需要重建索引") 
            return 2
        
        # 处理反馈数据
        old_vecs, new_vecs, total_vecs = updater.process_feedback(
            experiments_path, args.dry_run
        )
        
        # 输出结果
        print(f"\n{'=' * 50}")
        print(f"向量库更新结果")
        print(f"{'=' * 50}")
        print(f"旧向量数: {old_vecs}")
        print(f"新向量数: {new_vecs}")  
        print(f"总向量数: {total_vecs}")
        print(f"后端类型: {updater.backend}")
        print(f"运行模式: {'试运行' if args.dry_run else '实际更新'}")
        
        if new_vecs == 0 and old_vecs > 0:
            print("状态: 无新片段需要追加")
        elif new_vecs > 0:
            print(f"状态: 成功追加 {new_vecs} 条反馈向量")
        
        return 0
        
    except Exception as e:
        logger.error(f"处理失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
