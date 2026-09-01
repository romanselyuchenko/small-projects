import tkinter as tk
import time
import threading
import subprocess


class Stopwatch:
    def __init__(self, root):
        self.root = root
        self.root.title("Stopwatch")
        self.root.geometry("500x180")

        self.running = False
        self.start_time = 0
        self.elapsed = 0

        self.last_announced = None

        self.label = tk.Label(
            root,
            text="00:00",
            font=("Arial", 64)
        )
        self.label.pack(expand=True)

        self.info = tk.Label(
            root,
            text="Space — start/pause"
        )
        self.info.pack()

        self.root.bind("<space>", self.toggle)

        self.update_display()

    def speak_worker(self, text):
        cmd = (
            "Add-Type -AssemblyName System.Speech; "
            f'(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{text}")'
        )

        subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True
        )

    def speak(self, text):
        threading.Thread(
            target=self.speak_worker,
            args=(text,),
            daemon=True
        ).start()

    def toggle(self, event=None):
        if self.running:
            self.elapsed += time.perf_counter() - self.start_time
            self.running = False
        else:
            self.start_time = time.perf_counter()
            self.running = True

    def update_display(self):
        total = self.elapsed

        if self.running:
            total += time.perf_counter() - self.start_time

        total_seconds = int(total)

        minutes = total_seconds // 60
        seconds = total_seconds % 60

        self.label.config(
            text=f"{minutes:02}:{seconds:02}"
        )

        if self.running and total_seconds % 30 == 0:
            if total_seconds != self.last_announced:
                self.last_announced = total_seconds

                print("ANNOUNCE:", total_seconds)

                self.speak(f"{minutes} {seconds}")

        self.root.after(100, self.update_display)


root = tk.Tk()
app = Stopwatch(root)
root.mainloop()