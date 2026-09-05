#!/usr/bin/env python3
"""LockCrypt — AES-256 file & folder encryption with secure delete."""

import os
import sys
import secrets
import shutil
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
import py7zr


def secure_delete(path: Path) -> None:
    # SSD wear-leveling means overwriting is best-effort, not guaranteed.
    # For true erasure on SSDs, use full-disk encryption (BitLocker).
    path = Path(path)
    if path.is_file():
        size = max(path.stat().st_size, 1)
        with open(path, "r+b") as f:
            f.write(secrets.token_bytes(size))
            f.flush()
            os.fsync(f.fileno())
        path.unlink()
    elif path.is_dir():
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                secure_delete(child)
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
        try:
            path.rmdir()
        except OSError:
            shutil.rmtree(path, ignore_errors=True)


class PasswordDialog(ctk.CTkToplevel):
    def __init__(self, parent, mode: str = "encrypt"):
        super().__init__(parent)
        self.title("Set Password" if mode == "encrypt" else "Enter Password")
        self.geometry("340x200" if mode == "encrypt" else "340x160")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.result: str | None = None
        self._mode = mode

        ctk.CTkLabel(self, text="Password:", font=ctk.CTkFont(size=13)).pack(pady=(18, 4))
        self._pw = ctk.CTkEntry(self, show="•", width=240, placeholder_text="Enter password")
        self._pw.pack()
        self._pw.focus()

        if mode == "encrypt":
            ctk.CTkLabel(self, text="Confirm password:", font=ctk.CTkFont(size=13)).pack(pady=(10, 4))
            self._confirm = ctk.CTkEntry(self, show="•", width=240, placeholder_text="Re-enter password")
            self._confirm.pack()
        else:
            self._confirm = None

        self._err = ctk.CTkLabel(self, text="", text_color="#e05555", font=ctk.CTkFont(size=11))
        self._err.pack(pady=(4, 0))

        ctk.CTkButton(self, text="OK", width=120, command=self._submit).pack(pady=(8, 0))
        self.bind("<Return>", lambda _: self._submit())

    def _submit(self):
        pw = self._pw.get()
        if not pw:
            self._err.configure(text="Password cannot be empty.")
            return
        if self._confirm is not None and pw != self._confirm.get():
            self._err.configure(text="Passwords do not match.")
            return
        self.result = pw
        self.destroy()


