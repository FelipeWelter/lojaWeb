import re
from html import unescape


class _Status:
    def __init__(self, err=False):
        self.err = err


def _escape_pdf_text(text: str) -> str:
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _html_to_lines(src: str) -> list[str]:
    html = src or ''
    html = re.sub(r'<style\b[^>]*>.*?</style>', ' ', html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<script\b[^>]*>.*?</script>', ' ', html, flags=re.IGNORECASE | re.DOTALL)

    # Preserve visual structure for receipts/coupons by converting block tags into line breaks.
    block_tags = (
        'br', 'p', 'div', 'tr', 'table', 'thead', 'tbody', 'tfoot',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'section', 'article', 'header', 'footer'
    )
    for tag in block_tags:
        html = re.sub(fr'<\s*{tag}\b[^>]*>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(fr'<\s*/\s*{tag}\s*>', '\n', html, flags=re.IGNORECASE)

    html = re.sub(r'<\s*td\b[^>]*>', ' ', html, flags=re.IGNORECASE)
    html = re.sub(r'<\s*/\s*td\s*>', ' | ', html, flags=re.IGNORECASE)
    html = re.sub(r'<\s*th\b[^>]*>', ' ', html, flags=re.IGNORECASE)
    html = re.sub(r'<\s*/\s*th\s*>', ' | ', html, flags=re.IGNORECASE)

    text = re.sub(r'<[^>]+>', ' ', html)
    text = unescape(text)
    text = text.replace('\r', '\n').replace('\t', ' ')

    lines = []
    for raw in text.split('\n'):
        clean = re.sub(r'\s+', ' ', raw).strip(' |')
        if clean:
            lines.append(clean)

    if not lines:
        return ['Documento LojaWeb']

    # Limit output size to keep simple PDF generation predictable.
    max_chars = 3000
    joined = '\n'.join(lines)[:max_chars]
    return joined.split('\n')


def CreatePDF(src: str, dest):
    lines = _html_to_lines(src)

    max_lines = 48
    lines = lines[:max_lines]

    stream_parts = ["BT /F1 10 Tf 50 790 Td 14 TL"]
    for i, line in enumerate(lines):
        safe = _escape_pdf_text(line)
        if i == 0:
            stream_parts.append(f"({safe}) Tj")
        else:
            stream_parts.append(f"T* ({safe}) Tj")
    stream_parts.append("ET")
    stream = ' '.join(stream_parts)

    pdf = f"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R>>endobj\n2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1>>endobj\n3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R>>endobj\n4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n5 0 obj<< /Length {len(stream)} >>stream\n{stream}\nendstream endobj\nxref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000063 00000 n \n0000000122 00000 n \n0000000248 00000 n \n0000000318 00000 n \ntrailer<< /Size 6 /Root 1 0 R>>\nstartxref\n{400 + len(stream)}\n%%EOF"
    dest.write(pdf.encode('latin-1', errors='ignore'))
    return _Status(err=False)
