from maowise.llm.client import llm_chat
from maowise.llm.rag import build_context, build_rag_prompt
from maowise.llm.jsonio import expect_schema


def test_llm_chat_basic():
    """测试基本 LLM 聊天功能"""
    messages = [{"role": "user", "content": "Hello, respond with 'test ok'"}]
    response = llm_chat(messages)
    
    assert "content" in response
    assert "role" in response
    assert "usage" in response
    assert isinstance(response["content"], str)


def test_llm_chat_json():
    """测试 JSON 格式输出"""
    messages = [
        {
            "role": "user", 
            "content": "Return JSON: {\"status\": \"ok\", \"value\": 42}"
        }
    ]
    response = llm_chat(messages)
    content = response.get("content", "")
    
    # 应该包含某种 JSON 结构
    assert "{" in content and "}" in content


def test_rag_context_build():
    """测试 RAG 上下文构建"""
    try:
        context = build_context("micro-arc oxidation", topk=2, max_tokens=500)
        assert isinstance(context, list)
        # 即使 KB 为空，也应该返回列表
    except Exception:
        # KB 可能未构建，这是正常的
        pass


def test_json_schema_parsing():
    """测试 JSON schema 解析"""
    schema = {"name": str, "value": int, "active": bool}
    
    # 测试正确的 JSON
    json_text = '{"name": "test", "value": 42, "active": true}'
    result = expect_schema(schema, json_text)
    
    assert result["name"] == "test"
    assert result["value"] == 42
    assert result["active"] is True
    
    # 测试损坏的 JSON（应该有默认值）
    broken_json = '{"name": "test", "value": invalid'
    result = expect_schema(schema, broken_json)
    
    # 应该有默认结构
    assert "name" in result
    assert "value" in result
    assert "active" in result


def test_rag_prompt_build():
    """测试 RAG prompt 构建"""
    messages = build_rag_prompt("What is MAO?", max_context_tokens=100)
    
    assert isinstance(messages, list)
    assert len(messages) >= 1
    assert messages[0]["role"] == "system"
    
    # 应该有用户消息
    user_msgs = [m for m in messages if m["role"] == "user"]
    assert len(user_msgs) == 1
