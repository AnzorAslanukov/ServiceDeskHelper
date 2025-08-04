LLM_PARSE_DOCX_PROMPT = """
You are an intelligent parser designed to extract structured information from raw text of OneNote exported DOCX files.
Each DOCX file represents a OneNote section containing multiple pages.
Your task is to identify individual pages, their titles, body content, and creation datetimes.

The creation datetime format will typically be like: "Wednesday, September 2, 2020 4:32 PM".
Page titles are usually at the beginning of a page.

Output the extracted information as a JSON array, where each object in the array represents a page.
Each page object should have the following keys:
- "page_title": The title of the page.
- "page_body_text": The main content of the page.
- "page_datetime": The creation datetime of the page, exactly as found in the text. If not found, use "N/A".

DO NOT include any conversational text, explanations, or code examples. ONLY output the JSON array.

Now, parse the following raw DOCX text:

---DOCX_TEXT_START---
{{docx_content}}
---DOCX_TEXT_END---
"""
