from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


SOURCE = Path(r"E:\LaptopHealthMonitor_AI\I3_Project_Documentation_2026_27.docx")
OUTPUT = Path(
    r"E:\LaptopHealthMonitor_AI\LaptopHealthMonitor_AI\Project_Documentation"
    r"\I3_Project_Documentation_2026_27_INDEX_CORRECTED.docx"
)


CONTENTS = [
    ("Declaration", 29),
    ("Certificate", 35),
    ("Acknowledgements", 41),
    ("Abstract", 58),
    ("Contents", 70),
    ("List of Figures", 96),
    ("List of Tables", 118),
    ("List of Screenshots", 129),
    ("Symbols and Abbreviations", 139),
    ("Chapter 1 Introduction", 141),
    ("1.1 Motivation", 142),
    ("1.2 Introduction", 147),
    ("1.3 Problem Definition", 155),
    ("1.4 Ił Framework: Ideation, Innovation and Implementation", 161),
    ("1.5 Objectives", 168),
    ("1.6 Scope of the Mini Project", 174),
    ("1.7 Organization of the Report", 179),
    ("Chapter 2 Literature Review", 181),
    ("2.1 Short Introduction about the Literature", 183),
    ("2.2 Literature Review Summary", 190),
    ("2.3 Research Gap and Project Improvement", 203),
    ("2.4 Summary of Literature Review", 205),
    ("Chapter 3 Requirements, Methodology and System Design", 220),
    ("3.1 Software and Hardware Requirements", 222),
    ("3.2 Dataset / Data Source / Input Source", 233),
    ("3.3 Methodology", 242),
    ("3.4 System Architecture", 250),
    ("3.5 Algorithms", 256),
    ("3.6 Tools and Technology Stack", 262),
    ("Chapter 4 Design, Implementation, Testing and Results", 279),
    ("4.1 Design Overview", 281),
    ("4.2 Module Design and Organization", 291),
    ("4.3 Implementation Details", 293),
    ("4.4 Explanation of Key Functions", 299),
    ("4.5 Repository Summary", 351),
    ("4.6 Testing Methodology", 356),
    ("4.7 Test Cases and Validation", 363),
    ("4.8 Results and Discussion", 366),
    ("4.9 Project Management Evidence", 383),
    ("Chapter 5 Conclusion and Future Scope", 386),
    ("5.1 Project Conclusion", 388),
    ("5.2 Future Enhancements / Scope for Future Work", 396),
    ("References", 417),
    ("Annexures", 445),
]

FIGURES = [
    ("Figure 1.1", "AI-Ready Laptop Health Monitoring System", 153),
    ("Figure 3.1", "System Architecture", 255),
    ("Figure 3.2", "Workflow", 261),
    ("Figure 4.1", "Laptop Health Monitor Dashboard Interface", 311),
    ("Figure 4.2", "Real-Time System Monitoring Interface", 315),
    ("Figure 4.3", "Temperature Monitoring Interface", 319),
    ("Figure 4.4", "Remaining Useful Life Prediction Interface", 323),
    ("Figure 4.5", "System Health History Interface", 327),
    ("Figure 4.6", "Preventive-Maintenance Recommendations Interface", 331),
    ("Figure 4.7", "Storage Manager Interface", 335),
    ("Figure 4.8", "Smart Uninstaller Interface", 338),
    ("Figure 4.9", "Complete System Data Interface", 342),
    ("Figure 4.10", "Report Generation and Export Interface", 346),
    ("Figure 4.11", "About and System Information Interface", 350),
    ("Figure 4.3", "Trello", 384),
]

TABLES = [
    ("Table 1.1", "Ił Framework Summary", 166),
    ("Table 1.2", "Report of the Organization", 180),
    ("Table 2.1", "Literature Review Summary", 202),
    ("Table 2.2", "Research Gap and Proposed Improvement", 204),
    ("Table 3.1", "Software and Hardware Requirements", 232),
    ("Table 3.2", "Data Source Summary", 241),
    ("Table 3.3", "Methodology", 249),
    ("Table 3.4", "Tools and Technology Stack", 263),
    ("Table 4.1", "Module Design and Organization", 292),
    ("Table 4.2", "Repository Summary", 355),
    ("Table 4.3", "Consolidated Test Cases and Validation Results", 365),
    ("Table 4.4", "Results and Discussion Summary", 382),
]

