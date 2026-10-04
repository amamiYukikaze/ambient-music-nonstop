"""Windows 3.11 has reparse attributes but no Path.is_junction()."""
import stat
from pathlib import Path


def is_link(path):
    try:
        info=Path(path).lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0))


def reject_links(path):
    path=Path(path).absolute()
    if any(is_link(p) for p in [path,*path.parents]):
        raise ValueError('路径暂不支持符号链接或目录联接')
