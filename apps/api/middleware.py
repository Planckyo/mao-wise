"""
API中间件：日志脱敏和请求跟踪
"""

import json
import time
import uuid
from typing import Any, Dict, Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from maowise.utils.sanitizer import sanitize_request_body, sanitize_response, sanitize_text
from maowise.utils.logger import logger


class LogSanitizationMiddleware(BaseHTTPMiddleware):
    """日志脱敏中间件"""
    
    def __init__(self, app, debug_mode: bool = False):
        super().__init__(app)
        self.debug_mode = debug_mode
    
    async def dispatch(self, request: Request, call_next):
        # 生成请求ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        
        start_time = time.time()
        
        # 读取请求体
        body = await self._get_request_body(request)
        
        # 记录请求（脱敏）
        self._log_request(request, body, request_id)
        
        try:
            # 处理请求
            response = await call_next(request)
            
            # 记录响应
            response_body = await self._get_response_body(response)
            duration = time.time() - start_time
            
            self._log_response(request, response, response_body, duration, request_id)
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            self._log_error(request, e, duration, request_id)
            
            # 返回脱敏的错误响应
            error_response = {
                "error": "Internal server error",
                "request_id": request_id,
                "message": sanitize_text(str(e)) if self.debug_mode else "An error occurred"
            }
            
            return JSONResponse(
                status_code=500,
                content=error_response
            )
    
    async def _get_request_body(self, request: Request) -> Optional[bytes]:
        """获取请求体"""
        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                body = await request.body()
                # 重置请求体以供后续使用
                async def receive():
                    return {"type": "http.request", "body": body}
                request._receive = receive
                return body
        except Exception as e:
            logger.warning(f"Failed to read request body: {e}")
        return None
    
    async def _get_response_body(self, response: Response) -> Optional[str]:
        """获取响应体"""
        try:
            if hasattr(response, 'body') and response.body:
                return response.body.decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to read response body: {e}")
        return None
    
    def _log_request(self, request: Request, body: Optional[bytes], request_id: str):
        """记录请求（脱敏）"""
        try:
            # 基本请求信息
            log_data = {
                "request_id": request_id,
                "method": request.method,
                "url": sanitize_text(str(request.url)),
                "user_agent": sanitize_text(request.headers.get("user-agent", "")),
                "content_type": request.headers.get("content-type", ""),
            }
            
            # 脱敏请求头
            sensitive_headers = {'authorization', 'x-api-key', 'cookie', 'x-auth-token'}
            headers = {}
            for key, value in request.headers.items():
                if key.lower() in sensitive_headers:
                    headers[key] = '[REDACTED]'
                else:
                    headers[key] = sanitize_text(value)
            log_data["headers"] = headers
            
            # 脱敏请求体
            if body:
                try:
                    body_str = body.decode('utf-8')
                    if request.headers.get("content-type", "").startswith("application/json"):
                        body_data = json.loads(body_str)
                        log_data["body"] = sanitize_request_body(body_data)
                    else:
                        log_data["body"] = sanitize_text(body_str)
                except Exception:
                    log_data["body"] = "[BODY_PARSE_ERROR]"
            
            if self.debug_mode:
                logger.info(f"Request: {json.dumps(log_data, ensure_ascii=False, indent=2)}")
            else:
                logger.info(f"Request [{request_id}]: {log_data['method']} {log_data['url']}")
                
        except Exception as e:
            logger.warning(f"Failed to log request: {e}")
    
    def _log_response(self, request: Request, response: Response, body: Optional[str], 
                     duration: float, request_id: str):
        """记录响应（脱敏）"""
        try:
            log_data = {
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "content_type": response.headers.get("content-type", ""),
            }
            
            # 脱敏响应体
            if body and self.debug_mode:
                try:
                    if response.headers.get("content-type", "").startswith("application/json"):
                        response_data = json.loads(body)
                        log_data["body"] = sanitize_response(response_data)
                    else:
                        log_data["body"] = sanitize_text(body)
                except Exception:
                    log_data["body"] = "[RESPONSE_PARSE_ERROR]"
            
            if self.debug_mode:
                logger.info(f"Response: {json.dumps(log_data, ensure_ascii=False, indent=2)}")
            else:
                logger.info(f"Response [{request_id}]: {log_data['status_code']} in {log_data['duration_ms']}ms")
                
        except Exception as e:
            logger.warning(f"Failed to log response: {e}")
    
    def _log_error(self, request: Request, error: Exception, duration: float, request_id: str):
        """记录错误（脱敏）"""
        try:
            log_data = {
                "request_id": request_id,
                "error_type": type(error).__name__,
                "error_message": sanitize_text(str(error)),
                "duration_ms": round(duration * 1000, 2),
            }
            
            logger.error(f"Request Error [{request_id}]: {json.dumps(log_data, ensure_ascii=False)}")
            
        except Exception as e:
            logger.error(f"Failed to log error: {e}")


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """请求跟踪中间件"""
    
    def __init__(self, app):
        super().__init__(app)
        self.request_count = 0
        self.start_time = time.time()
    
    async def dispatch(self, request: Request, call_next):
        self.request_count += 1
        
        # 添加服务器信息到响应头
        response = await call_next(request)
        
        response.headers["X-Request-Count"] = str(self.request_count)
        response.headers["X-Server-Uptime"] = str(int(time.time() - self.start_time))
        
        # 不暴露敏感的服务器信息
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]
        if "Server" in response.headers:
            response.headers["Server"] = "MAO-Wise"
        
        return response


def create_logging_middleware(debug_llm: bool = False):
    """创建日志中间件"""
    return LogSanitizationMiddleware, {"debug_mode": debug_llm}


def create_tracking_middleware():
    """创建跟踪中间件"""
    return RequestTrackingMiddleware, {}