SCREENSHOTS = [
    ("A2.1", "Dashboard and Live System Health Output", 4013),
    ("A2.2", "Real-Time System Monitoring Output", 4016),
    ("A2.3", "Temperature Monitoring Output", 4018),
    ("A2.4", "RUL Prediction and AI Model Status Output", 4025),
    ("A2.5", "System Health History Output", 4027),
    ("A2.6", "Preventive-Maintenance Recommendations Output", 4034),
    ("A2.7", "Storage Manager Output", 4036),
    ("A2.8", "Smart Uninstaller and Installed-Program Output", 4044),
    ("A2.9", "Complete System Data Output", 4046),
    ("A2.10", "Report Generation and Export Interface", 4054),
    ("A2.11", "Application Settings Interface", 4056),
    ("A2.12", "About and System Information Interface", 4064),
    (
        "A2.13(a)",
        "NASA Battery RUL Model Training Output Evidence – Part 1 of 3",
        4087,
    ),
    (
        "A2.13(b)",
        "NASA Battery RUL Model Training Output Evidence – Part 2 of 3",
        4096,
    ),
    (
        "A2.13(c)",
        "NASA Battery RUL Model Training Output Evidence – Part 3 of 3",
        4106,
    ),
]


def resize_table(table, required_rows):
    while len(table.rows) < required_rows:
        table._tbl.append(deepcopy(table.rows[-1]._tr))
    while len(table.rows) > required_rows:
        table._tbl.remove(table.rows[-1]._tr)


def clear_paragraph(paragraph):
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)


def add_bookmark(paragraph, name, bookmark_id):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def add_pageref(paragraph, bookmark):
    clear_paragraph(paragraph)
    begin_run = OxmlElement("w:r")
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "true")
    begin_run.append(begin)
    instr_run = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" PAGEREF {bookmark} \\h "
    instr_run.append(instr)
    sep_run = OxmlElement("w:r")
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    sep_run.append(sep)
    result_run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "0"
    result_run.append(text)
    end_run = OxmlElement("w:r")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    end_run.append(end)
    for element in (begin_run, instr_run, sep_run, result_run, end_run):
        paragraph._p.append(element)


def populate(document, table_index, headers, entries, bookmark_map):
    table = document.tables[table_index]
    resize_table(table, len(entries) + 1)
    for col, text in enumerate(headers):
        table.cell(0, col).text = text
    for row_index, entry in enumerate(entries, 1):
        label, title, paragraph_index = entry
        table.cell(row_index, 0).text = label
        table.cell(row_index, 1).text = title
        add_pageref(
            table.cell(row_index, 2).paragraphs[0],
            bookmark_map[paragraph_index],
        )


def main():
    document = Document(SOURCE)
    target_indices = sorted(
        {p for _, p in CONTENTS}
        | {p for _, _, p in FIGURES}
        | {p for _, _, p in TABLES}
        | {p for _, _, p in SCREENSHOTS}
    )
    bookmark_map = {}
    for bookmark_id, paragraph_index in enumerate(target_indices, 1):
        name = f"idx_target_{paragraph_index}"
        add_bookmark(document.paragraphs[paragraph_index], name, bookmark_id)
        bookmark_map[paragraph_index] = name

    contents_table = document.tables[4]
    resize_table(contents_table, len(CONTENTS) + 1)
    contents_table.cell(0, 0).text = "Section"
    contents_table.cell(0, 1).text = "Page No."
    for row_index, (title, paragraph_index) in enumerate(CONTENTS, 1):
        contents_table.cell(row_index, 0).text = title
        add_pageref(
            contents_table.cell(row_index, 1).paragraphs[0],
            bookmark_map[paragraph_index],
        )

    populate(
        document,
        5,
        ("Figure No.", "Figure Title", "Page No."),
        FIGURES,
        bookmark_map,
    )
    populate(
        document,
        6,
        ("Table No.", "Table Title", "Page No."),
        TABLES,
        bookmark_map,
    )
    populate(
        document,
        7,
        ("Screenshot No.", "Screenshot Title", "Page No."),
        SCREENSHOTS,
        bookmark_map,
    )

    settings = document.settings._element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document.save(OUTPUT)
    print(f"Saved: {OUTPUT}")
    print(
        f"Entries: contents={len(CONTENTS)}, figures={len(FIGURES)}, "
        f"tables={len(TABLES)}, screenshots={len(SCREENSHOTS)}"
    )


if __name__ == "__main__":
    main()
