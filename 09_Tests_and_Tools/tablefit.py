#!/usr/bin/env python3
"""Font-metric-driven table column sizing for md2docx.

The previous heuristic sized columns from raw character counts, which ignores
three things that actually decide whether Word/WPS clips a cell:

  1. the real advance width of each glyph in Calibri / Consolas,
  2. the left+right cell margin that is subtracted from every column, and
  3. the fact that a word processor will not break an identifier such as
     ``S2_Strategic_Referral_To_Authorisation.bpmn`` - so the column must be
     at least as wide as the longest unbreakable token it contains.

This module measures glyph advances straight out of the installed TrueType
files (no third-party dependency), then solves for a set of column widths that
never clip a token while keeping the table as short as possible.
"""
import os
import re
import sys

# --------------------------------------------------------------------- geometry
# A4 portrait is 11906 twips wide; the documents use 2 cm margins (1134 twips).
USABLE = 9638
CELL_MAR = 180     # explicit left+right cell margin written on every table
SAFETY = 14        # border rounding slack per column
MIN_COL = 380      # never emit a comically narrow column

FONT_FILES = {
    ('body', False): r'C:\Windows\Fonts\calibri.ttf',
    ('body', True): r'C:\Windows\Fonts\calibrib.ttf',
    ('mono', False): r'C:\Windows\Fonts\consola.ttf',
    ('mono', True): r'C:\Windows\Fonts\consolab.ttf',
}

# Word/WPS break a line after these characters (the character stays on the
# first line); whitespace is always a break opportunity.
BREAK_AFTER = '-/\u2013\u2014'


# ------------------------------------------------------------------ TrueType

def _u16(d, o):
    return int.from_bytes(d[o:o + 2], 'big')


def _u32(d, o):
    return int.from_bytes(d[o:o + 4], 'big')


class TTF(object):
    """Just enough of the TrueType format to read horizontal advances."""

    def __init__(self, path):
        with open(path, 'rb') as fh:
            self.d = fh.read()
        self.tables = {}
        for i in range(_u16(self.d, 4)):
            o = 12 + 16 * i
            tag = self.d[o:o + 4].decode('latin-1')
            self.tables[tag] = (_u32(self.d, o + 8), _u32(self.d, o + 12))
        head = self.tables['head'][0]
        self.upem = _u16(self.d, head + 18) or 2048
        hhea = self.tables['hhea'][0]
        self.nh = _u16(self.d, hhea + 34)
        self.hmtx = self.tables['hmtx'][0]
        self.cmap = self._cmap(self.tables['cmap'][0])
        self._cache = {}

    # -- cmap ------------------------------------------------------------
    def _cmap(self, base):
        best = None
        for i in range(_u16(self.d, base + 2)):
            o = base + 4 + 8 * i
            pid, eid, off = _u16(self.d, o), _u16(self.d, o + 2), _u32(self.d, o + 4)
            fmt = _u16(self.d, base + off)
            rank = {(3, 10, 12): 0, (3, 1, 4): 1, (0, 4, 12): 2, (0, 3, 4): 3}.get((pid, eid, fmt))
            if rank is not None and (best is None or rank < best[0]):
                best = (rank, base + off)
        if best is None:
            return {}
        off = best[1]
        fmt = _u16(self.d, off)
        if fmt == 4:
            return self._cmap4(off)
        if fmt == 12:
            return self._cmap12(off)
        return {}

    def _cmap4(self, off):
        segx2 = _u16(self.d, off + 6)
        end = off + 14
        start = end + segx2 + 2
        delta = start + segx2
        roff = delta + segx2
        m = {}
        for i in range(segx2 // 2):
            e = _u16(self.d, end + 2 * i)
            s = _u16(self.d, start + 2 * i)
            if s == 0xFFFF or e < s:
                continue
            dl = int.from_bytes(self.d[delta + 2 * i:delta + 2 * i + 2], 'big', signed=True)
            ro = _u16(self.d, roff + 2 * i)
            for c in range(s, e + 1):
                if ro == 0:
                    g = (c + dl) & 0xFFFF
                else:
                    gi = roff + 2 * i + ro + 2 * (c - s)
                    if gi + 2 > len(self.d):
                        continue
                    g = _u16(self.d, gi)
                    if g:
                        g = (g + dl) & 0xFFFF
                if g:
                    m[c] = g
        return m

    def _cmap12(self, off):
        m = {}
        for i in range(_u32(self.d, off + 12)):
            b = off + 16 + 12 * i
            s, e, g = _u32(self.d, b), _u32(self.d, b + 4), _u32(self.d, b + 8)
            if e - s > 0xFFFF:
                continue
            for c in range(s, e + 1):
                m[c] = g + (c - s)
        return m

    # -- advance width ---------------------------------------------------
    def units(self, ch):
        cp = ord(ch)
        g = self.cmap.get(cp)
        if g is None:
            # Rough fallback for anything the cmap does not cover.
            if 0x2E80 <= cp <= 0x9FFF or 0xFF00 <= cp <= 0xFF60:
                return int(self.upem * 1.0)
            return int(self.upem * 0.5)
        if g >= self.nh:
            g = self.nh - 1
        return _u16(self.d, self.hmtx + 4 * g)

    def twips(self, ch, size_hp):
        """Advance width of ``ch`` in twips for a font size in half-points."""
        return self.units(ch) * (size_hp / 2.0) * 20.0 / self.upem


_FONTS = {}
_HEURISTIC = {}


def font(bold=False, mono=False):
    key = ('mono' if mono else 'body', bool(bold))
    if key not in _FONTS:
        path = FONT_FILES[key]
        try:
            _FONTS[key] = TTF(path)
        except Exception:
            _FONTS[key] = None
    return _FONTS[key]


_HEUR = {('body', False): 0.4785, ('body', True): 0.5054,
         ('mono', False): 0.5500, ('mono', True): 0.5500}


def char_twips(ch, size_hp, bold=False, mono=False):
    f = font(bold, mono)
    if f is None:
        return _HEUR[('mono' if mono else 'body', bool(bold))] * (size_hp / 2.0) * 20.0
    return f.twips(ch, size_hp)


# --------------------------------------------------------------- inline parse

# A backslash escape has to be removed *before* the span delimiters are found,
# otherwise "i\*" would be read as the start of an italic span. Each escaped
# character is swapped for a private sentinel, the text is split on the real
# delimiters, and the sentinels are turned back into the literal characters
# afterwards - including inside bold, italic and code spans.
_ESC = {
    '\\': '\x01', '`': '\x02', '*': '\x03', '_': '\x04', '{': '\x05',
    '}': '\x06', '[': '\x07', ']': '\x08', '(': '\x09', ')': '\x0a',
    '#': '\x0b', '+': '\x0c', '-': '\x0d', '.': '\x0e', '!': '\x0f',
    '~': '\x10', '|': '\x11',
}
_REV = dict((v, k) for k, v in _ESC.items())

_TOK = re.compile(r'(\*\*.+?\*\*|`[^`]+`|\*[^*\n]+?\*)')


def protect_md(s):
    """Swap backslash-escaped punctuation for sentinels."""
    out, i = [], 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s) and s[i + 1] in _ESC:
            out.append(_ESC[s[i + 1]])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def restore_md(s):
    """Turn sentinels back into the literal characters the author escaped."""
    return ''.join(_REV.get(c, c) for c in s)


