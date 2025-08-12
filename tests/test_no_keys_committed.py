"""
CI防泄密测试：扫描仓库中的敏感信息
"""

import os
import re
import pytest
from pathlib import Path
from typing import List, Tuple, Set


# 敏感信息模式定义
SENSITIVE_PATTERNS = {
    'openai_api_key': {
        'pattern': r'sk-[a-zA-Z0-9]{20,}',
        'description': 'OpenAI API Key',
        'severity': 'critical'
    },
    'azure_api_key': {
        'pattern': r'[a-f0-9]{32}',
        'description': 'Azure API Key (32-char hex)',
        'severity': 'high'
    },
    'generic_api_key': {
        'pattern': r'(?:api[_-]?key|secret|token|password)["\s]*[:=]["\s]*[a-zA-Z0-9+/=]{20,}',
        'description': 'Generic API Key/Secret',
        'severity': 'high'
    },
    'bearer_token': {
        'pattern': r'Bearer\s+[a-zA-Z0-9\-._~+/]+=*',
        'description': 'Bearer Token',
        'severity': 'medium'
    },
    'jwt_token': {
        'pattern': r'eyJ[a-zA-Z0-9\-._~+/]+=*\.eyJ[a-zA-Z0-9\-._~+/]+=*\.[a-zA-Z0-9\-._~+/]+=*',
        'description': 'JWT Token',
        'severity': 'medium'
    },
    'private_key': {
        'pattern': r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
        'description': 'Private Key',
        'severity': 'critical'
    },
    'ssh_key': {
        'pattern': r'ssh-rsa\s+[A-Za-z0-9+/]+=*',
        'description': 'SSH Public Key',
        'severity': 'medium'
    },
    'aws_access_key': {
        'pattern': r'AKIA[0-9A-Z]{16}',
        'description': 'AWS Access Key',
        'severity': 'critical'
    },
    'slack_token': {
        'pattern': r'xox[baprs]-[0-9a-zA-Z\-]{10,}',
        'description': 'Slack Token',
        'severity': 'high'
    },
    'github_token': {
        'pattern': r'gh[pousr]_[A-Za-z0-9_]{36}',
        'description': 'GitHub Token',
        'severity': 'high'
    }
}

# 允许的例外情况（测试文件等）
ALLOWED_EXCEPTIONS = {
    'test_patterns': [
        'sk-test-key-example',
        'sk-fake-key-for-testing',
        'sk-1234567890abcdefghijklmnopqrstuvwxyz',  # 测试用假密钥
        'example-api-key',
        'your-api-key-here',
        'INSERT_YOUR_API_KEY_HERE',
        '[API_KEY_REDACTED]',
        '[REDACTED]',
        'Bearer Token',  # 文档中的描述
        'Bearer abc123',  # 测试用token
        'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0'  # 测试用JWT
    ],
    'file_patterns': [
        r'.*\.md$',  # Markdown文档
        r'.*\.example$',  # 示例文件
        r'.*\.template$',  # 模板文件
        r'.*/test_.*\.py$',  # 测试文件（部分例外）
    ]
}

# 需要扫描的文件类型
SCAN_EXTENSIONS = {
    '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', 
    '.sh', '.bat', '.ps1', '.md', '.txt', '.env', '.example', '.template'
}

# 排除的目录
EXCLUDE_DIRS = {
    '.git', '.vscode', '.idea', '__pycache__', 'node_modules', 
    '.pytest_cache', '.mypy_cache', 'datasets', 'models', 'cache'
}


class SensitiveDataScanner:
    """敏感数据扫描器"""
    
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.violations: List[Tuple[str, str, str, str]] = []  # (file, line_no, pattern_name, content)
    
    def scan_repository(self) -> List[Tuple[str, str, str, str]]:
        """扫描整个仓库"""
        self.violations = []
        
        for file_path in self._get_files_to_scan():
            self._scan_file(file_path)
        
        return self.violations
    
    def _get_files_to_scan(self) -> List[Path]:
        """获取需要扫描的文件列表"""
        files = []
        
        for root, dirs, file_names in os.walk(self.root_path):
            # 排除指定目录
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            
            root_path = Path(root)
            
            for file_name in file_names:
                file_path = root_path / file_name
                
                # 检查文件扩展名
                if file_path.suffix.lower() in SCAN_EXTENSIONS or file_path.name.startswith('.env'):
                    files.append(file_path)
        
        return files
    
    def _scan_file(self, file_path: Path):
        """扫描单个文件"""
        try:
            # 检查是否为允许的例外文件
            relative_path = file_path.relative_to(self.root_path)
            if self._is_exception_file(str(relative_path)):
                return
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            lines = content.splitlines()
            
            for line_no, line in enumerate(lines, 1):
                self._scan_line(file_path, line_no, line)
                
        except Exception as e:
            # 忽略无法读取的文件
            pass
    
    def _scan_line(self, file_path: Path, line_no: int, line: str):
        """扫描单行内容"""
        for pattern_name, pattern_info in SENSITIVE_PATTERNS.items():
            pattern = pattern_info['pattern']
            
            matches = re.finditer(pattern, line, re.IGNORECASE)
            
            for match in matches:
                matched_text = match.group()
                
                # 检查是否为允许的例外
                if not self._is_exception_content(matched_text):
                    relative_path = file_path.relative_to(self.root_path)
                    self.violations.append((
                        str(relative_path),
                        str(line_no),
                        pattern_name,
                        matched_text
                    ))
    
    def _is_exception_file(self, file_path: str) -> bool:
        """检查是否为例外文件"""
        for pattern in ALLOWED_EXCEPTIONS['file_patterns']:
            if re.match(pattern, file_path):
                return True
        return False
    
    def _is_exception_content(self, content: str) -> bool:
        """检查是否为允许的例外内容"""
        for exception in ALLOWED_EXCEPTIONS['test_patterns']:
            if exception.lower() in content.lower():
                return True
        return False