class LockCryptApp(TkinterDnD.Tk):
    def __init__(self, initial_paths: list[Path] | None = None, initial_mode: str = "encrypt"):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("LockCrypt")
        self.geometry("600x540")
        self.minsize(500, 460)
        self.configure(bg="#1a1a2e")

        self._queued: list[Path] = []
        self._mode = ctk.StringVar(value=initial_mode)
        self._delete_originals = ctk.BooleanVar(value=True)

        self._build_ui()

        for p in (initial_paths or []):
            self._add_path(p)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color="#12122a")
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header,
            text="LockCrypt",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#5ea7ff",
        ).pack(side="left", padx=22, pady=14)

        # Mode selector
        seg = ctk.CTkSegmentedButton(
            self,
            values=["encrypt", "decrypt"],
            variable=self._mode,
            command=self._on_mode_change,
            width=220,
            font=ctk.CTkFont(size=13),
        )
        seg.pack(pady=(14, 0))

        # Drop zone
        self._drop_frame = ctk.CTkFrame(
            self, corner_radius=14, border_width=2, border_color="#3a7ebf", fg_color="#0f1729"
        )
        self._drop_frame.pack(fill="both", expand=True, padx=20, pady=12)

        self._drop_label = ctk.CTkLabel(
            self._drop_frame,
            text="Drop files or folders here\n\nor click to browse",
            font=ctk.CTkFont(size=15),
            text_color="#5577aa",
        )
        self._drop_label.pack(expand=True)

        for widget in (self._drop_frame, self._drop_label):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.bind("<Button-1>", self._browse)
            widget.bind("<Enter>", lambda _: self._drop_frame.configure(border_color="#5ea7ff"))
            widget.bind("<Leave>", lambda _: self._drop_frame.configure(border_color="#3a7ebf"))

        # Queue summary
        self._queue_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color="#667799"
        )
        self._queue_label.pack(anchor="w", padx=22)

        # Options row
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.pack(fill="x", padx=20, pady=(2, 4))

        self._delete_cb = ctk.CTkCheckBox(
            opts,
            text="Securely delete originals",
            variable=self._delete_originals,
            font=ctk.CTkFont(size=12),
        )
        self._delete_cb.pack(side="left")
        ctk.CTkButton(
            opts,
            text="Clear",
            width=64,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color="#445566",
            font=ctk.CTkFont(size=12),
            command=self._clear,
        ).pack(side="right")

        # Progress bar (hidden until work starts)
        self._progress = ctk.CTkProgressBar(self, mode="indeterminate")

        # Action button
        self._action_btn = ctk.CTkButton(
            self,
            text=self._mode.get().capitalize(),
            height=44,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._run,
        )
        self._action_btn.pack(fill="x", padx=20, pady=(4, 6))

        # Log output
        self._log_box = ctk.CTkTextbox(
            self, height=108, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#0a0f1a"
        )
        self._log_box.pack(fill="x", padx=20, pady=(0, 14))
        self._log_box.configure(state="disabled")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_mode_change(self, value: str):
        self._action_btn.configure(text=value.capitalize())
        self._clear()

    def _on_drop(self, event):
        for p in self._parse_drop(event.data):
            self._add_path(Path(p))

    def _parse_drop(self, data: str) -> list[str]:
        """Handle tkinterdnd2 path strings: {path with spaces} or plain tokens."""
        paths, data = [], data.strip()
        while data:
            if data.startswith("{"):
                end = data.index("}")
                paths.append(data[1:end])
                data = data[end + 1:].strip()
            else:
                token, _, data = data.partition(" ")
                paths.append(token)
                data = data.strip()
        return paths

    def _browse(self, _event=None):
        if self._mode.get() == "encrypt":
            chosen = filedialog.askopenfilenames(title="Select files to encrypt")
        else:
            chosen = filedialog.askopenfilenames(
                title="Select archives to decrypt",
                filetypes=[("7-Zip archives", "*.7z"), ("All files", "*.*")],
            )
        for p in chosen:
            self._add_path(Path(p))

    # ── Queue management ──────────────────────────────────────────────────────

    def _add_path(self, path: Path):
        if path not in self._queued:
            self._queued.append(path)
            self._refresh_queue()

    def _refresh_queue(self):
        n = len(self._queued)
        if n == 0:
            self._queue_label.configure(text="")
            self._drop_label.configure(text="Drop files or folders here\n\nor click to browse")
            return
        names = [p.name for p in self._queued]
        preview = ", ".join(names[:3]) + (f"  +{n - 3} more" if n > 3 else "")
        self._queue_label.configure(text=f"{n} item(s) queued:  {preview}")
        self._drop_label.configure(text=f"{n} item(s) ready\n\nDrop more or click to add")

    def _clear(self):
        self._queued.clear()
        self._refresh_queue()
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    # ── Encryption / decryption ───────────────────────────────────────────────

    def _run(self):
        if not self._queued:
            self._log("Nothing queued. Drop some files first.")
            return

        dialog = PasswordDialog(self, mode=self._mode.get())
        self.wait_window(dialog)
        if not dialog.result:
            return

        paths = list(self._queued)
        mode = self._mode.get()
        delete = self._delete_originals.get()
        password = dialog.result

        self._action_btn.configure(state="disabled")
        self._progress.pack(fill="x", padx=20, pady=(0, 4), before=self._action_btn)
        self._progress.start()

        threading.Thread(
            target=self._worker, args=(paths, password, mode, delete), daemon=True
        ).start()

    def _worker(self, paths: list[Path], password: str, mode: str, delete: bool):
        for path in paths:
            try:
                if mode == "encrypt":
                    self._encrypt(path, password, delete)
                else:
                    self._decrypt(path, password, delete)
            except Exception as exc:
                self.after(0, self._log, f"  ERROR — {path.name}: {exc}")
        self.after(0, self._finish)

    def _encrypt(self, source: Path, password: str, delete: bool):
        out = self._unique_path(
            source.with_suffix(".7z") if source.is_file() else source.parent / (source.name + ".7z")
        )
        self.after(0, self._log, f"Encrypting  {source.name}  →  {out.name}")
        with py7zr.SevenZipFile(out, "w", password=password) as arc:
            if source.is_file():
                arc.write(source, source.name)
            else:
                arc.writeall(source, source.name)
        if delete:
            self.after(0, self._log, f"  Securely deleting  {source.name}")
            secure_delete(source)
        self.after(0, self._log, f"  Done  →  {out}")

    def _decrypt(self, source: Path, password: str, delete: bool):
        self.after(0, self._log, f"Decrypting  {source.name}  →  {source.parent}/")
        with py7zr.SevenZipFile(source, "r", password=password) as arc:
            arc.extractall(path=source.parent)
        if delete:
            self.after(0, self._log, f"  Securely deleting  {source.name}")
            secure_delete(source)
        self.after(0, self._log, f"  Done  →  {source.parent}")

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem, i = path.stem, 1
        while path.exists():
            path = path.with_name(f"{stem}_{i}{path.suffix}")
            i += 1
        return path

    def _finish(self):
        self._progress.stop()
        self._progress.pack_forget()
        self._action_btn.configure(state="normal")
        self._log("─" * 40)
        self._queued.clear()
        self._refresh_queue()


if __name__ == "__main__":
    args = sys.argv[1:]
    initial_mode = "decrypt" if "--decrypt" in args else "encrypt"
    initial = [Path(p) for p in args if not p.startswith("--") and Path(p).exists()]
    app = LockCryptApp(initial_paths=initial, initial_mode=initial_mode)
    app.mainloop()
