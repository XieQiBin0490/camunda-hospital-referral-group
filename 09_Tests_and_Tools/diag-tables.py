#!/usr/bin/env python3
"""Verify table layout in generated .docx files.

Re-reads word/document.xml straight out of each package and checks, for every
table, that

  * the declared column widths, the sum of the grid, the table width and the
    usable text column all agree, and
  * no unbreakable token inside any cell is wider than that cell's content
    area (the condition that makes Word/WPS overflow or clip a cell).

Widths are measured with the same Calibri metrics used by the converter; those
were validated against Word itself (see tools/measure-word.ps1) and are 1-3%
wider than Word, so a pass here is a conservative pass.
"""
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tablefit

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def cell_chars(tc):
    out = []
    for r in tc.iter(W + 'r'):
        rpr = r.find(W + 'rPr')
        bold = rpr is not None and rpr.find(W + 'b') is not None
        mono = False
        sz = 21
        if rpr is not None:
            rf = rpr.find(W + 'rFonts')
            if rf is not None and rf.get(W + 'ascii') == 'Consolas':
                mono = True
            s = rpr.find(W + 'sz')
            if s is not None:
                sz = int(s.get(W + 'val'))
        for t in r.iter(W + 't'):
            for ch in (t.text or ''):
                out.append((ch, bold, mono, sz))
    return out


def check(path, verbose=False):
    z = zipfile.ZipFile(path)
    xml = z.read('word/document.xml')
    root = ET.fromstring(xml)
    body = root.find(W + 'body')
    problems, ntables, sizes = [], 0, set()
    widths_seen = []
    for tbl in body.iter(W + 'tbl'):
        ntables += 1
        grid = [int(g.get(W + 'w')) for g in tbl.find(W + 'tblGrid').iter(W + 'gridCol')]
        widths_seen.append(grid)
        tblpr = tbl.find(W + 'tblPr')
        tw = 0
        if tblpr is not None:
            e = tblpr.find(W + 'tblW')
            if e is not None:
                tw = int(e.get(W + 'w'))
            mar = tblpr.find(W + 'tblCellMar')
            if mar is not None:
                left = mar.find(W + 'left')
                right = mar.find(W + 'right')
                mar = (int(left.get(W + 'w')) if left is not None else 0) + \
                      (int(right.get(W + 'w')) if right is not None else 0)
            else:
                mar = 216
        else:
            mar = 216
        if sum(grid) != tablefit.USABLE:
            problems.append('grid sums to %d, expected %d' % (sum(grid), tablefit.USABLE))
        if tw and tw != sum(grid):
            problems.append('tblW %d != sum(gridCol) %d' % (tw, sum(grid)))
        for tr in tbl.findall(W + 'tr'):
            for ci, tc in enumerate(tr.findall(W + 'tc')):
                tcw = tc.find(W + 'tcPr/' + W + 'tcW')
                cw = int(tcw.get(W + 'w')) if tcw is not None else 0
                if ci < len(grid) and cw != grid[ci]:
                    problems.append('cell %d: tcW %d != gridCol %d' % (ci, cw, grid[ci]))
                chars = cell_chars(tc)
                if not chars:
                    continue
                size = chars[0][3]
                sizes.add(size)
                plain = [(c, b, m) for c, b, m, _ in chars]
                avail = (grid[ci] if ci < len(grid) else cw) - mar
                w = tablefit.widest_chunk(plain, size)
                if w + 2 > avail:
                    txt = ''.join(c for c, _, _, _ in chars)
                    problems.append('table %d cell %d: token %g > %g  "%s"'
                                    % (ntables, ci, w, avail, txt[:60]))
    return ntables, problems, sizes, widths_seen


def dump(path, index):
    """Print one table row by row, with the width each cell's longest word needs."""
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read('word/document.xml'))
    tbls = list(root.find(W + 'body').iter(W + 'tbl'))
    tbl = tbls[index - 1]
    grid = [int(g.get(W + 'w')) for g in tbl.find(W + 'tblGrid').iter(W + 'gridCol')]
    mar = 180
    print('table %d of %d   cols=%s  total=%d' % (index, len(tbls), grid, sum(grid)))
    for ri, tr in enumerate(tbl.findall(W + 'tr')):
        out = []
        for ci, tc in enumerate(tr.findall(W + 'tc')):
            chars = cell_chars(tc)
            txt = ''.join(c for c, _, _, _ in chars)
            if not chars:
                out.append('')
                continue
            size = chars[0][3]
            plain = [(c, b, m) for c, b, m, _ in chars]
            w = tablefit.widest_chunk(plain, size)
            avail = (grid[ci] if ci < len(grid) else 0) - mar
            mark = '' if w + 2 <= avail else '  <<< OVERFLOW'
            out.append('%s [%g/%g]%s' % (txt, w, avail, mark))
        print('  r%-2d | %s' % (ri, ' | '.join(out)))


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == '-t':
        dump(args[1], int(args[2]))
        sys.exit(0)
    files = args
    if not files:
        print(__doc__)
        sys.exit(1)
    total_bad = 0
    for f in files:
        n, probs, sizes, widths_seen = check(f)
        tag = 'OK ' if not probs else 'FAIL'
        print('%-3s %-56s tables=%-3d sizes=%s' %
              (tag, os.path.basename(f), n,
               ','.join('%gpt' % (s / 2.0) for s in sorted(sizes))))
        for i, w in enumerate(widths_seen[:40], 1):
            print('      t%-3d %s' % (i, ','.join(str(x) for x in w)))
        for p in probs[:12]:
            print('      %s' % p)
        if len(probs) > 12:
            print('      ... and %d more' % (len(probs) - 12))
        total_bad += len(probs)
    print('\n%d problem(s) across %d file(s)' % (total_bad, len(files)))
    sys.exit(1 if total_bad else 0)
