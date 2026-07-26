from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


SOURCE = Path(
    r"E:\LaptopHealthMonitor_AI\LaptopHealthMonitor_AI\Project_Documentation"
    r"\I3_Project_Documentation_2026_27_FINAL_RESULTS_UPDATED.docx"
)
OUTPUT = Path(
    r"E:\LaptopHealthMonitor_AI\LaptopHealthMonitor_AI\Project_Documentation"
    r"\I3_Project_Documentation_2026_27_SUBMISSION_READY.docx"
)


def set_shading(paragraph, fill: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    old = p_pr.find(qn("w:shd"))
    if old is not None:
        p_pr.remove(old)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    p_pr.append(shading)


def set_borders(paragraph, edges, color: str, size: str = "6") -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    old = p_pr.find(qn("w:pBdr"))
    if old is not None:
        p_pr.remove(old)
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        if edge not in edges:
            continue
        border = OxmlElement(f"w:{edge}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), size)
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), color)
        borders.append(border)
    p_pr.append(borders)


def set_run_font(run, size: float, color: str = "24292F", bold=False) -> None:
    run.font.name = "Consolas"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        r_fonts.set(qn(f"w:{attr}"), "Consolas")


def style_header(paragraph) -> None:
    original = paragraph.text.strip()
    if not original.startswith("In [ ]:"):
        paragraph.text = f"In [ ]:  {original}"
    fmt = paragraph.paragraph_format
    fmt.left_indent = Inches(0.18)
    fmt.right_indent = Inches(0.12)
    fmt.first_line_indent = Inches(0)
    fmt.space_before = Pt(8)
    fmt.space_after = Pt(0)
    fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
    fmt.keep_with_next = True
    set_shading(paragraph, "EAF3FF")
    set_borders(
        paragraph,
        {"top", "left", "bottom", "right"},
        color="9CC2E5",
        size="8",
    )
    for run in paragraph.runs:
        set_run_font(run, 9.5, color="1F5A94", bold=True)


def style_code_line(paragraph, is_last: bool) -> None:
    fmt = paragraph.paragraph_format
    fmt.left_indent = Inches(0.18)
    fmt.right_indent = Inches(0.12)
    fmt.first_line_indent = Inches(0)
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
    fmt.keep_with_next = False
    fmt.keep_together = False
    fmt.widow_control = False
    set_shading(paragraph, "F6F8FA")
    edges = {"left", "right"}
    if is_last:
        edges.add("bottom")
    set_borders(paragraph, edges, color="D0D7DE", size="6")
    for run in paragraph.runs:
        set_run_font(run, 8.5)


def main() -> None:
    document = Document(SOURCE)
    paragraphs = document.paragraphs
    start = next(
        i for i, p in enumerate(paragraphs) if p.text.strip().startswith("FILE: ")
    )
    end = next(
        i
        for i, p in enumerate(paragraphs[start + 1 :], start + 1)
        if p.text.strip()
        == "Annexure-II(B): Application Interface and Output Evidence"
    )
    headers = [
        i
        for i in range(start, end)
        if paragraphs[i].text.strip().startswith("FILE: ")
    ]

    for cell_index, header_index in enumerate(headers):
        next_header = (
            headers[cell_index + 1] if cell_index + 1 < len(headers) else end
        )
        style_header(paragraphs[header_index])
        code_indices = list(range(header_index + 1, next_header))
        for index in code_indices:
            style_code_line(paragraphs[index], is_last=index == code_indices[-1])

    document.core_properties.title = (
        "Laptop Health Monitor – Final Project Documentation"
    )
    document.save(OUTPUT)
    print(f"Saved: {OUTPUT}")
    print(f"Notebook-style file cells: {len(headers)}")
    print(f"Formatted code paragraphs: {end - start - len(headers)}")


if __name__ == "__main__":
    main()
