"""A distinct entry-point name avoids shadowing the local_control package."""
from local_control.cli import entry

if __name__ == '__main__':
    entry()
