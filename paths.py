"""Find our files regardless of how they got into the repo.

The web upload flattens folders, so the same code has to run whether it
sits at tools/vivios/ with a data/ subfolder or loose at the repo root
next to its json. Nothing here is clever, it just looks in the places the
files can actually be instead of assuming one layout.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def find_file(name, extra=()):
    """Locate a data file by name. Returns an absolute path or raises."""
    seen = []
    for base in (HERE, os.path.dirname(HERE)) + tuple(extra):
        for sub in ("data", "", os.path.join("tools", "vivios", "data")):
            p = os.path.join(base, sub, name) if sub else os.path.join(base, name)
            seen.append(p)
            if os.path.isfile(p):
                return os.path.abspath(p)
    raise FileNotFoundError("could not find %s. Looked in:\n  %s"
                            % (name, "\n  ".join(seen)))


def repo_root(slug):
    """The directory that contains the client page folder."""
    d = HERE
    for _ in range(5):
        if os.path.isdir(os.path.join(d, slug)) or os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return HERE
