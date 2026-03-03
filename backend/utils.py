import aiofiles
import urllib
import mistune
import os
import re
from typing import Iterable, List, Optional

DEFAULT_WORD_FONT_CHAIN = ["仿宋", "FangSong", "STFangsong"]


def _normalize_word_fonts(word_fonts: Optional[Iterable[str] | str]) -> List[str]:
    if word_fonts is None:
        env_fonts = os.getenv("WORD_EXPORT_FONTS", "")
        word_fonts = env_fonts if env_fonts else DEFAULT_WORD_FONT_CHAIN

    if isinstance(word_fonts, str):
        candidates = [font.strip() for font in re.split(r"[,，;\n]+", word_fonts)]
    else:
        candidates = [str(font).strip() for font in word_fonts]

    deduped_fonts = []
    seen_fonts = set()
    for font in candidates:
        if font and font not in seen_fonts:
            deduped_fonts.append(font)
            seen_fonts.add(font)

    return deduped_fonts or DEFAULT_WORD_FONT_CHAIN.copy()


def _set_r_fonts(target, east_asia_font: str, latin_font: str, complex_script_font: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    r_pr = target._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)

    r_fonts.set(qn("w:eastAsia"), east_asia_font)
    r_fonts.set(qn("w:ascii"), latin_font)
    r_fonts.set(qn("w:hAnsi"), latin_font)
    r_fonts.set(qn("w:cs"), complex_script_font)


def _apply_word_fonts(doc, font_chain: List[str]) -> None:
    east_asia_font = font_chain[0]
    latin_font = font_chain[1] if len(font_chain) > 1 else east_asia_font
    complex_script_font = font_chain[2] if len(font_chain) > 2 else east_asia_font

    for style_name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "Heading 4"):
        if style_name in doc.styles:
            style = doc.styles[style_name]
            style.font.name = latin_font
            _set_r_fonts(style, east_asia_font, latin_font, complex_script_font)

    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            run.font.name = latin_font
            _set_r_fonts(run, east_asia_font, latin_font, complex_script_font)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = latin_font
                        _set_r_fonts(run, east_asia_font, latin_font, complex_script_font)

async def write_to_file(filename: str, text: str) -> None:
    """Asynchronously write text to a file in UTF-8 encoding.

    Args:
        filename (str): The filename to write to.
        text (str): The text to write.
    """
    # Ensure text is a string
    if not isinstance(text, str):
        text = str(text)

    # Convert text to UTF-8, replacing any problematic characters
    text_utf8 = text.encode('utf-8', errors='replace').decode('utf-8')

    async with aiofiles.open(filename, "w", encoding='utf-8') as file:
        await file.write(text_utf8)

async def write_text_to_md(text: str, filename: str = "") -> str:
    """Writes text to a Markdown file and returns the file path.

    Args:
        text (str): Text to write to the Markdown file.

    Returns:
        str: The file path of the generated Markdown file.
    """
    file_path = f"outputs/{filename[:60]}.md"
    await write_to_file(file_path, text)
    return urllib.parse.quote(file_path)

def _preprocess_images_for_pdf(text: str) -> str:
    """Convert web image URLs to absolute file paths for PDF generation.
    
    Transforms /outputs/images/... URLs to absolute file:// paths that
    weasyprint can resolve.
    """
    import re
    
    base_path = os.path.abspath(".")
    
    # Pattern to find markdown images with /outputs/ URLs
    def replace_image_url(match):
        alt_text = match.group(1)
        url = match.group(2)
        
        # Convert /outputs/... to absolute path
        if url.startswith("/outputs/"):
            abs_path = os.path.join(base_path, url.lstrip("/"))
            return f"![{alt_text}]({abs_path})"
        return match.group(0)
    
    # Match ![alt text](/outputs/images/...)
    pattern = r'!\[([^\]]*)\]\((/outputs/[^)]+)\)'
    return re.sub(pattern, replace_image_url, text)


async def write_md_to_pdf(text: str, filename: str = "") -> str:
    """Converts Markdown text to a PDF file and returns the file path.

    Args:
        text (str): Markdown text to convert.

    Returns:
        str: The encoded file path of the generated PDF.
    """
    file_path = f"outputs/{filename[:60]}.pdf"

    try:
        # Resolve css path relative to this backend module to avoid
        # dependency on the current working directory.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        css_path = os.path.join(current_dir, "styles", "pdf_styles.css")
        
        # Preprocess image URLs for PDF compatibility
        processed_text = _preprocess_images_for_pdf(text)
        
        # Set base_url to current directory for resolving any remaining relative paths
        base_url = os.path.abspath(".")

        from md2pdf.core import md2pdf
        md2pdf(file_path,
               md_content=processed_text,
               # md_file_path=f"{file_path}.md",
               css_file_path=css_path,
               base_url=base_url)
        print(f"Report written to {file_path}")
    except Exception as e:
        print(f"Error in converting Markdown to PDF: {e}")
        return ""

    encoded_file_path = urllib.parse.quote(file_path)
    return encoded_file_path

async def write_md_to_word(
    text: str,
    filename: str = "",
    word_fonts: Optional[Iterable[str] | str] = None
) -> str:
    """Converts Markdown text to a DOCX file and returns the file path.

    Args:
        text (str): Markdown text to convert.
        word_fonts: Priority font list for DOCX export. First is preferred.

    Returns:
        str: The encoded file path of the generated DOCX.
    """
    file_path = f"outputs/{filename[:60]}.docx"

    try:
        from docx import Document
        from htmldocx import HtmlToDocx
        # Convert report markdown to HTML
        html = mistune.html(text)
        # Create a document object
        doc = Document()
        # Convert the html generated from the report to document format
        HtmlToDocx().add_html_to_document(html, doc)
        _apply_word_fonts(doc, _normalize_word_fonts(word_fonts))

        # Saving the docx document to file_path
        doc.save(file_path)

        print(f"Report written to {file_path}")

        encoded_file_path = urllib.parse.quote(file_path)
        return encoded_file_path

    except Exception as e:
        print(f"Error in converting Markdown to DOCX: {e}")
        return ""
