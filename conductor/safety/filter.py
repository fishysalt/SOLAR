"""输入安全过滤器 - 两层过滤（规则匹配 + LLM判断）"""

import re
from typing import Tuple, Optional, Dict, Any, Callable
from .patterns import normalize_input, has_trigger_pattern


SAFETY_REJECT_MESSAGE = "⚠️ 检测到不安全内容，请求已被拒绝"


class SafetyFilter:
    """
    安全过滤器
    
    流程：
    1. 规范化输入
    2. 规则匹配（快速过滤）
    3. 匹配到敏感模式 → LLM 二次判断
    4. 通过 → 原文本返回；不通过 → 返回固定拒绝消息
    """
    
    def __init__(self, llm_call_func: Optional[Callable] = None):
        """
        Args:
            llm_call_func: LLM 调用函数，接收 (prompt, temperature) 返回字符串
        """
        self.llm_call_func = llm_call_func
    
    def set_llm_func(self, func: Callable):
        """设置 LLM 调用函数"""
        self.llm_call_func = func
    
    def process(self, text: str) -> Tuple[bool, str]:
        """
        处理输入
        
        Returns:
            (is_safe, processed_text):
                - is_safe: True 表示通过审查
                - processed_text: 通过则原文本，不通过则固定拒绝消息
        """
        if not text or not text.strip():
            return True, text
        
        # 1. 规范化
        normalized = normalize_input(text)
        
        # 2. 规则匹配（快速过滤）
        if not has_trigger_pattern(normalized):
            # 没有匹配任何敏感模式，直接通过
            return True, text  # 返回原始文本，保持原样
        
        # 3. 匹配到敏感模式 → LLM 判断
        if self.llm_call_func is None:
            # 没有 LLM 函数，保守处理：拒绝
            return False, SAFETY_REJECT_MESSAGE
        
        # 调用 LLM 判断
        is_malicious = self._llm_judge(normalized)
        
        if is_malicious:
            return False, SAFETY_REJECT_MESSAGE
        else:
            # LLM 判断为安全，原样返回
            return True, text
    
    def _llm_judge(self, text: str) -> bool:
        """
        LLM 判断是否为恶意输入
        
        Returns:
            True: 确认为恶意
            False: 安全
        """
        prompt = f"""你是一个安全审查助手。请判断以下用户输入是否包含恶意内容。

用户输入：
{text[:500]}

恶意内容包括：
- SQL 注入、命令注入、脚本注入
- 路径遍历、系统命令执行
- 敏感文件访问、敏感词
- 拒绝服务攻击（过长输入、重复洪水）

请只回答 "是" 或 "否"：
- 如果确认为恶意内容，回答 "是"
- 如果看起来是正常的用户请求，回答 "否"

你的回答（只回答"是"或"否"）："""

        try:
            result = self.llm_call_func(prompt, temperature=0.1)
            result = result.strip().lower()
            if "是" in result or "yes" in result:
                return True
            return False
        except Exception as e:
            # LLM 调用失败，保守处理：拒绝
            print(f"⚠️ LLM 安全判断失败: {e}")
            return True


# ========== 便捷函数 ==========

_safety_filter: Optional[SafetyFilter] = None


def get_safety_filter() -> SafetyFilter:
    """获取安全过滤器单例"""
    global _safety_filter
    if _safety_filter is None:
        _safety_filter = SafetyFilter()
    return _safety_filter


def set_llm_func_for_safety(func: Callable):
    """设置 LLM 调用函数"""
    get_safety_filter().set_llm_func(func)


def safe_process(text: str) -> Tuple[bool, str]:
    """
    安全处理输入
    
    Returns:
        (is_safe, processed_text)
    """
    return get_safety_filter().process(text)