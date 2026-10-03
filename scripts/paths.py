"""Filesystem boundary checks, including Windows reparse points on Python 3.11."""
import stat
from pathlib import Path


def is_link(path):
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def no_links(path):
    for part in (Path(path), *Path(path).parents):
        if is_link(part):
            raise ValueError('Paths must not traverse symbolic links, junctions or reparse points')
