import tkinter as tk
import json
import os
import re
from tkinter import messagebox

SAVE_FILE = "sticky_notes.json"

class NoteManager:
    def __init__(self, app):
        self.app = app

    @staticmethod
    def load_notes_list():
        """读取所有便笺的 JSON 文件"""
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (json.JSONDecodeError, TypeError) as e:
                print(f"⚠️ JSON 文件损坏，自动重置：{e}")
                return {}
        return {}

    @staticmethod
    def cleanup_unused_images():
        """
        遍历所有便笺，收集其中的 [[IMG:...]] 路径，与 sticky_notes_images 文件夹下的文件对比，
        如果有文件不在引用列表中，则删除它。
        """
        from Note import IMAGE_FOLDER
        data = NoteManager.load_notes_list()
        all_references = set()

        pattern = re.compile(r"\[\[IMG:(.*?)\]\]")
        for note_id, note_info in data.items():
            text = note_info.get("text", "")
            matches = pattern.findall(text)
            for m in matches:
                possible_abs = os.path.abspath(m)
                if os.path.exists(possible_abs):
                    all_references.add(os.path.abspath(possible_abs))
                else:
                    alt_path = os.path.abspath(os.path.join(IMAGE_FOLDER, m))
                    if os.path.exists(alt_path):
                        all_references.add(alt_path)

        if os.path.exists(IMAGE_FOLDER) and os.path.isdir(IMAGE_FOLDER):
            for f in os.listdir(IMAGE_FOLDER):
                full_path = os.path.abspath(os.path.join(IMAGE_FOLDER, f))
                if full_path not in all_references:
                    try:
                        os.remove(full_path)
                        print(f"已删除未被引用的图片: {full_path}")
                    except Exception as e:
                        print(f"删除图片失败: {full_path}，原因: {e}")

    def save_note(self):
        """
        1) 获取纯文本（含 [[IMG:...]]）和所有标签区间（bold, italic, bold_italic, underline）
        2) 存入 JSON
        3) cleanup_unused_images
        """
        widget = self.app.text_widget
        content = widget.get("1.0", tk.END).rstrip("\n")

        # 如果文本全空，就不保存
        if not content.strip():
            return

        data = self.load_notes_list()
        if not isinstance(data, dict):
            data = {}

        note_id_str = str(self.app.note_id)
        existing = data.get(note_id_str, {})
        name = existing.get("name", None)

        # 提取所有标签区间，包括下划线
        tag_info = {
            "bold": self._get_tag_ranges(widget, "bold"),
            "italic": self._get_tag_ranges(widget, "italic"),
            "bold_italic": self._get_tag_ranges(widget, "bold_italic"),
            "underline": self._get_tag_ranges(widget, "underline"),
            "strikethrough": self._get_tag_ranges(widget, "strikethrough")

        }

        # 同时保存 is_pinned, text_bg, text_fg
        data[note_id_str] = {
            "text": content,
            "header_bg": self.app.header_bg,
            "is_pinned": self.app.is_pinned,
            "text_bg": self.app.text_bg,
            "text_fg": self.app.text_fg,
            "tag_info": tag_info
        }
        if name is not None:
            data[note_id_str]["name"] = name

        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        self.cleanup_unused_images()

    def load_note(self):
        """
        1) 加载纯文本并插入（这会还原图片位置）
        2) 若有 tag_info，则重新给相应区间加上 bold/italic/bold_italic/underline
        3) 恢复 header_bg, is_pinned, text_bg, text_fg 并刷新 UI
        """
        data = self.load_notes_list()
        if self.app.note_id in data:
            note = data[self.app.note_id]
            # 1) 纯文本 + 图片
            self.app.load_content(note.get("text", ""))

            # 2) 恢复标签
            tag_info = note.get("tag_info", {})
            self._apply_tag_info(self.app.text_widget, tag_info)

            # 3) 恢复外观
            self.app.header_bg = note.get("header_bg", self.app.header_bg)
            self.app.is_pinned = note.get("is_pinned", self.app.is_pinned)
            self.app.text_bg   = note.get("text_bg", self.app.text_bg)
            self.app.text_fg   = note.get("text_fg", self.app.text_fg)

            # 应用标题栏颜色
            self.app.header.config(bg=self.app.header_bg)
            if hasattr(self.app, "_refresh_header_buttons"):
                self.app._refresh_header_buttons()

            if hasattr(self.app, "_ensure_topmost_state"):
                self.app._ensure_topmost_state()

            self.app.text_widget.config(bg=self.app.text_bg, fg=self.app.text_fg,
                                        insertbackground=self.app.text_fg)

    def delete_note(self):
        """删除当前便笺后，调用 cleanup_unused_images 清理不再使用的图片。"""
        if messagebox.askyesno("删除便笺", "确定删除此便笺吗？"):
            data = self.load_notes_list()
            if self.app.note_id in data:
                del data[self.app.note_id]
                with open(SAVE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            self.app.root.destroy()
            self.cleanup_unused_images()

    # ------------------ 以下是提取和还原标签的辅助函数 ------------------
    def _get_tag_ranges(self, widget, tag_name):
        """
        提取 tag_name 在 widget 中的所有区间，
        返回 [ [start_offset, end_offset], ... ]；使用字符偏移计数
        """
        result = []
        ranges = widget.tag_ranges(tag_name)
        for i in range(0, len(ranges), 2):
            start_i = ranges[i]
            end_i = ranges[i + 1]
            try:
                valid_start = widget.index(start_i)
                valid_end = widget.index(end_i)
            except tk.TclError:
                continue
            if not valid_start or not valid_end:
                continue
            start_vals = widget.count("1.0", valid_start, "chars")
            end_vals = widget.count("1.0", valid_end, "chars")
            if not start_vals or not end_vals:
                continue
            start_off = start_vals[0]
            end_off = end_vals[0]
            if end_off > start_off:
                result.append([start_off, end_off])
        return result

    def _apply_tag_info(self, widget, tag_info):
        """
        根据保存的 tag_info 恢复所有标签
        tag_info 结构示例:
        {
          "bold": [ [start_off, end_off], ... ],
          "italic": [ ... ],
          "bold_italic": [ ... ],
          "underline": [ ... ]
        }
        """
        for tag_name, ranges_list in tag_info.items():
            for (start_off, end_off) in ranges_list:
                if end_off > start_off:
                    start_idx = widget.index(f"1.0+{start_off}c")
                    end_idx   = widget.index(f"1.0+{end_off}c")
                    widget.tag_add(tag_name, start_idx, end_idx)
