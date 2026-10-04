"""OS-owned exclusive lease: released automatically even if the producer crashes."""
from .config import DATA


class InferenceLease:
    def __enter__(self):
        self.file=(DATA/'inference.lock').open('a+b')
        self.file.seek(0,2)
        if self.file.tell()==0:self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:
            import msvcrt
            msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.file.close();raise BlockingIOError('Another producer owns inference')
        return self
    def __exit__(self,*args):
        import msvcrt
        self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1);self.file.close()
