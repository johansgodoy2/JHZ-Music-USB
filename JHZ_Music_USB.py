import os
import sys
import shutil
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

import yt_dlp


APP_NAME = "JHZ Music USB"


def get_ffmpeg_location():
    """Encuentra FFmpeg incluido en el EXE o instalado en el sistema."""

    if getattr(sys, "frozen", False):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))

        ffmpeg = os.path.join(base_path, "ffmpeg.exe")
        ffprobe = os.path.join(base_path, "ffprobe.exe")

        if os.path.isfile(ffmpeg) and os.path.isfile(ffprobe):
            return base_path

    local_vendor = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "vendor"
    )

    ffmpeg = os.path.join(local_vendor, "ffmpeg.exe")
    ffprobe = os.path.join(local_vendor, "ffprobe.exe")

    if os.path.isfile(ffmpeg) and os.path.isfile(ffprobe):
        return local_vendor

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return None

    return None


class QueueLogger:
    def __init__(self, events):
        self.events = events

    def debug(self, message):
        pass

    def warning(self, message):
        self.events.put(("log", "Aviso: " + str(message)))

    def error(self, message):
        self.events.put(("log", "Error: " + str(message)))


class JHZMusicUSB:

    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("650x540")
        self.root.minsize(580, 480)

        self.events = queue.Queue()
        self.downloading = False

        self.destination = tk.StringVar()
        self.url = tk.StringVar()
        self.quality = tk.StringVar(value="320")

        self.create_interface()
        self.root.after(100, self.process_events)

    def create_interface(self):

        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="JHZ MUSIC USB",
            font=("Arial", 22, "bold")
        )
        title.pack(pady=(0, 5))

        subtitle = ttk.Label(
            main,
            text="Descarga y convierte tu música a MP3"
        )
        subtitle.pack(pady=(0, 20))

        ttk.Label(main, text="Enlace de YouTube:").pack(anchor="w")

        self.url_entry = ttk.Entry(
            main,
            textvariable=self.url
        )
        self.url_entry.pack(fill="x", pady=(5, 12))

        ttk.Label(main, text="Carpeta de destino:").pack(anchor="w")

        folder_frame = ttk.Frame(main)
        folder_frame.pack(fill="x", pady=(5, 12))

        self.folder_entry = ttk.Entry(
            folder_frame,
            textvariable=self.destination
        )
        self.folder_entry.pack(side="left", fill="x", expand=True)

        self.folder_button = ttk.Button(
            folder_frame,
            text="Examinar",
            command=self.select_folder
        )
        self.folder_button.pack(side="right", padx=(8, 0))

        ttk.Label(main, text="Calidad del MP3:").pack(anchor="w")

        quality_box = ttk.Combobox(
            main,
            textvariable=self.quality,
            values=["128", "192", "256", "320"],
            state="readonly",
            width=12
        )
        quality_box.pack(anchor="w", pady=(5, 15))

        self.start_button = ttk.Button(
            main,
            text="DESCARGAR MÚSICA",
            command=self.start_download
        )
        self.start_button.pack(fill="x", ipady=7, pady=(0, 15))

        self.status_label = ttk.Label(
            main,
            text="Esperando descarga..."
        )
        self.status_label.pack(anchor="w")

        self.progress = ttk.Progressbar(
            main,
            mode="determinate",
            maximum=100
        )
        self.progress.pack(fill="x", pady=(7, 15))

        ttk.Label(main, text="Registro de actividad:").pack(anchor="w")

        self.log_box = ScrolledText(
            main,
            height=11,
            state="disabled",
            font=("Consolas", 9)
        )
        self.log_box.pack(fill="both", expand=True, pady=(5, 0))

        footer = ttk.Label(
            main,
            text="JHZ Music USB | Conversión automática a MP3"
        )
        footer.pack(pady=(12, 0))

    def select_folder(self):

        folder = filedialog.askdirectory(
            title="Selecciona la carpeta de tu pendrive"
        )

        if folder:
            self.destination.set(folder)

    def log(self, message):

        self.log_box.configure(state="normal")
        self.log_box.insert("end", str(message) + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start_download(self):

        if self.downloading:
            return

        url = self.url.get().strip()
        destination = self.destination.get().strip()

        if not url:
            messagebox.showwarning(
                APP_NAME,
                "Introduce un enlace de YouTube."
            )
            return

        if not destination:
            messagebox.showwarning(
                APP_NAME,
                "Selecciona la carpeta de destino."
            )
            return

        if not os.path.isdir(destination):
            messagebox.showerror(
                APP_NAME,
                "La carpeta de destino no existe."
            )
            return

        if not os.access(destination, os.W_OK):
            messagebox.showerror(
                APP_NAME,
                "No se puede escribir en esta carpeta."
            )
            return

        self.downloading = True
        self.start_button.configure(state="disabled")
        self.folder_button.configure(state="disabled")
        self.progress["value"] = 0
        self.status_label.configure(text="Preparando descarga...")

        self.log("Iniciando proceso...")
        self.log("Destino: " + destination)

        thread = threading.Thread(
            target=self.download_worker,
            args=(url, destination, self.quality.get()),
            daemon=True
        )
        thread.start()

    def download_worker(self, url, destination, quality):

        archive = os.path.join(
            destination,
            ".jhz_downloaded.txt"
        )

        ffmpeg_location = get_ffmpeg_location()

        if ffmpeg_location is None and not (
            shutil.which("ffmpeg") and shutil.which("ffprobe")
        ):
            self.events.put((
                "error",
                "No se encontró FFmpeg. Comprueba la compilación."
            ))
            return

        def progress_hook(data):

            if data.get("status") == "downloading":

                total = (
                    data.get("total_bytes")
                    or data.get("total_bytes_estimate")
                )

                downloaded = data.get("downloaded_bytes", 0)

                if total:
                    percentage = downloaded / total * 100

                    self.events.put((
                        "progress",
                        percentage,
                        "Descargando..."
                    ))

            elif data.get("status") == "finished":

                self.events.put((
                    "progress",
                    100,
                    "Convirtiendo a MP3..."
                ))

        options = {
            "format": "bestaudio/best",

            "outtmpl": os.path.join(
                destination,
                "%(title).180B [%(id)s].%(ext)s"
            ),

            "noplaylist": False,
            "ignoreerrors": True,
            "nooverwrites": True,
            "continuedl": True,
            "download_archive": archive,

            "writethumbnail": False,
            "write_all_thumbnails": False,
            "embedthumbnail": False,

            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": quality,
                }
            ],

            "keepvideo": False,

            "progress_hooks": [progress_hook],

            "logger": QueueLogger(self.events),

            "quiet": True,
            "noprogress": True,
        }

        if ffmpeg_location:
            options["ffmpeg_location"] = ffmpeg_location

        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.download([url])

            self.events.put(("finished", None))

        except Exception as error:
            self.events.put(("error", str(error)))

    def process_events(self):

        try:
            while True:
                event = self.events.get_nowait()
                event_type = event[0]

                if event_type == "log":
                    self.log(event[1])

                elif event_type == "progress":
                    percentage = event[1]
                    status = event[2]

                    self.progress["value"] = percentage
                    self.status_label.configure(text=status)

                elif event_type == "finished":
                    self.downloading = False

                    self.progress["value"] = 100
                    self.status_label.configure(
                        text="Proceso finalizado."
                    )

                    self.log("Proceso finalizado.")
                    self.log("Revisa tu carpeta de destino.")

                    self.start_button.configure(state="normal")
                    self.folder_button.configure(state="normal")

                    messagebox.showinfo(
                        APP_NAME,
                        "El proceso de descarga ha terminado."
                    )

                elif event_type == "error":
                    self.downloading = False

                    self.status_label.configure(
                        text="Se produjo un error."
                    )

                    self.log("ERROR: " + event[1])

                    self.start_button.configure(state="normal")
                    self.folder_button.configure(state="normal")

                    messagebox.showerror(
                        APP_NAME,
                        "No se pudo completar el proceso:\n\n"
                        + event[1]
                    )

        except queue.Empty:
            pass

        self.root.after(100, self.process_events)


if __name__ == "__main__":

    root = tk.Tk()
    app = JHZMusicUSB(root)
    root.mainloop()
