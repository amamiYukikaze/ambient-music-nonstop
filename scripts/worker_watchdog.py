"""Do not leave a GPU worker alive after its owning service has exited."""
import os
import threading
import time
import psutil


def start():
    parent=os.environ.get('AMBIENT_PARENT_PID')
    if not parent:return
    pid=int(parent)
    try:created=psutil.Process(pid).create_time()
    except psutil.NoSuchProcess:os._exit(2)
    def watch():
        while True:
            time.sleep(1)
            try:
                if psutil.Process(pid).create_time()!=created:os._exit(2)
            except psutil.NoSuchProcess:os._exit(2)
    threading.Thread(target=watch,daemon=True).start()
