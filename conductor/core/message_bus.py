"""消息总线 - 内存队列通信"""

import asyncio
import json
import uuid
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    """标准化消息格式"""
    msg_id: str
    sender: str
    receiver: str
    msg_type: str  # request, response, broadcast, status, feedback
    payload: Dict[str, Any]
    in_reply_to: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "msg_type": self.msg_type,
            "payload": self.payload,
            "in_reply_to": self.in_reply_to,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            msg_id=data["msg_id"],
            sender=data["sender"],
            receiver=data["receiver"],
            msg_type=data["msg_type"],
            payload=data["payload"],
            in_reply_to=data.get("in_reply_to"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class MessageBus:
    """消息总线（单例）- 同进程内 Agent 通信"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._subscribers: Dict[str, List[Callable]] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._history: List[Message] = []
        self._max_history = 1000
        print("📡 消息总线已初始化")
    
    def subscribe(self, agent_name: str, callback: Callable):
        """订阅消息"""
        if agent_name not in self._subscribers:
            self._subscribers[agent_name] = []
        self._subscribers[agent_name].append(callback)
        print(f"   📨 {agent_name} 已订阅消息总线")
    
    def unsubscribe(self, agent_name: str, callback: Callable = None):
        """取消订阅"""
        if agent_name not in self._subscribers:
            return
        if callback is None:
            self._subscribers[agent_name].clear()
        else:
            self._subscribers[agent_name].remove(callback)
    
    def _save_to_history(self, message: Message):
        """保存消息历史"""
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history.pop(0)
    
    def _dispatch(self, message: Message):
        """分发消息到订阅者"""
        # 如果是响应，唤醒等待的 Future
        if message.msg_type == "response" and message.in_reply_to:
            if message.in_reply_to in self._pending_requests:
                future = self._pending_requests.pop(message.in_reply_to)
                if not future.done():
                    future.set_result(message.payload)
            return
        
        # 分发消息
        if message.receiver == "broadcast":
            for subscribers in self._subscribers.values():
                for cb in subscribers:
                    cb(message)
        elif message.receiver in self._subscribers:
            for cb in self._subscribers[message.receiver]:
                cb(message)
        else:
            print(f"⚠️ 未找到订阅者: {message.receiver}")
    
    def publish(self, message: Message):
        """发布消息（同步）"""
        self._save_to_history(message)
        print(f"📨 [{message.sender}] → [{message.receiver}]: {message.msg_type}")
        self._dispatch(message)
    
    async def request(
        self, 
        sender: str, 
        receiver: str, 
        payload: Dict[str, Any],
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """发送请求并等待响应（异步）"""
        msg_id = f"{sender}_{uuid.uuid4().hex[:8]}"
        
        # 创建等待响应的 Future
        future = asyncio.Future()
        self._pending_requests[msg_id] = future
        
        # 发送请求
        message = Message(
            msg_id=msg_id,
            sender=sender,
            receiver=receiver,
            msg_type="request",
            payload=payload
        )
        self.publish(message)
        
        # 等待响应
        try:
            result = await asyncio.wait_for(future, timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(msg_id, None)
            return {
                "status": "error",
                "error": f"请求超时 ({timeout}s)",
                "request": payload
            }
    
    def respond(self, request_msg: Message, payload: Dict[str, Any]):
        """响应请求"""
        response = Message(
            msg_id=f"resp_{request_msg.msg_id}",
            sender=request_msg.receiver,
            receiver=request_msg.sender,
            msg_type="response",
            payload=payload,
            in_reply_to=request_msg.msg_id
        )
        self.publish(response)
    
    def get_history(self, limit: int = 50) -> List[Message]:
        """获取消息历史"""
        return self._history[-limit:]


# 全局单例
_message_bus = None

def get_message_bus() -> MessageBus:
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus