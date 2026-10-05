"""Strict JSON messages; dot paths are deliberately unambiguous."""
import json
import os
import tempfile
import re
from copy import deepcopy
from pathlib import Path


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {x}")))


def flatten(data):
    result = {}
    if not isinstance(data, dict):
        raise ValueError("message root must be an object")

    def visit(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if not key or any(char in key for char in ".[]"):
                    raise ValueError(f"empty or literal-dot/bracket key unsupported: {key!r}")
                visit(item, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
        elif isinstance(value, str):
            result[path] = value
        elif value is not None and not isinstance(value, (int, float, bool)):
            raise ValueError(f"unsupported value: {path}")
    visit(data, "")
    return result


def path_parts(path):
    if not isinstance(path, str) or not re.fullmatch(r"[^.\[\]]+(?:(?:\[(?:0|[1-9]\d*)\])|(?:\.[^.\[\]]+))*", path):
        raise ValueError(f"invalid message path: {path!r}")
    return [int(index) if index else name for name, index in
            re.findall(r"([^.\[\]]+)|\[(\d+)\]", path)]


def validate_paths(messages):
    """Allow partial arrays in Sheet rows; reject ambiguous or colliding paths."""
    tree = {}
    end = object()
    for path, value in messages.items():
        if not isinstance(value, str):
            raise ValueError(f"message must be string: {path}")
        node = tree
        for part in path_parts(path):
            if end in node or any(type(key) is not type(part) for key in node if key is not end):
                raise ValueError(f"path collision: {path}")
            node = node.setdefault(part, {})
        if node:
            raise ValueError(f"path collision: {path}")
        node[end] = value
    return tree, end


def unflatten(messages, template=None):
    tree, end = validate_paths(messages)
    if template is not None:
        source = flatten(template)
        if set(messages) != set(source):
            raise ValueError("messages must match template string paths")
        result = deepcopy(template)
        for path, value in messages.items():
            parts = path_parts(path)
            obj = result
            for part in parts[:-1]:
                obj = obj[part]
            obj[parts[-1]] = value
        return result

    def build(node):
        if end in node:
            return node[end]
        if node and isinstance(next(iter(node)), int):
            indices = sorted(node)
            if indices != list(range(len(indices))):
                raise ValueError("sparse arrays require a source template")
            return [build(node[index]) for index in indices]
        return {key: build(value) for key, value in node.items()}
    return build(tree)


def write(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
