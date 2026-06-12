"""Conductor 用户反馈工具"""

# 全局等待反馈的状态
_pending_feedback: dict = {}


def get_user_feedback(task_id: str, question: str = "请确认任务结果是否满意？") -> str:
    """
    获取用户对任务结果的反馈
    
    注意：这是一个阻塞式工具，会等待用户输入。
    
    Args:
        task_id: 任务 ID
        question: 询问用户的问题
    """
    global _pending_feedback
    
    # 设置等待状态
    _pending_feedback[task_id] = {"status": "waiting", "question": question}
    
    print(f"\n📢 [需要用户反馈] {question}")
    print("请回复 '满意' / '不满意' / '重试'")
    
    # 这里应该通过 UI 获取用户输入，暂时用控制台模拟
    # 实际使用时，这个工具会被 UI 层拦截，通过界面获取反馈
    
    return f"⏳ 等待用户反馈 (任务: {task_id})"


def submit_feedback(task_id: str, feedback: str, comment: str = "") -> str:
    """
    提交用户反馈（由 UI 层调用）
    
    Args:
        task_id: 任务 ID
        feedback: 反馈内容 (satisfied/unsatisfied/retry)
        comment: 附加评论
    """
    global _pending_feedback
    
    if task_id in _pending_feedback:
        _pending_feedback[task_id]["feedback"] = feedback
        _pending_feedback[task_id]["comment"] = comment
        _pending_feedback[task_id]["status"] = "done"
        
        print(f"📝 收到反馈: {feedback} - {comment}")
        return f"✅ 反馈已记录: {feedback}"
    
    return f"❌ 未找到任务: {task_id}"


def get_pending_feedback(task_id: str = None) -> dict:
    """获取等待中的反馈请求"""
    global _pending_feedback
    
    if task_id:
        return _pending_feedback.get(task_id, {})
    
    return {tid: info for tid, info in _pending_feedback.items() if info.get("status") == "waiting"}


# 工具定义
GET_USER_FEEDBACK_TOOL = {
    "name": "get_user_feedback",
    "description": "向用户询问反馈。当任务完成或有重要决策时使用。",
    "func": get_user_feedback,
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务标识"},
            "question": {"type": "string", "description": "询问用户的问题", "default": "请确认任务结果是否满意？"}
        },
        "required": ["task_id"]
    }
}