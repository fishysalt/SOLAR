"""Creator Agent 独立 UI - 包含 API 服务、记忆管理、RAG 管理"""

import sys
import os
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import gradio as gr
from creator.agent import get_creator


def run_api_server(port: int):
    """在后台线程运行 FastAPI 服务"""
    try:
        import uvicorn
        from creator.api import app
        print(f"📡 Creator API 服务启动在 http://localhost:{port}")
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except Exception as e:
        print(f"⚠️ API 服务启动失败: {e}")


def main():
    """启动 Creator Agent（独立模式）"""
    api_port = int(os.environ.get("AGENT_PORT", 7861))
    ui_port = api_port + 100
    
    # 启动 API 服务（后台线程）
    api_thread = threading.Thread(target=run_api_server, args=(api_port,), daemon=True)
    api_thread.start()
    
    import time
    time.sleep(2)
    
    creator = get_creator()
    
    print(f"✨ Creator Agent 已初始化")
    print(f"   能力: {', '.join(creator.capabilities)}")
    print(f"   记忆目录: {creator.memory.memory_dir}")
    print(f"   工具数量: {creator.tools.list_tools() if creator.tools else 0}")
    print(f"   API: http://localhost:{api_port}")
    print(f"   UI:  http://localhost:{ui_port}")
    
    with gr.Blocks(title="✨ Creator Agent") as demo:
        gr.Markdown("# ✨ Creator Agent")
        gr.Markdown(f"API: {api_port} | UI: {ui_port}")
        
        with gr.Tabs():
            # ========== 对话标签页 ==========
            with gr.TabItem("💬 对话"):
                chatbot = gr.Chatbot(label="Creator", height=500)
                msg = gr.Textbox(label="输入任务", placeholder="例如：自我介绍、记住我喜欢简约风格、查看我的记忆...", lines=2)
                clear_chat_btn = gr.Button("清空对话")
                
                def respond(message, history):
                    if not message:
                        return "", history
                    
                    result = creator.handle_task(message, [])
                    response = result.get("message", "处理完成")
                    
                    history = history or []
                    history.append({
                        "role": "user",
                        "content": [{"type": "text", "text": message}]
                    })
                    history.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": response}]
                    })
                    return "", history
                
                msg.submit(respond, [msg, chatbot], [msg, chatbot])
                clear_chat_btn.click(lambda: [], None, chatbot)
            
            # ========== 状态与统计标签页 ==========
            with gr.TabItem("📊 状态与统计"):
                status_display = gr.Markdown("点击下方按钮刷新状态")
                refresh_status_btn = gr.Button("刷新状态")
                
                def get_status_text():
                    status = creator.get_status()
                    memory_stats = status.get("memory_stats", {})
                    rag_stats = status.get("rag_stats", {})
                    short_term_stats = creator.get_short_term_stats()
                    tools_count = status.get("tools_count", 0)
                    
                    # 长期记忆统计
                    long_term = memory_stats.get("long_term", {})
                    long_term_total = long_term.get("total", 0)
                    long_term_categories = long_term.get("by_category", {})
                    category_str = ', '.join([f"{k}: {v}" for k, v in long_term_categories.items()]) if long_term_categories else "无"
                    
                    # RAG 统计
                    rag_doc_count = rag_stats.get("document_count", 0)
                    rag_docs = rag_stats.get("documents", [])
                    rag_doc_list = ', '.join(rag_docs[:5]) if rag_docs else "无"
                    if len(rag_docs) > 5:
                        rag_doc_list += f" 等{len(rag_docs)}个"
                    
                    return f"""
### Agent 信息
- **名称**: {status['name']}
- **状态**: {status['status']}
- **能力**: {', '.join(status['capabilities'])}
- **记忆目录**: {str(creator.memory.memory_dir)}

### LLM 配置
- **提供商**: {status.get('llm_provider', '未配置')}
- **模型**: {status.get('llm_model', '未配置')}

### 工具统计
- **已注册工具**: {tools_count} 个

### 短期记忆统计
- **消息条数**: {short_term_stats['message_count']} / {short_term_stats['max_messages']}
- **是否有摘要**: {'是' if short_term_stats['has_summary'] else '否'}
- **摘要长度**: {short_term_stats['summary_length']} 字符

### 长期记忆统计
- **总条数**: {long_term_total}
- **分类统计**: {category_str}

### RAG 知识库统计
- **文档数量**: {rag_doc_count}
- **文档列表**: {rag_doc_list}
"""
                
                refresh_status_btn.click(lambda: get_status_text(), None, status_display)
                
                gr.Markdown("---")
                gr.Markdown("### 短期记忆管理")
                
                short_term_stats_display = gr.Markdown("点击刷新查看")
                refresh_short_term_btn = gr.Button("刷新短期记忆统计")
                refresh_short_term_btn.click(
                    lambda: f"- **消息条数**: {creator.get_short_term_stats()['message_count']}\n- **最大条数**: {creator.get_short_term_stats()['max_messages']}\n- **是否有摘要**: {'是' if creator.get_short_term_stats()['has_summary'] else '否'}",
                    None,
                    short_term_stats_display
                )
                
                clear_short_term_btn = gr.Button("清空短期记忆", variant="stop")
                clear_short_term_result = gr.Markdown("")
                
                def clear_short_term():
                    creator.clear_short_term()
                    return "✅ 短期记忆已清空（包括摘要）"
                
                clear_short_term_btn.click(clear_short_term, None, clear_short_term_result)
            
            # ========== 长期记忆管理标签页 ==========
            with gr.TabItem("📝 长期记忆管理"):
                gr.Markdown("### 查看长期记忆")
                
                with gr.Row():
                    memory_limit = gr.Slider(5, 50, value=20, step=5, label="显示条数")
                    refresh_memory_btn = gr.Button("刷新记忆列表")
                
                memory_output = gr.Markdown("点击刷新按钮查看")
                
                def view_memories(limit=20):
                    memories = creator.memory.get_long_term_all(limit)
                    if not memories:
                        return "暂无记忆"
                    lines = []
                    for m in memories:
                        lines.append(f"**ID: {m['id']}** | 分类: {m['category']} | 重要性: {m['importance']} | 时间: {m['created_at'][:16]}")
                        lines.append(f"> {m['content'][:200]}")
                        lines.append("")
                    return "\n".join(lines)
                
                refresh_memory_btn.click(lambda l: view_memories(l), [memory_limit], [memory_output])
                
                gr.Markdown("### 删除记忆")
                gr.Markdown("输入记忆 ID 删除单条，或用逗号分隔多个 ID")
                
                with gr.Row():
                    delete_ids = gr.Textbox(label="记忆 ID（多个用逗号分隔）", placeholder="例如: 1 或 1,2,3", lines=1, scale=3)
                    delete_btn = gr.Button("删除选中", variant="stop", scale=1)
                
                delete_result = gr.Markdown("")
                
                def delete_memories(ids_str):
                    if not ids_str or not ids_str.strip():
                        return "请输入要删除的记忆 ID"
                    
                    try:
                        ids = [int(x.strip()) for x in ids_str.replace(',', ' ').split() if x.strip()]
                        if not ids:
                            return "未找到有效的 ID"
                        
                        if len(ids) == 1:
                            success = creator.delete_memory(ids[0])
                            if success:
                                return f"✅ 已删除记忆 ID: {ids[0]}"
                            else:
                                return f"❌ 未找到记忆 ID: {ids[0]}"
                        else:
                            count = creator.delete_memories_batch(ids)
                            return f"✅ 已删除 {count} 条记忆"
                    except ValueError:
                        return "❌ ID 格式错误，请输入数字"
                    except Exception as e:
                        return f"❌ 删除失败: {e}"
                
                delete_btn.click(delete_memories, [delete_ids], [delete_result])
                
                gr.Markdown("### 批量操作")
                
                with gr.Row():
                    category_dropdown = gr.Dropdown(
                        choices=["general", "preference", "knowledge"],
                        label="选择分类",
                        value="general"
                    )
                    clear_category_btn = gr.Button("清空选中分类", variant="stop")
                
                clear_result = gr.Markdown("")
                
                def clear_by_category(category):
                    if not category:
                        return "请选择分类"
                    count = creator.clear_memory_by_category(category)
                    return f"✅ 已清空分类 '{category}'，共 {count} 条"
                
                clear_category_btn.click(clear_by_category, [category_dropdown], [clear_result])
                
                gr.Markdown("---")
                
                clear_all_btn = gr.Button("清空所有长期记忆", variant="stop")
                clear_all_result = gr.Markdown("")
                
                def clear_all():
                    count = creator.clear_all_memory()
                    return f"✅ 已清空所有长期记忆，共 {count} 条"
                
                clear_all_btn.click(clear_all, None, [clear_all_result])
            
            # ========== RAG 知识库管理标签页 ==========
            with gr.TabItem("📚 RAG 知识库"):
                gr.Markdown("### RAG 知识库管理")
                gr.Markdown("知识库用于存储专业知识，LLM 会在回答时自动检索相关知识。")
                
                # 知识库统计
                rag_stats_display = gr.Markdown("加载中...")
                refresh_rag_stats_btn = gr.Button("刷新统计")
                
                def get_rag_stats():
                    stats = creator.get_knowledge_stats()
                    docs = stats.get('documents', [])
                    doc_list = '\n'.join([f"  - {d}" for d in docs]) if docs else "  无"
                    return f"""
### 知识库统计
- **文档数量**: {stats['document_count']}
- **文档列表**: 
{doc_list}
"""
                
                refresh_rag_stats_btn.click(get_rag_stats, None, rag_stats_display)
                
                gr.Markdown("---")
                gr.Markdown("### 搜索知识库")
                
                search_query = gr.Textbox(label="搜索关键词", placeholder="输入要搜索的内容...", lines=1)
                search_btn = gr.Button("搜索")
                search_result = gr.Markdown("")
                
                def search_knowledge(query):
                    if not query:
                        return "请输入搜索关键词"
                    results = creator.search_knowledge(query)
                    if not results:
                        return "未找到相关内容"
                    lines = []
                    for r in results:
                        lines.append(f"**来源: {r['source']}** (相关度: {r.get('score', 0)})")
                        lines.append(f"{r['content']}")
                        lines.append("---")
                    return "\n".join(lines)
                
                search_btn.click(search_knowledge, [search_query], [search_result])
                
                gr.Markdown("---")
                gr.Markdown("### 添加知识文档")
                
                doc_content = gr.Textbox(label="文档内容", lines=8, placeholder="输入要添加的知识内容...")
                doc_filename = gr.Textbox(label="文件名（可选）", placeholder="example.txt", lines=1)
                add_doc_btn = gr.Button("添加文档")
                add_doc_result = gr.Markdown("")
                
                def add_document(content, filename):
                    if not content:
                        return "请输入文档内容"
                    result = creator.add_knowledge_document(content, filename if filename else None)
                    return f"✅ 已添加文档: {result}"
                
                add_doc_btn.click(add_document, [doc_content, doc_filename], [add_doc_result])
                
                gr.Markdown("---")
                gr.Markdown("### 管理现有文档")
                
                # 文档列表
                doc_list_output = gr.Markdown("点击刷新查看文档列表")
                refresh_doc_list_btn = gr.Button("刷新文档列表")
                
                def list_documents():
                    docs = creator.get_all_knowledge_documents()
                    if not docs:
                        return "暂无文档"
                    lines = ["| 文件名 | 预览 | 创建时间 |"]
                    lines.append("|--------|------|----------|")
                    for doc in docs:
                        filename = doc.get('filename', doc.get('source', '未知'))
                        preview = doc.get('content_preview', '')[:50] + "..."
                        created = doc.get('created_at', '未知')
                        lines.append(f"| {filename} | {preview} | {created} |")
                    return "\n".join(lines)
                
                refresh_doc_list_btn.click(list_documents, None, doc_list_output)
                
                # 删除文档
                gr.Markdown("### 删除文档")
                delete_filename = gr.Textbox(label="文件名", placeholder="要删除的文件名", lines=1)
                delete_doc_btn = gr.Button("删除文档", variant="stop")
                delete_doc_result = gr.Markdown("")
                
                def delete_document(filename):
                    if not filename:
                        return "请输入文件名"
                    if creator.delete_knowledge_document(filename):
                        return f"✅ 已删除文档: {filename}"
                    return f"❌ 未找到文档: {filename}"
                
                delete_doc_btn.click(delete_document, [delete_filename], [delete_doc_result])
                
                gr.Markdown("---")
                
                reload_kb_btn = gr.Button("重新加载知识库", variant="secondary")
                reload_kb_result = gr.Markdown("")
                
                def reload_knowledge():
                    creator.reload_knowledge()
                    stats = creator.get_knowledge_stats()
                    return f"✅ 知识库已重新加载，共 {stats['document_count']} 个文档"
                
                reload_kb_btn.click(reload_knowledge, None, reload_kb_result)
    
    demo.launch(
        server_name="127.0.0.1",
        server_port=ui_port,
        share=False
    )


if __name__ == "__main__":
    main()