def spans(text, header_bold=False):
    """Markdown cell text -> list of (char, bold, mono)."""
    out = []
    for tok in _TOK.split(protect_md(text)):
        if not tok:
            continue
        if tok.startswith('**') and tok.endswith('**') and len(tok) > 4:
            body, bold, mono = tok[2:-2], True, False
        elif tok.startswith('`') and tok.endswith('`') and len(tok) > 2:
            body, bold, mono = tok[1:-1], header_bold, True
        elif tok.startswith('*') and tok.endswith('*') and len(tok) > 2:
            body, bold, mono = tok[1:-1], header_bold, False
        else:
            body, bold, mono = tok, header_bold, False
        for ch in restore_md(body):
            out.append((ch, bold, mono))
    return out


def full_width(chars, size_hp):
    return sum(char_twips(c, size_hp, b, m) for c, b, m in chars)


def chunks(chars, size_hp):
    """Split into (width, is_space) unbreakable pieces."""
    out, cur, cur_is_space = [], 0.0, False
    for ch, b, m in chars:
        if ch.isspace():
            if cur:
                out.append((cur, cur_is_space))
                cur, cur_is_space = 0.0, False
            out.append((0.0, True))
            continue
        if not cur:
            cur_is_space = False
        cur += char_twips(ch, size_hp, b, m)
        if ch in BREAK_AFTER:
            out.append((cur, False))
            cur = 0.0
    if cur:
        out.append((cur, False))
    return out


def widest_chunk(chars, size_hp):
    return max([w for w, sp in chunks(chars, size_hp) if not sp] + [0.0])


def lines(chars, size_hp, avail):
    """Greedy line count for the cell text inside ``avail`` twips."""
    if avail <= 0:
        return 1
    n, cur = 1, 0.0
    for w, is_space in chunks(chars, size_hp):
        if is_space:
            continue
        if cur == 0.0:
            cur = w
        elif cur + w <= avail:
            cur += w
        else:
            n += 1
            cur = w
    return n


# --------------------------------------------------------------------- solver

def _round_to_total(widths, total):
    """Round float widths to integers that sum exactly to ``total``."""
    out = [int(w) for w in widths]
    diff = total - sum(out)
    order = sorted(range(len(out)), key=lambda i: -widths[i])
    i = 0
    while diff and order:
        out[order[i % len(order)]] += 1 if diff > 0 else -1
        diff += -1 if diff > 0 else 1
        i += 1
        if i > 4 * len(order) + 8:
            break
    if sum(out) != total:
        out[order[0]] += total - sum(out)
    return out


