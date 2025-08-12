from __future__ import annotations

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from ..kb.search import kb_search
from ..utils.logger import logger


@dataclass
class Snippet:
    text: str
    source: str
    page: int
    score: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "page": self.page,
            "score": self.score
        }


def estimate_tokens(text: str) -> int:
    """粗略估计文本 token 数量（1 token ≈ 4 chars for Chinese/English mix）"""
    return len(text) // 4


def build_context(
    query_or_payload: str, 
    topk: int = 5, 
    max_tokens: int = 2000
) -> List[Snippet]:
    """
    构建 RAG 上下文
    
    Args:
        query_or_payload: 查询文本或负载
        topk: 检索数量
        max_tokens: 最大 token 限制
    
    Returns:
        List[Snippet]: 检索到的文档片段
    """
    try:
        # 使用 KB 检索
        results = kb_search(query_or_payload, k=topk)
        
        snippets = []
        total_tokens = 0
        
        for result in results:
            text = result.get("snippet", "")
            source = result.get("doc_id", "unknown")
            page = result.get("page", 1)
            score = result.get("score", 0.0)
            
            # 估计 token 数量
            text_tokens = estimate_tokens(text)
            
            # 检查是否超过限制
            if total_tokens + text_tokens > max_tokens:
                # 截断文本以适应限制
                remaining_tokens = max_tokens - total_tokens
                if remaining_tokens > 50:  # 至少保留 50 tokens
                    truncated_chars = remaining_tokens * 4
                    text = text[:truncated_chars] + "..."
                    text_tokens = estimate_tokens(text)
                else:
                    break
            
            snippet = Snippet(
                text=text,
                source=source,
                page=page,
                score=score
            )
            
            snippets.append(snippet)
            total_tokens += text_tokens
            
            if total_tokens >= max_tokens:
                break
        
        logger.info(f"Built RAG context: {len(snippets)} snippets, ~{total_tokens} tokens")
        return snippets
        
    except Exception as e:
        logger.warning(f"RAG context building failed: {e}")
        return []


def format_context_for_prompt(snippets: List[Snippet], include_sources: bool = True) -> str:
    """
    将 snippets 格式化为 prompt 上下文
    
    Args:
        snippets: 文档片段列表
        include_sources: 是否包含来源信息
    
    Returns:
        str: 格式化的上下文文本
    """
    if not snippets:
        return "No relevant context found."
    
    context_parts = []
    for i, snippet in enumerate(snippets, 1):
        if include_sources:
            header = f"[Document {i}: {snippet.source}, Page {snippet.page}]"
            context_parts.append(f"{header}\n{snippet.text}")
        else:
            context_parts.append(snippet.text)
    
    return "\n\n".join(context_parts)


def build_rag_prompt(
    user_query: str,
    system_prompt: str = "You are a helpful assistant for micro-arc oxidation research.",
    context_snippets: Optional[List[Snippet]] = None,
    max_context_tokens: int = 2000
) -> List[Dict[str, str]]:
    """
    构建包含 RAG 上下文的完整 prompt
    
    Args:
        user_query: 用户查询
        system_prompt: 系统提示
        context_snippets: 上下文片段（可选，会自动检索）
        max_context_tokens: 最大上下文 token 数
    
    Returns:
        List[Dict[str, str]]: 消息列表
    """
    if context_snippets is None:
        context_snippets = build_context(user_query, max_tokens=max_context_tokens)
    
    messages = [{"role": "system", "content": system_prompt}]
    
    if context_snippets:
        context_text = format_context_for_prompt(context_snippets)
        enhanced_query = f"Based on the following context:\n\n{context_text}\n\nQuestion: {user_query}"
        messages.append({"role": "user", "content": enhanced_query})
    else:
        messages.append({"role": "user", "content": user_query})
    
    return messages