def test_no_sensitive_data_committed():
    """测试：确保没有敏感数据被提交到仓库"""
    
    # 获取仓库根目录
    current_file = Path(__file__)
    repo_root = current_file.parent.parent
    
    # 扫描仓库
    scanner = SensitiveDataScanner(repo_root)
    violations = scanner.scan_repository()
    
    # 如果发现违规，生成详细报告
    if violations:
        error_messages = []
        error_messages.append("🚨 发现敏感信息泄露！")
        error_messages.append("")
        
        # 按严重程度分组
        critical_violations = []
        high_violations = []
        medium_violations = []
        
        for file_path, line_no, pattern_name, content in violations:
            severity = SENSITIVE_PATTERNS[pattern_name]['severity']
            description = SENSITIVE_PATTERNS[pattern_name]['description']
            
            violation_info = {
                'file': file_path,
                'line': line_no,
                'pattern': pattern_name,
                'description': description,
                'content': content[:50] + '...' if len(content) > 50 else content
            }
            
            if severity == 'critical':
                critical_violations.append(violation_info)
            elif severity == 'high':
                high_violations.append(violation_info)
            else:
                medium_violations.append(violation_info)
        
        # 生成分级报告
        if critical_violations:
            error_messages.append("🔴 CRITICAL 级别违规:")
            for v in critical_violations:
                error_messages.append(f"  文件: {v['file']}:{v['line']}")
                error_messages.append(f"  类型: {v['description']}")
                error_messages.append(f"  内容: {v['content']}")
                error_messages.append("")
        
        if high_violations:
            error_messages.append("🟠 HIGH 级别违规:")
            for v in high_violations:
                error_messages.append(f"  文件: {v['file']}:{v['line']}")
                error_messages.append(f"  类型: {v['description']}")
                error_messages.append(f"  内容: {v['content']}")
                error_messages.append("")
        
        if medium_violations:
            error_messages.append("🟡 MEDIUM 级别违规:")
            for v in medium_violations:
                error_messages.append(f"  文件: {v['file']}:{v['line']}")
                error_messages.append(f"  类型: {v['description']}")
                error_messages.append(f"  内容: {v['content']}")
                error_messages.append("")
        
        error_messages.append("💡 解决建议:")
        error_messages.append("1. 立即从代码中移除敏感信息")
        error_messages.append("2. 使用环境变量或配置文件存储敏感信息")
        error_messages.append("3. 将敏感文件添加到 .gitignore")
        error_messages.append("4. 考虑使用 git filter-branch 清理历史记录")
        error_messages.append("")
        error_messages.append("🔒 如果这些是测试数据，请添加到 ALLOWED_EXCEPTIONS")
        
        # 测试失败
        pytest.fail("\n".join(error_messages))


def test_gitignore_covers_sensitive_files():
    """测试：确保 .gitignore 覆盖了敏感文件"""
    
    repo_root = Path(__file__).parent.parent
    gitignore_path = repo_root / '.gitignore'
    
    # 检查 .gitignore 是否存在
    assert gitignore_path.exists(), ".gitignore 文件不存在"
    
    with open(gitignore_path, 'r', encoding='utf-8') as f:
        gitignore_content = f.read()
    
    # 应该忽略的敏感文件模式
    required_patterns = [
        '.env',
        '*.key',
        '*.pem',
        'secrets/',
        'credentials/',
    ]
    
    missing_patterns = []
    
    for pattern in required_patterns:
        if pattern not in gitignore_content:
            missing_patterns.append(pattern)
    
    if missing_patterns:
        error_msg = f".gitignore 缺少以下敏感文件模式: {', '.join(missing_patterns)}"
        pytest.fail(error_msg)


def test_env_example_files_are_safe():
    """测试：确保 .env.example 文件不包含真实敏感信息"""
    
    repo_root = Path(__file__).parent.parent
    
    # 查找所有 .env.example 文件
    example_files = []
    for root, dirs, files in os.walk(repo_root):
        for file in files:
            if file.endswith('.example') or file.endswith('.template'):
                example_files.append(Path(root) / file)
    
    violations = []
    
    for file_path in example_files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 检查是否包含看起来像真实密钥的内容
            suspicious_patterns = [
                r'sk-[a-zA-Z0-9]{40,}',  # 真实的OpenAI密钥通常更长
                r'[a-f0-9]{64}',  # 64位hex字符串
                r'AKIA[0-9A-Z]{16}',  # AWS密钥
            ]
            
            for pattern in suspicious_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    # 排除明显的占位符
                    if not any(placeholder in match.lower() for placeholder in ['example', 'your', 'insert', 'replace']):
                        violations.append((file_path.name, match))
        
        except Exception:
            continue
    
    if violations:
        error_msg = "发现示例文件包含疑似真实敏感信息:\n"
        for file_name, content in violations:
            error_msg += f"  {file_name}: {content}\n"
        pytest.fail(error_msg)


if __name__ == "__main__":
    # 直接运行扫描
    repo_root = Path(__file__).parent.parent
    scanner = SensitiveDataScanner(repo_root)
    violations = scanner.scan_repository()
    
    if violations:
        print("🚨 发现敏感信息泄露！")
        for file_path, line_no, pattern_name, content in violations:
            severity = SENSITIVE_PATTERNS[pattern_name]['severity']
            description = SENSITIVE_PATTERNS[pattern_name]['description']
            print(f"[{severity.upper()}] {file_path}:{line_no} - {description}: {content}")
    else:
        print("✅ 未发现敏感信息泄露")