def _floors(grid, ncols, size_hp):
    need = []
    for c in range(ncols):
        w = max(widest_chunk(grid[r][c], size_hp) for r in range(len(grid)))
        need.append(max(int(w) + CELL_MAR + SAFETY, MIN_COL))
    return need


def _alloc_height(grid, ncols, size_hp, floors):
    """Water-fill: spend every twip where it removes the most wrapped lines."""
    widths = list(floors)
    left = USABLE - sum(widths)

    def total_lines(ws):
        tot = 0
        for r in range(len(grid)):
            h = 1
            for c in range(ncols):
                h = max(h, lines(grid[r][c], size_hp, ws[c] - CELL_MAR))
            tot += h
        return tot

    step = 40
    cur_h = total_lines(widths)
    while left >= step:
        best, best_gain = -1, 0.0
        for c in range(ncols):
            trial = list(widths)
            trial[c] += step
            gain = cur_h - total_lines(trial)
            if gain > best_gain:
                best, best_gain = c, gain
        if best < 0:
            break
        widths[best] += step
        left -= step
        cur_h -= best_gain
        if best_gain == 0:
            break
    if left > 0:
        widths[widths.index(max(widths))] += left
    return widths


def _alloc_balance(grid, ncols, size_hp, floors):
    """Give each column a share proportional to its widest cell, then lift the
    narrow ones up to their floor and take the difference off whichever
    columns are still above their floor. Keeps the familiar 'wide prose
    column, slim code column' look while never clipping a token."""
    want = []
    for c in range(ncols):
        w = max(full_width(grid[r][c], size_hp) for r in range(len(grid)))
        want.append(min(w + CELL_MAR, USABLE * 0.55))
    sw = sum(want) or 1.0
    cur = [USABLE * w / sw for w in want]
    cur = [max(cur[c], floors[c]) for c in range(ncols)]
    for _ in range(60):
        over = sum(cur) - USABLE
        if over <= 0:
            break
        slack = [max(0.0, cur[c] - floors[c]) for c in range(ncols)]
        tot = sum(slack)
        if tot <= 0:
            break
        take = min(over, tot)
        for c in range(ncols):
            cur[c] -= take * slack[c] / tot
    rest = USABLE - sum(cur)
    if rest > 0:
        order = sorted(range(ncols), key=lambda c: -want[c])
        for c in order:
            if rest <= 0:
                break
            room = max(0.0, want[c] * 1.6 - cur[c])
            add = min(rest, room)
            cur[c] += add
            rest -= add
        if rest > 0:
            cur[order[0]] += rest
    return [int(round(x)) for x in cur]


def solve(rows, sizes=(21, 20, 19, 18, 17, 16, 15), label='', mode='balance'):
    """Pick a font size and column widths for a markdown table.

    ``rows`` is a list of lists of raw markdown cell strings; row 0 is the
    header. Returns ``(size_hp, widths)`` where sum(widths) == USABLE.
    """
    if not rows:
        return 21, []
    ncols = max(len(r) for r in rows)
    grid = []
    for ri, row in enumerate(rows):
        grid.append([spans(row[c] if c < len(row) else '', header_bold=(ri == 0))
                     for c in range(ncols)])

    chosen, floors = None, None
    for size_hp in sizes:
        need = _floors(grid, ncols, size_hp)
        if sum(need) <= USABLE:
            chosen, floors = size_hp, need
            break
    if chosen is None:
        chosen, floors = sizes[-1], need
        sys.stderr.write('  ! table %s: columns cannot fit at %gpt; '
                         'content may clip\n' % (label or '?', chosen / 2.0))

    alloc = _alloc_height if mode == 'height' else _alloc_balance
    widths = _round_to_total(alloc(grid, ncols, chosen, floors), USABLE)
    return chosen, widths


def report(rows, size_hp, widths, label):
    """Diagnostics used by the build to prove nothing can clip."""
    bad = 0
    for ri, row in enumerate(rows):
        for ci in range(len(widths)):
            txt = row[ci] if ci < len(row) else ''
            ch = spans(txt, header_bold=(ri == 0))
            w = widest_chunk(ch, size_hp)
            if w + CELL_MAR + 2 > widths[ci]:
                bad += 1
                sys.stderr.write('  ! %s r%d c%d needs %d has %d: %s\n'
                                 % (label, ri, ci, int(w) + CELL_MAR, widths[ci], txt[:50]))
    return bad


if __name__ == '__main__':
    f = font()
    if f is None:
        print('no font')
    else:
        print('upem=%d  glyphs=%d  cmap=%d' % (f.upem, f.nh, len(f.cmap)))
        for s in ('Verdict', 'REQ-01', 'Measurability',
                  'S2_Strategic_Referral_To_Authorisation.bpmn'):
            print('%5.0f twips @10.5pt  %s' % (full_width(spans(s), 21), s))
            print('%5.0f twips @10.5pt bold' % full_width(spans('**%s**' % s), 21))
