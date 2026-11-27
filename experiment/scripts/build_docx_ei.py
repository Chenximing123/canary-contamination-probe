#!/usr/bin/env python3
"""Build the EI-template Word version of the paper.

Unlike build_docx.py (which formats everything by hand), this builder starts from
the official EI template, keeps its styles (paper title, Author, Affiliation,
Abstract, Keywords, Heading 1/2, Body Text, Caption, figure caption, references)
and lays the paper out as A4 with a single-column front matter followed by a
two-column body. Display equations and inline math are emitted as real Word
equations (OMML), not as linear text.

Output: Chen_Contamination_Detection_EI.docx
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Inches, Pt

ROOT = Path(r'E:\论文')
TEMPLATE = ROOT / '_ei_template.docx'
OUT = ROOT / 'Chen_Contamination_Detection_EI.docx'

sys.path.insert(0, str(ROOT / 'experiment' / 'scripts'))
import build_docx as bd  # noqa: E402

# ---------------------------------------------------------------------------
# LaTeX math -> OMML (subset used by the paper)
# ---------------------------------------------------------------------------
GREEK = {'Delta': '\u0394', 'tau': '\u03c4', 'alpha': '\u03b1', 'beta': '\u03b2',
         'lambda': '\u03bb', 'mu': '\u03bc', 'sigma': '\u03c3', 'pi': '\u03c0'}
OPS = {'in': '\u2208', 'le': '\u2264', 'ge': '\u2265', 'gets': '\u2190',
       'times': '\u00d7', 'cdot': '\u00b7', 'approx': '\u2248', 'neq': '\u2260',
       'to': '\u2192'}
SKIP = {'bigl', 'bigr', 'Bigl', 'Bigr', 'big', 'Big', 'left', 'right', '!',
        'displaystyle'}
SPACE = {';', ',', ':', 'quad', 'qquad'}


def _tok(latex: str) -> list[str]:
    toks, i = [], 0
    while i < len(latex):
        c = latex[i]
        if c == '\\':
            j = i + 1
            if j < len(latex) and latex[j].isalpha():
                k = j
                while k < len(latex) and latex[k].isalpha():
                    k += 1
                toks.append(latex[i:k])
                i = k
            else:
                toks.append(latex[i:i + 2])
                i += 2
        elif c.isalnum():
            k = i
            while k < len(latex) and (latex[k].isalnum()):
                k += 1
            toks.append(latex[i:k])
            i = k
        elif c in '{}_^':
            toks.append(c)
            i += 1
        elif c.isspace():
            i += 1
        else:
            toks.append(c)
            i += 1
    return toks


def _run(text: str) -> str:
    return '<m:r><m:t xml:space="preserve">%s</m:t></m:r>' % escape(text)


def _group(toks: list[str], i: int) -> tuple[str, int]:
    if i < len(toks) and toks[i] == '{':
        i += 1
        nodes = []
        while i < len(toks) and toks[i] != '}':
            xml, i = _atom(toks, i)
            nodes.append(xml)
        return ''.join(nodes), i + 1
    return _atom(toks, i)


def _atom(toks: list[str], i: int) -> tuple[str, int]:
    t = toks[i]
    name = t[1:] if t.startswith('\\') else t
    if t == '\\frac':
        num, i = _group(toks, i + 1)
        den, i = _group(toks, i)
        xml = '<m:f><m:num>%s</m:num><m:den>%s</m:den></m:f>' % (num, den)
    elif t == '\\sum':
        xml = _run('\u03a3')
        i += 1
    elif t == '\\prod':
        xml = _run('\u220f')
        i += 1
    elif t.startswith('\\') and name in GREEK:
        xml = _run(GREEK[name])
        i += 1
    elif t.startswith('\\') and name in OPS:
        xml = _run(OPS[name])
        i += 1
    elif t in ('\\mathcal', '\\mathrm', '\\text', '\\texttt', '\\emph'):
        xml, i = _group(toks, i + 1)
    elif t in ('\\{', '\\}'):
        xml = _run('{' if t == '\\{' else '}')
        i += 1
    elif t in ('\\|', '\\backslash'):
        xml = _run('||' if t == '\\|' else '\\')
        i += 1
    elif t.startswith('\\') and name in SKIP:
        xml = ''
        i += 1
    elif t.startswith('\\') and name in SPACE:
        xml = _run(' ')
        i += 1
    elif t == '{':
        xml, i = _group(toks, i)
    elif t in ('}', '^', '_'):
        xml = ''
        i += 1
    else:
        ch = '\u2212' if t == '-' else t
        xml = _run(ch)
        i += 1
    while i < len(toks) and toks[i] in ('^', '_'):
        kind = toks[i]
        part, i = _group(toks, i + 1)
        if kind == '^':
            xml = '<m:sSup><m:e>%s</m:e><m:sup>%s</m:sup></m:sSup>' % (xml, part)
        else:
            xml = '<m:sSub><m:e>%s</m:e><m:sub>%s</m:sub></m:sSub>' % (xml, part)
    return xml, i


def _omml_body(latex: str) -> str:
    toks = _tok(latex)
    nodes, i = [], 0
    while i < len(toks):
        xml, i = _atom(toks, i)
        nodes.append(xml)
    return ''.join(nodes)


def omml_inline(latex: str):
    return parse_xml('<m:oMath %s>%s</m:oMath>' % (nsdecls('m'), _omml_body(latex)))


def omml_display(latex: str):
    return parse_xml('<m:oMathPara %s><m:oMath>%s</m:oMath></m:oMathPara>'
                     % (nsdecls('m'), _omml_body(latex)))


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
MATH_RE = re.compile(r'\$([^$]*)\$')
FMT_RE = re.compile(r'\\(emph|textbf|texttt)\{([^{}]*)\}')


def _plain_run(p, text: str) -> None:
    """Add a plain text run, keeping the boundary spaces that surround math."""
    lead = ' ' if text[:1].isspace() else ''
    trail = ' ' if text[-1:].isspace() else ''
    core = bd.strip_tex(text)
    if not core and not (lead or trail):
        return
    r = p.add_run(lead + core + trail)
    r.font.name = 'Times New Roman'
    t = r._r.find(qn('w:t'))
    if t is not None:
        t.set(qn('xml:space'), 'preserve')


def _text_segment(p, seg: str) -> None:
    pos = 0
    for m in FMT_RE.finditer(seg):
        if m.start() > pos:
            _plain_run(p, seg[pos:m.start()])
        r = p.add_run(m.group(2))
        r.font.name = 'Times New Roman'
        if m.group(1) == 'emph':
            r.italic = True
        elif m.group(1) == 'textbf':
            r.bold = True
        else:
            r.font.name = 'Courier New'
        pos = m.end()
    if pos < len(seg):
        _plain_run(p, seg[pos:])


def add_rich(p, text: str) -> None:
    """Add text to paragraph p, turning $...$ spans into Word equation objects."""
    pos = 0
    for m in MATH_RE.finditer(text):
        seg = text[pos:m.start()]
        if seg:
            _text_segment(p, seg)
        p._p.append(omml_inline(m.group(1)))
        pos = m.end()
    tail = text[pos:]
    if tail:
        _text_segment(p, tail)


def set_columns(section, num: int, space_twips: int = 360) -> None:
    sectPr = section._sectPr
    cols = sectPr.find(qn('w:cols'))
    if cols is None:
        cols = OxmlElement('w:cols')
        sectPr.append(cols)
    cols.set(qn('w:num'), str(num))
    cols.set(qn('w:space'), str(space_twips))


def page_setup(section) -> None:
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.left_margin = section.right_margin = Cm(1.6)
    section.top_margin, section.bottom_margin = Cm(1.9), Cm(2.54)


def clear_body(doc: Document) -> None:
    body = doc.element.body
    for child in list(body):
        if child.tag != qn('w:sectPr'):
            body.remove(child)


def heading(doc, text: str, style: str = 'Heading 1'):
    p = doc.add_paragraph(text, style=style)
    return p


def table_caption(doc, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    r.font.size = Pt(8)
    r.font.name = 'Times New Roman'
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    return p


def set_table_borders(table, inside_h: bool = True) -> None:
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge, val in (('top', 'single'), ('bottom', 'single'),
                      ('insideH', 'single' if inside_h else 'nil'),
                      ('left', 'nil'), ('right', 'nil'), ('insideV', 'nil')):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), val)
        el.set(qn('w:sz'), '4')
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), '000000')
        borders.append(el)
    tblPr.insert_element_before(borders, 'w:shd', 'w:tblLayout', 'w:tblCellMar',
                                'w:tblLook', 'w:tblCaption', 'w:tblDescription')


def add_table(doc, caption: str, rows, widths=None):
    table_caption(doc, caption)
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    set_table_borders(t)
    t.autofit = False
    if widths:
        for j, w in enumerate(widths):
            t.columns[j].width = Cm(w)
            for i in range(len(rows)):
                t.cell(i, j).width = Cm(w)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            cell.text = ''
            run = cell.paragraphs[0].add_run(val)
            run.font.name = 'Times New Roman'
            run.font.size = Pt(7.5)
            run.bold = (i == 0)
    doc.add_paragraph()


def add_figure(doc, path: Path, caption: str):
    if not path.exists():
        return
    doc.add_picture(str(path), width=Inches(3.3))
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(caption)
    r.font.size = Pt(8)
    r.font.name = 'Times New Roman'


def render_algorithm(doc, block: str, number: str):
    cap = re.search(r'\\caption\{(.*?)\}', block, re.S)
    p = doc.add_paragraph()
    r = p.add_run('Algorithm %s. %s' % (number, bd.strip_tex(cap.group(1)) if cap else ''))
    r.bold = True
    r.font.size = Pt(8)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    n = 0
    lines = []
    for raw in block.splitlines():
        line = raw.strip()
        body = None
        if line.startswith('\\Require'):
            body = 'Require: ' + line[len('\\Require'):].strip()
        elif line.startswith('\\State'):
            n += 1
            body = re.sub(r'\\Comment\{(.*?)\}', lambda m: '  \u25b8 ' + m.group(1),
                          line[len('\\State'):])
            body = body.replace('\\Return', 'return ')
            body = '%d: %s' % (n, body)
        elif line.startswith('\\If'):
            n += 1
            cond = re.search(r'\\If\{(.*)\}', line).group(1)
            body = '%d: if %s then' % (n, cond)
        elif line.startswith('\\Else'):
            n += 1
            body = '%d: else' % n
        elif line.startswith('\\EndIf'):
            n += 1
            body = '%d: end if' % n
        if body:
            lines.append(body)
    if not lines:
        return
    t = doc.add_table(rows=len(lines), cols=1)
    set_table_borders(t, inside_h=False)
    t.autofit = False
    t.columns[0].width = Cm(8.2)
    for row in t.rows:
        row.cells[0].width = Cm(8.2)
        row.height = None
        row.height_rule = WD_ROW_HEIGHT_RULE.AUTO
    for i, body in enumerate(lines):
        cell = t.cell(i, 0)
        para = cell.paragraphs[0]
        para.paragraph_format.space_after = Pt(2)
        para.paragraph_format.space_before = Pt(0)
        para.paragraph_format.line_spacing = 1.15
        add_rich(para, body)
        for run in para.runs:
            run.font.size = Pt(7.5)
            run.font.name = 'Times New Roman'
    doc.add_paragraph()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    doc = Document(str(TEMPLATE))
    clear_body(doc)

    s0 = doc.sections[0]
    page_setup(s0)
    set_columns(s0, 1)

    title_lines, abstract = bd.front_matter()
    for line in title_lines:
        p = doc.add_paragraph(style='paper title')
        p.add_run(line)
    p = doc.add_paragraph(style='Author')
    p.add_run('Ximing Chen')
    for line in ['NUIST Waterford Institute',
                 'Nanjing University of Information Science and Technology',
                 'Nanjing, China', 'Email: 3562958174@qq.com']:
        doc.add_paragraph(line, style='Affiliation')

    p = doc.add_paragraph(style='Abstract')
    lead = p.add_run('Abstract\u2014')
    lead.bold = True
    lead.italic = True
    body = p.add_run(abstract)
    body.bold = False

    p = doc.add_paragraph(style='Keywords')
    lead = p.add_run('Keywords\u2014')
    lead.bold = True
    lead.italic = True
    p.add_run('data contamination, benchmark contamination, memorisation, '
              'perturbation invariance, black-box evaluation, LLM audit')

    body_sec = doc.add_section(WD_SECTION.CONTINUOUS)
    page_setup(body_sec)
    set_columns(body_sec, 2)

    refs = bd.cross_refs()
    cite_nums, ref_texts = bd.bibliography()

    roman = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII']
    sec_no = 0
    fig_no = 0
    sub_no = [0]

    for name in bd.SECTIONS:
        text = (ROOT / 'sections' / f'{name}.tex').read_text(encoding='utf-8-sig')
        text = bd.resolve_refs(text, refs, cite_nums)
        text = re.sub(r'\\begin\{table\}.*?\\end\{table\}', '', text, flags=re.S)
        text = re.sub(r'\\begin\{figure\}.*?\\end\{figure\}', '', text, flags=re.S)
        blocks = {}

        def stash(m):
            key = '@@BLOCK%d@@' % len(blocks)
            blocks[key] = m.group(0)
            return '\n' + key + '\n'

        text = re.sub(r'\\begin\{equation\}.*?\\end\{equation\}', stash, text, flags=re.S)
        text = re.sub(r'\\begin\{algorithm\}.*?\\end\{algorithm\}', stash, text, flags=re.S)

        buf: list[str] = []
        item = None
        in_items = False
        left_align = [False]

        def flush_para():
            nonlocal buf
            if buf:
                p = doc.add_paragraph(style='Body Text')
                add_rich(p, ' '.join(buf))
                if left_align[0]:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                buf = []

        def flush_item():
            nonlocal item
            if item:
                p = doc.add_paragraph(style='bullet list')
                add_rich(p, item)
                item = None

        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                flush_para()
                continue
            if line in blocks:
                flush_para()
                flush_item()
                block = blocks[line]
                if block.startswith('\\begin{equation}'):
                    eq = re.sub(r'\\begin\{equation\}|\\end\{equation\}', '', block)
                    eq = re.sub(r'\\label\{[^}]*\}', '', eq)
                    eq = ' '.join(eq.split())
                    p = doc.add_paragraph(style='equation')
                    p.paragraph_format.tab_stops.add_tab_stop(Cm(8.4), 2)  # right aligned
                    p._p.append(omml_inline(eq))
                    r = p.add_run('\t(1)')
                    r.font.size = Pt(9)
                else:
                    render_algorithm(doc, block, '1')
                continue
            m = re.match(r'\\section\*?\{(.*?)\}', line)
            if m:
                flush_para()
                flush_item()
                title = bd.strip_tex(m.group(1))
                if line.startswith('\\section*'):
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    r = p.add_run(title.upper())
                    r.bold = True
                    r.font.size = Pt(9)
                    left_align[0] = True
                else:
                    sec_no += 1
                    sub_no[0] = 0
                    heading(doc, title.upper())
                continue
            m = re.match(r'\\subsection\{(.*?)\}', line)
            if m:
                flush_para()
                flush_item()
                head = bd.strip_tex(m.group(1))
                sub_letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                sub_no[0] += 1
                heading(doc, head, style='Heading 2')
                if head in bd.TABLES:
                    label, caption, rows, widths = bd.TABLES[head]
                    num = refs.get(label, '')
                    add_table(doc, 'TABLE %s. %s' % (num, caption), rows, widths)
                if head in bd.FIGURES:
                    label, img, caption = bd.FIGURES[head]
                    fig_no += 1
                    add_figure(doc, ROOT / img, 'Fig. %d. %s' % (fig_no, caption))
                continue
            if line.startswith('\\begin{itemize}'):
                in_items = True
                continue
            if line.startswith('\\end{itemize}'):
                flush_item()
                in_items = False
                continue
            if line.startswith('\\item'):
                flush_item()
                flush_para()
                item = line[5:].strip()
                continue
            if line and not line.startswith('\\input') and not line.startswith('\\label'):
                if in_items and item is not None:
                    item += ' ' + line
                else:
                    buf.append(line)
        flush_item()
        flush_para()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('REFERENCES')
    r.bold = True
    r.font.size = Pt(9)
    for i, ref in enumerate(ref_texts, 1):
        q = doc.add_paragraph(style='references')
        q.add_run(ref)

    doc.save(str(OUT))
    print('saved ->', OUT)


if __name__ == '__main__':
    main()
