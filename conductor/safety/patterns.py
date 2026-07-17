"""安全模式定义 - 独立维护，易于更新"""

import re
from typing import List, Dict


# ========== 恶意输入模式（触发 LLM 二次判断） ==========

TRIGGER_PATTERNS: List[Dict[str, str]] = [
    # SQL 注入特征
    {
        "name": "sql_injection",
        "pattern": r"(?i)(SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+.+\s+SET|DELETE\s+FROM|DROP\s+TABLE|UNION\s+SELECT|--\s*$|;.*--)",
    },
    # 命令注入特征
    {
        "name": "command_injection",
        "pattern": r"(?i)(rm\s+-rf|sudo\s+rm|del\s+/f|format\s+[a-z]:|shutdown\s+/s|reboot|curl.*\||wget.*\|)",
    },
    # XSS/脚本注入
    {
        "name": "script_injection",
        "pattern": r"<script.*?>.*?</script>|<iframe.*?>|javascript:|onerror=|onload=",
    },
    # 路径遍历
    {
        "name": "path_traversal",
        "pattern": r"(\.\./|\.\.\\)|/etc/passwd|/etc/shadow|C:\\Windows\\System32",
    },
    # 系统命令执行
    {
        "name": "system_command",
        "pattern": r"(?i)(eval\(|exec\(|system\(|popen\(|subprocess\.|os\.system|__import__|compile\()",
    },
    # 过长输入（可能为DoS尝试）
    {
        "name": "excessive_length",
        "pattern": r"^.{2000,}$",
    },
    # 敏感文件/配置
    {
        "name": "sensitive_file",
        "pattern": r"(?i)(\.env|\.git|config\.yaml|config\.json|secret|api[_-]?key|password|token|credential)",
    },
    # 重复字符洪水
    {
        "name": "repetition_flood",
        "pattern": r"^(.)\1{30,}$",
    },
    # 敏感词（触发LLM判断）
    {
        "name": "sensitive_word",
        "pattern": r"(?i)(系统管理员|root|admin|sudo|黑客|攻击|入侵|病毒|木马|删除所有|格式化|关机)",
    },
]


# ========== 规范化规则 ==========

def normalize_input(text: str) -> str:
    """输入规范化：压缩多余空格、换行，去除零宽字符"""
    import re
    
    if not text:
        return text
    
    # 移除零宽字符
    text = re.sub(r'[\u200b\u200c\u200d\u2060\uFEFF]', '', text)
    # 全角转半角（基础）
    fullwidth_map = {
        '，': ',', '。': '.', '！': '!', '？': '?',
        '；': ';', '：': ':', '（': '(', '）': ')',
        '【': '[', '】': ']', '、': ',', '～': '~',
        '＝': '=', '＋': '+', '－': '-', '＊': '*',
        '／': '/', '％': '%', '＃': '#', '＠': '@',
        '＆': '&', '＿': '_', '｜': '|', '｀': '`',
        '＾': '^', '｛': '{', '｝': '}', '＜': '<',
        '＞': '>', '　': ' '
    }
    text = ''.join(fullwidth_map.get(c, c) for c in text)
    # 压缩多个空格为单个
    text = re.sub(r' +', ' ', text)
    # 压缩多个换行为两个
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def compile_trigger_patterns():
    """预编译触发模式"""
    compiled = []
    for p in TRIGGER_PATTERNS:
        compiled.append({
            "name": p["name"],
            "pattern": re.compile(p["pattern"], re.IGNORECASE | re.DOTALL)
        })
    return compiled


# 预编译实例
TRIGGER_PATTERNS_COMPILED = compile_trigger_patterns()


def has_trigger_pattern(text: str) -> bool:
    """检查是否匹配任何触发模式"""
    for p in TRIGGER_PATTERNS_COMPILED:
        if p["pattern"].search(text):
            return True
    return False