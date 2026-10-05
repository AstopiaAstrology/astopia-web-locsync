"""Explicit raw-message contracts; ordinary messages still use ICU validation."""
import re
from html.parser import HTMLParser
from .icu import signature


class RawHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in {'p', 'strong', 'span', 'br'}:
            raise ValueError(f'raw HTML tag not allowed: {tag}')
        for name, value in attrs:
            if name != 'style' or not re.fullmatch(r'color:\s*rgb\(\d{1,3},\s*\d{1,3},\s*\d{1,3}\);?', value or ''):
                raise ValueError('raw HTML only permits color: rgb(...) style attributes')
        if tag != 'br':
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise ValueError('unbalanced raw HTML tags')

    def handle_startendtag(self, tag, attrs):
        if tag != 'br':
            raise ValueError('only br may be self-closing')
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        signature(data)
        if '{' in data or '}' in data or '<' in data or '>' in data:
            raise ValueError('raw HTML cannot contain placeholders or malformed markup')

    def handle_comment(self, data):
        raise ValueError('raw HTML comments are not allowed')

    def handle_decl(self, decl):
        raise ValueError('raw HTML declarations are not allowed')

    def unknown_decl(self, data):
        raise ValueError('raw HTML declarations are not allowed')

    def handle_pi(self, data):
        raise ValueError('raw HTML processing instructions are not allowed')


def raw_signature(text, policy):
    if policy == 'html-color':
        parser = RawHTML()
        parser.feed(text)
        parser.close()
        if parser.stack:
            raise ValueError('unclosed raw HTML tag')
        return {'raw': 'html-color'}
    if policy == 'credit-token':
        if text.count('<credit>') != 1:
            raise ValueError('raw credit message requires exactly one <credit> token')
        rest = text.replace('<credit>', '')
        if any(c in rest for c in '<>{}'):
            raise ValueError('raw credit message contains unsupported markup/placeholders')
        return {'raw': 'credit-token'}
    raise ValueError(f'unknown raw message policy: {policy}')
