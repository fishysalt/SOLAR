"""Conductor 任务管理器"""

import uuid
import threading
from typing import Dict, List, Optional
from datetime import datetime
from .models import Task, TaskStatus, SubTask, SubtaskStatus


class TaskManager:
    """
    任务管理器 - 管理所有任务的生命周期
    
    线程安全：使用锁保护共享数据
    """
    
    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._user_tasks: Dict[str, List[str]] = {}  # user_id -> [task_ids]
        self._lock = threading.Lock()
        
        # 回调处理函数（由Conductor注入）
        self._callback_handler = None
        
        print("📋 TaskManager 已初始化")
    
    def set_callback_handler(self, handler):
        """注入回调处理函数"""
        self._callback_handler = handler
    
    def create_task(self, user_id: str, instruction: str, 
                    initial_memory: List[Dict[str, str]] = None) -> Task:
        """
        创建新任务
        
        Args:
            user_id: 用户ID
            instruction: 用户指令
            initial_memory: 任务隔离上下文
        
        Returns:
            创建的任务对象
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        task = Task(
            task_id=task_id,
            user_id=user_id,
            instruction=instruction,
            isolated_memory=initial_memory or []
        )
        
        with self._lock:
            self._tasks[task_id] = task
            if user_id not in self._user_tasks:
                self._user_tasks[user_id] = []
            self._user_tasks[user_id].append(task_id)
        
        print(f"📋 创建任务: {task_id} (用户: {user_id})")
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_user_tasks(self, user_id: str) -> List[Task]:
        """获取用户的所有任务"""
        with self._lock:
            task_ids = self._user_tasks.get(user_id, [])
            return [self._tasks[tid] for tid in task_ids if tid in self._tasks]
    
    def update_task_status(self, task_id: str, status: TaskStatus):
        """更新任务状态"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                task.updated_at = datetime.now()
    
    def add_subtask(self, task_id: str, agent_name: str, instruction: str) -> Optional[SubTask]:
        """添加子任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            
            subtask_id = f"{task_id}_sub_{len(task.subtasks) + 1:03d}"
            subtask = SubTask(
                id=subtask_id,
                agent_name=agent_name,
                instruction=instruction
            )
            task.subtasks.append(subtask)
            task.updated_at = datetime.now()
            return subtask
    
    def start_subtask(self, task_id: str, subtask_id: str) -> bool:
        """标记子任务开始执行"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            for st in task.subtasks:
                if st.id == subtask_id:
                    st.status = SubtaskStatus.RUNNING
                    st.started_at = datetime.now()
                    task.updated_at = datetime.now()
                    task.status = TaskStatus.RUNNING
                    return True
            return False
    
    def complete_subtask(self, task_id: str, subtask_id: str, 
                          result: str = None, output_files: List[str] = None) -> bool:
        """
        标记子任务完成（由回调触发）
        
        Returns:
            是否所有子任务都已完成
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            for st in task.subtasks:
                if st.id == subtask_id:
                    st.status = SubtaskStatus.COMPLETED
                    st.result = result
                    st.output_files = output_files or []
                    st.completed_at = datetime.now()
                    task.updated_at = datetime.now()
                    break
            else:
                return False
            
            # 检查是否所有子任务完成
            all_done = task.is_all_completed()
            if all_done:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                task.updated_at = datetime.now()
            
            return all_done
    
    def fail_subtask(self, task_id: str, subtask_id: str, error: str) -> bool:
        """标记子任务失败"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            for st in task.subtasks:
                if st.id == subtask_id:
                    st.status = SubtaskStatus.FAILED
                    st.error = error
                    st.completed_at = datetime.now()
                    task.updated_at = datetime.now()
                    task.status = TaskStatus.FAILED
                    return True
            return False
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Returns:
            是否成功标记取消
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
                return False
            
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now()
            
            # 标记所有未完成的子任务为取消
            for st in task.subtasks:
                if st.status not in [SubtaskStatus.COMPLETED, SubtaskStatus.CANCELLED]:
                    st.status = SubtaskStatus.CANCELLED
                    st.completed_at = datetime.now()
            
            print(f"⏹️ 任务已取消: {task_id}")
            return True
    
    def get_task_summary(self, task_id: str) -> Dict:
        """获取任务摘要（供UI展示）"""
        task = self.get_task(task_id)
        if not task:
            return {"error": f"任务 {task_id} 不存在"}
        return task.to_dict()