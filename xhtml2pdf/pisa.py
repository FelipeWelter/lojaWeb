import re


class _Status:
    def __init__(self, err=False):
        self.err = err


def _escape_pdf_text(text: str) -> str:
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def CreatePDF(src: str, dest):
    text = re.sub(r'<[^>]+>', ' ', src or '')
    text = re.sub(r'\s+', ' ', text).strip()[:1500] or 'Documento LojaWeb'
    safe = _escape_pdf_text(text)

    stream = f"BT /F1 11 Tf 50 760 Td ({safe}) Tj ET"
    pdf = f"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R>>endobj\n2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1>>endobj\n3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R>>endobj\n4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n5 0 obj<< /Length {len(stream)} >>stream\n{stream}\nendstream endobj\nxref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000063 00000 n \n0000000122 00000 n \n0000000248 00000 n \n0000000318 00000 n \ntrailer<< /Size 6 /Root 1 0 R>>\nstartxref\n{400 + len(stream)}\n%%EOF"
    dest.write(pdf.encode('latin-1', errors='ignore'))
    return _Status(err=False)
