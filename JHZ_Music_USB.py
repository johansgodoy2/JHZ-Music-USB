import os
import sys
import queue
import threading
import string
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


APP_NAME = "JHZ Music USB"


class MusicUSBApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("700x560")
        self.root.minsize(620, 500)
        self.events = queue.Queue()
        self.worker = None
        self.running = False

        self.url_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.quality_var = tk.StringVar(value="192")
        self.status_var = tk.StringVar(value="Listo para comenzar.")
        self.progress_var = tk.DoubleVar(value=0)

        self.build_ui()
        self.refresh_drives()
        self.root.after(150, self.process_events)

    def build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="JHZ Music USB", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Convierte playlists en archivos MP3 individuales y guárdalos en tu USB.",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(4, 0))

        ttk.Label(outer, text="1. Enlace de YouTube o playlist", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.url_entry = ttk.Entry(outer, textvariable=self.url_var, font=("Segoe UI", 10))
        self.url_entry.pack(fill="x", pady=(6, 16))
        self.url_entry.focus_set()

        ttk.Label(outer, text="2. Carpeta de destino (elige tu pendrive)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        dest_row = ttk.Frame(outer)
        dest_row.pack(fill="x", pady=(6, 16))
        self.dest_entry = ttk.Entry(dest_row, textvariable=self.dest_var)
        self.dest_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(dest_row, text="Examinar…", command=self.choose_folder).pack(side="left", padx=(8, 0))
        ttk.Button(dest_row, text="Detectar USB", command=self.refresh_drives).pack(side="left", padx=(8, 0))

        ttk.Label(outer, text="3. Calidad MP3", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        quality_row = ttk.Frame(outer)
        quality_row.pack(fill="x", pady=(6, 16))
        quality = ttk.Combobox(
            quality_row, textvariable=self.quality_var,
            values=["128", "192", "256", "320"], state="readonly", width=10
        )
        quality.pack(side="left")
        ttk.Label(quality_row, text="kbps  ·  192 kbps es una buena opción general.").pack(side="left", padx=10)

        ttk.Separator(outer).pack(fill="x", pady=8)
        self.start_button = ttk.Button(outer, text="COMENZAR DESCARGA Y COPIA", command=self.start)
        self.start_button.pack(fill="x", ipady=9, pady=(8, 12))

        self.progress = ttk.Progressbar(outer, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress.pack(fill="x", pady=(2, 7))
        ttk.Label(outer, textvariable=self.status_var, wraplength=640).pack(anchor="w")

        self.log = tk.Text(outer, height=9, wrap="word", font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True, pady=(12, 0))

        footer = (
            "Nota: los MP3 se guardan directamente en la carpeta elegida. "
            "Las canciones descargadas anteriormente se omiten cuando sea posible."
        )
        ttk.Label(outer, text=footer, wraplength=640, foreground="#666666").pack(anchor="w", pady=(10, 0))

    def add_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Selecciona una carpeta del pendrive")
        if folder:
            self.dest_var.set(folder)

    def refresh_drives(self):
        drives = []
        if os.name == "nt":
            for letter in string.ascii_uppercase:
                path = f"{letter}:\\"
                if os.path.exists(path):
                    drives.append(path)
        if drives:
            self.add_log("Unidades detectadas: " + ", ".join(drives))
            if not self.dest_var.get():
                # No se elige automáticamente: el usuario confirma el destino.
                self.status_var.set("Unidades detectadas. Selecciona la carpeta de tu pendrive.")
        else:
            self.add_log("No se detectaron unidades extraíbles automáticamente. Puedes usar Examinar…")

    def start(self):
        if yt_dlp is None:
            messagebox.showerror(
                "Falta yt-dlp",
                "No está instalado yt-dlp. Ejecuta primero INSTALAR.bat dentro de la carpeta del programa."
            )
            return
        url = self.url_var.get().strip()
        dest = self.dest_var.get().strip()
        if not url:
            messagebox.showwarning("Falta el enlace", "Pega el enlace de un video o playlist de YouTube.")
            return
        if not dest or not os.path.isdir(dest):
            messagebox.showwarning("Destino no válido", "Selecciona una carpeta existente del pendrive.")
            return
        if not os.access(dest, os.W_OK):
            messagebox.showerror("Sin permisos", "No se puede escribir en la carpeta seleccionada.")
            return
        if self.running:
            return

        self.running = True
        self.start_button.configure(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("Iniciando…")
        self.add_log("Iniciando tarea. Los archivos MP3 se guardarán en: " + dest)

        self.worker = threading.Thread(
            target=self.download_worker,
            args=(url, dest, self.quality_var.get()),
            daemon=True
        )
        self.worker.start()

    def download_worker(self, url, dest, quality):
        archive = os.path.join(dest, ".jhz_music_usb_archive.txt")

        def hook(data):
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes", 0)
                percent = (downloaded / total * 100) if total else 0
                name = os.path.basename(data.get("filename", ""))
                self.events.put(("progress", percent, f"Descargando: {name[:75]}"))
            elif status == "finished":
                name = os.path.basename(data.get("filename", ""))
                self.events.put(("log", "Audio descargado; convirtiendo a MP3: " + name))

        def logger_message(message):
            self.events.put(("log", str(message).strip()))

        options = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(dest, "%(title)s.%(ext)s"),
            "noplaylist": False,
            "ignoreerrors": True,
            "nooverwrites": True,
            "continuedl": True,
            "windowsfilenames": True,
            "download_archive": archive,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }],
            "progress_hooks": [hook],
            "logger": type("QueueLogger", (), {
                "debug": lambda _self, msg: None,
                "warning": lambda _self, msg: logger_message("Aviso: " + msg),
                "error": lambda _self, msg: logger_message("Error: " + msg),
            })(),
            "quiet": True,
            "noprogress": True,
            "extract_flat": False,
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
            if info is None:
                self.events.put(("done", False, "No se pudo procesar el enlace. Comprueba que sea válido y accesible."))
            else:
                self.events.put(("progress", 100, "Proceso terminado."))
                self.events.put(("done", True, "Tarea finalizada. Revisa los archivos MP3 en tu pendrive."))
        except Exception as exc:
            self.events.put(("done", False, f"No se pudo completar la tarea: {exc}"))

    def process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self.progress_var.set(max(0, min(100, event[1])))
                    self.status_var.set(event[2])
                elif kind == "log":
                    self.add_log(event[1])
                elif kind == "done":
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.status_var.set(event[2])
                    self.add_log(event[2])
                    if event[1]:
                        messagebox.showinfo("JHZ Music USB", event[2])
                    else:
                        messagebox.showerror("JHZ Music USB", event[2] + "\n\nComprueba que FFmpeg esté instalado y que el enlace sea accesible.")
        except queue.Empty:
            pass
        self.root.after(150, self.process_events)


def main():
    root = tk.Tk()
    MusicUSBApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
