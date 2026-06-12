"""RAG 知识库 - 独立于记忆系统，用于专业知识检索"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional


class KnowledgeBase:
    """简单的文档知识库，支持关键词检索"""
    
    def __init__(self, rag_dir: Path):
        self.rag_dir = Path(rag_dir)
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        
        self._documents: List[Dict] = []
        self._index_file = self.rag_dir / "index.json"
        
        self._load()
    
    def _load(self):
        self._documents.clear()
        
        if self._index_file.exists():
            try:
                with open(self._index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._documents = data.get("documents", [])
                print(f"   📚 从索引加载 {len(self._documents)} 个知识文档")
            except Exception as e:
                print(f"   ⚠️ 加载知识库索引失败: {e}")
        
        for file_path in self.rag_dir.glob("*.txt"):
            if file_path.name == "index.json":
                continue
            try:
                content = file_path.read_text(encoding='utf-8')
                exists = any(d.get("source") == file_path.name for d in self._documents)
                if not exists:
                    self._documents.append({
                        "source": file_path.name,
                        "content": content,
                        "type": "file",
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    print(f"   📚 加载知识文档: {file_path.name}")
            except Exception as e:
                print(f"   ⚠️ 加载文档失败 {file_path.name}: {e}")
        
        self._save_index()
    
    def _save_index(self):
        try:
            with open(self._index_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "documents": self._documents,
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"   ⚠️ 保存知识库索引失败: {e}")
    
    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        搜索相关知识
        
        简化策略：如果文档数少于 5 个，直接返回所有文档
        """
        if not self._documents:
            return []
        
        # 简化策略：文档少时全部返回
        if len(self._documents) <= 5:
            print(f"   📚 RAG: 文档数少({len(self._documents)})，返回全部")
            results = []
            for doc in self._documents:
                content = doc["content"]
                if len(content) > 500:
                    content = content[:500] + "..."
                results.append({
                    "source": doc["source"],
                    "content": content,
                    "score": 1.0
                })
            return results
        
        # 正常关键词匹配
        if not query:
            return []
        
        query_lower = query.lower()
        results = []
        
        for doc in self._documents:
            content_lower = doc["content"].lower()
            score = 0
            
            words = query_lower.split()
            for word in words:
                if len(word) > 2:
                    score += content_lower.count(word)
            
            source_lower = doc.get("source", "").lower()
            for word in words:
                if len(word) > 2 and word in source_lower:
                    score += 10
            
            if score > 0:
                content = doc["content"]
                if len(content) > 500:
                    idx = content_lower.find(query_lower)
                    if idx >= 0:
                        start = max(0, idx - 200)
                        end = min(len(content), idx + 300)
                        content = "..." + content[start:end] + "..."
                    else:
                        content = content[:500] + "..."
                
                results.append({
                    "source": doc["source"],
                    "content": content,
                    "score": score,
                    "created_at": doc.get("created_at", "")
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    
    def add_document(self, content: str, filename: str = None) -> str:
        if filename is None:
            filename = f"doc_{int(time.time())}.txt"
        
        if not filename.endswith('.txt'):
            filename += '.txt'
        
        file_path = self.rag_dir / filename
        file_path.write_text(content, encoding='utf-8')
        
        self._documents.append({
            "source": filename,
            "filename": filename,
            "content": content,
            "type": "file",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save_index()
        
        return filename
    
    def delete_document(self, filename: str) -> bool:
        original_count = len(self._documents)
        self._documents = [d for d in self._documents if d.get("filename") != filename]
        
        file_path = self.rag_dir / filename
        if file_path.exists():
            file_path.unlink()
        
        self._save_index()
        return len(self._documents) < original_count
    
    def get_all_documents(self) -> List[Dict]:
        return [
            {
                "filename": d.get("filename", d.get("source")),
                "source": d.get("source"),
                "content_preview": d["content"][:200] + ("..." if len(d["content"]) > 200 else ""),
                "created_at": d.get("created_at", "")
            }
            for d in self._documents
        ]
    
    def get_document_content(self, filename: str) -> Optional[str]:
        for doc in self._documents:
            if doc.get("filename") == filename:
                return doc["content"]
        return None
    
    def get_stats(self) -> dict:
        return {
            "document_count": len(self._documents),
            "documents": [d.get("filename", d.get("source")) for d in self._documents]
        }
    
    def reload(self):
        self._load()