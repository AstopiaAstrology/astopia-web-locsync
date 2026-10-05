"""Three-way structural merge; never silently resolve conflicting leaf edits."""
import sys
from .json_io import load, write

MISSING = object()


def merge(base, ours, theirs, path=""):
    if ours == theirs:
        return ours
    if ours == base:
        return theirs
    if theirs == base:
        return ours
    if all(isinstance(v, dict) for v in (base, ours, theirs)):
        result = {}
        for key in sorted(set(base) | set(ours) | set(theirs)):
            value = merge(base.get(key, MISSING), ours.get(key, MISSING),
                          theirs.get(key, MISSING), path + "/" + key)
            if value is not MISSING:
                result[key] = value
        return result
    # Independent additions under a new namespace.
    if base is MISSING and isinstance(ours, dict) and isinstance(theirs, dict):
        return merge({}, ours, theirs, path)
    raise ValueError(f"JSON merge conflict: {path}")


def main():
    try:
        base, ours, theirs = sys.argv[1:4]
        result = merge(load(base), load(ours), load(theirs))
        write(ours, result)
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
