"""记忆管理组件 - 通用版本"""

from nicegui import ui
from typing import Dict, Any, List, Callable


def render_memory_view(
    memory,
    knowledge_base,
    fetch_long_term: Callable,
    delete_memory_fn: Callable,
    fetch_rag: Callable,
    delete_rag_fn: Callable,
    on_back: Callable
):
    """渲染记忆管理视图"""
    with ui.column().classes("w-full gap-4 p-4"):
        ui.label("📝 记忆管理").classes("text-2xl font-bold")

        # ===== 固定记忆 =====
        with ui.expansion("📌 固定记忆 (permanent.yaml)", icon="pin_drop").classes("w-full"):
            try:
                permanent = memory.permanent._data
                if permanent:
                    for key, value in permanent.items():
                        ui.label(f"**{key}**").classes("font-bold text-sm")
                        ui.label(str(value)[:500] + ("..." if len(str(value)) > 500 else "")).classes(
                            "text-sm text-gray-600 whitespace-pre-wrap"
                        )
                        ui.separator()
                else:
                    ui.label("固定记忆为空，请配置对应目录下的 permanent.yaml").classes("text-gray-400")
            except Exception as e:
                ui.label(f"读取固定记忆失败: {e}").classes("text-red-500")

        # ===== 长期记忆 =====
        with ui.expansion("💾 长期记忆", icon="storage").classes("w-full"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("所有已保存的长期记忆").classes("text-sm text-gray-500")
                ui.button("刷新", on_click=lambda: render_memory_view(
                    memory, knowledge_base, fetch_long_term, delete_memory_fn,
                    fetch_rag, delete_rag_fn, on_back
                )).props("flat size=sm")

            memories = fetch_long_term(50)
            if not memories:
                ui.label("暂无长期记忆").classes("text-gray-400 py-4")
            else:
                categories = list(set(m.get("category", "general") for m in memories))
                selected_category = ui.select(
                    categories + ["全部"],
                    value="全部",
                    label="分类筛选"
                ).classes("w-48")

                memory_container = ui.column().classes("w-full gap-2 mt-2")

                def refresh_memory_list():
                    memory_container.clear()
                    with memory_container:
                        cat = selected_category.value
                        filtered = memories if cat == "全部" else [m for m in memories if m.get("category", "general") == cat]
                        for m in filtered:
                            with ui.row().classes("w-full justify-between items-center border-b border-gray-100 py-2"):
                                with ui.column().classes("flex-1"):
                                    ui.label(m.get("content", "")[:200]).classes("text-sm")
                                    with ui.row().classes("gap-4 text-xs text-gray-400"):
                                        ui.label(f"ID: {m.get('id')}")
                                        ui.label(f"分类: {m.get('category', 'general')}")
                                        ui.label(f"重要性: {m.get('importance', 0.5)}")
                                        ui.label(f"创建: {m.get('created_at', '')[:16]}")
                                ui.button(
                                    "删除",
                                    on_click=lambda mid=m.get('id'): delete_memory_and_refresh(mid),
                                    color="red"
                                ).props("flat dense size=sm")

                selected_category.on('change', refresh_memory_list)
                refresh_memory_list()

                def delete_memory_and_refresh(memory_id):
                    if delete_memory_fn(memory_id):
                        ui.notify(f"✅ 已删除记忆 ID: {memory_id}", type="positive")
                        refresh_memory_list()
                    else:
                        ui.notify("❌ 删除失败", type="negative")

        # ===== RAG知识库 =====
        with ui.expansion("📚 RAG 知识库", icon="book").classes("w-full"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("知识文档列表").classes("text-sm text-gray-500")
                ui.button("刷新", on_click=lambda: render_memory_view(
                    memory, knowledge_base, fetch_long_term, delete_memory_fn,
                    fetch_rag, delete_rag_fn, on_back
                )).props("flat size=sm")

            docs = fetch_rag()
            if not docs:
                ui.label("暂无知识文档").classes("text-gray-400 py-4")
            else:
                for doc in docs:
                    with ui.row().classes("w-full justify-between items-center border-b border-gray-100 py-2"):
                        with ui.column().classes("flex-1"):
                            filename = doc.get("filename", doc.get("source", "未知"))
                            ui.label(filename).classes("text-sm font-mono")
                            preview = doc.get("content_preview", "")
                            if preview:
                                ui.label(preview[:100] + ("..." if len(preview) > 100 else "")).classes(
                                    "text-xs text-gray-400"
                                )
                            ui.label(f"创建: {doc.get('created_at', '未知')}").classes("text-xs text-gray-400")
                        ui.button(
                            "删除",
                            on_click=lambda f=filename: delete_rag_and_refresh(f),
                            color="red"
                        ).props("flat dense size=sm")

        ui.button("← 返回对话", on_click=on_back).props("flat size=sm")

    def delete_rag_and_refresh(filename: str):
        if delete_rag_fn(filename):
            ui.notify(f"✅ 已删除文档: {filename}", type="positive")
            render_memory_view(memory, knowledge_base, fetch_long_term, delete_memory_fn,
                             fetch_rag, delete_rag_fn, on_back)
        else:
            ui.notify("❌ 删除失败", type="negative")