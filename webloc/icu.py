"""Conservative ICU/next-intl parser, including nested options and rich tags.

Custom number/date/time styles and skeletons are rejected rather than falsely
certified. Argument types and rich tag names form the translation contract.
"""
import re


class Parser:
    def __init__(self, text):
        self.text, self.i, self.contract = text, 0, {}

    def error(self, message):
        raise ValueError(f"{message} at character {self.i}")

    def token(self, pattern):
        match = re.match(pattern, self.text[self.i:])
        if not match:
            self.error("expected token")
        self.i += len(match[0])
        return match[0]

    def spaces(self):
        self.token(r"\s*")

    def add(self, name, kind):
        self.contract.setdefault(name, set()).add(kind)

    def message(self, nested=False, tag=None, plural=False):
        while self.i < len(self.text):
            char = self.text[self.i]
            if char == "'":
                self.i += 1
                if self.i < len(self.text) and self.text[self.i] == "'":
                    self.i += 1
                elif self.i < len(self.text) and self.text[self.i] in ("{}", "{}#")[plural] + "<":
                    while self.i < len(self.text):
                        if self.text[self.i] == "'":
                            self.i += 1
                            if self.i < len(self.text) and self.text[self.i] == "'":
                                self.i += 1
                                continue
                            break
                        self.i += 1
                continue
            if char == "}":
                if not nested or tag:
                    self.error("unexpected closing brace")
                return
            if char == "{":
                self.argument()
            elif self.text.startswith("</", self.i):
                close = self.token(r"</[A-Za-z][A-Za-z0-9_]*\s*>")
                if not tag or close[2:].rstrip(">").strip() != tag:
                    self.error("mismatched rich text tag")
                return
            elif char == "<" and re.match(r"<[A-Za-z]", self.text[self.i:]):
                opening = self.token(r"<[A-Za-z][A-Za-z0-9_]*\s*>")
                name = opening[1:].rstrip(">").strip()
                self.add(name, "tag")
                self.message(tag=name, plural=plural)
            else:
                self.i += 1
        if tag or nested:
            self.error("unclosed message")

    def argument(self):
        self.i += 1
        self.spaces()
        name = self.token(r"[A-Za-z_][A-Za-z0-9_]*")
        self.spaces()
        if self.i >= len(self.text):
            self.error("unclosed argument")
        if self.text[self.i] == "}":
            self.add(name, "argument")
            self.i += 1
            return
        self.token(",")
        self.spaces()
        kind = self.token(r"[a-z]+")
        if kind not in {"number", "date", "time", "plural", "selectordinal", "select"}:
            self.error("unsupported argument type")
        self.add(name, kind)
        self.spaces()
        if kind in {"number", "date", "time"}:
            if self.i < len(self.text) and self.text[self.i] == ",":
                self.i += 1
                self.spaces()
                style = self.token(r"[a-z]+")
                allowed = {"number": {"integer", "currency", "percent"},
                           "date": {"short", "medium", "long", "full"},
                           "time": {"short", "medium", "long", "full"}}
                if style not in allowed[kind]:
                    self.error("unsupported format style")
                self.spaces()
            self.token("}")
            return
        self.token(",")
        self.spaces()
        if kind != "select" and self.text.startswith("offset:", self.i):
            self.token(r"offset:\s*\d+")
            self.spaces()
        selectors = set()
        while self.i < len(self.text) and self.text[self.i] != "}":
            selector = self.token(r"(?:=\d+|[A-Za-z_][A-Za-z0-9_]*)")
            if selector in selectors:
                self.error("duplicate selector")
            if kind != "select" and selector not in {"zero", "one", "two", "few", "many", "other"} and not selector.startswith("="):
                self.error("invalid plural selector")
            if kind == "select" and selector.startswith("="):
                self.error("invalid select selector")
            selectors.add(selector)
            self.spaces()
            self.token(r"\{")
            self.message(nested=True, plural=kind != "select")
            self.token("}")
            self.spaces()
        if "other" not in selectors:
            self.error("missing other selector")
        self.token("}")


def signature(text):
    parser = Parser(text)
    parser.message()
    return parser.contract
