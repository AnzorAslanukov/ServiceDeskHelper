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

LLM_INDEX_PAGES_PROMPT = """
You are an intelligent assistant designed to identify the start of individual pages within a given document text.
The document text is from a OneNote exported DOCX file, which contains multiple pages.
Each page starts with a page title, immediately followed by a date and time string.
Your task is to identify these page titles, their corresponding date/time strings, and create a unique demarcation string for each page.
The date/time string most closely resembles these formats: "Friday, December 18, 2020\n9:08 AM" and "Friday, December 18, 2020 9:08 AM".
If the date/time format is different from the already mentioned one, then do not count it for demarcation pruposes and ignore it. 
Here is how the date/time format needs to look like for it to qualify for demarcation: (Name of the week day), (name of month) DD, YYYY HH:MM AM/PM. 
Here are examples of date/time formats that are incorrect and must not be considered for demarcation: "string" - (name of month) DD, YYYY or (name of month)/DD/YYYY or MM/DD/YYYY. 

Output the information as a JSON array of strings. Each string should be the exact concatenation of the "page_title" and "page_datetime" as they appear in the document text, including all whitespace and line breaks between them. This string will be used to precisely locate the start of each page.

The order of strings in the array must match the order of pages in the document.
DO NOT include any conversational text, explanations, or code examples. ONLY output the JSON array.

Now, process the following document text:

---DOCUMENT_TEXT_START---
{{document_content}}
---DOCUMENT_TEXT_END---
"""

LLM_EXTRACT_PAGE_DATA_PROMPT = """
You are an intelligent parser designed to extract structured information for a single page from a larger document.
You will be provided with a section of text that contains the content of one or more pages, but you should focus on extracting data for a specific page identified by its title.
Your task is to extract the page's title, its body content, and its creation datetime.

The creation datetime format will typically be like: "Wednesday, September 2, 2020 4:32 PM".
The page title is usually at the beginning of the page.

Prioritize providing the full 'page_body_text'. Only summarize if the full content *cannot* be included without exceeding the API's maximum token limit.
If a summary is provided, ensure it accurately represents the main points of the page.

Output the extracted information as a JSON object with the following keys:
- "page_title": The title of the page.
- "page_body_text": The main content of the page, or a concise summary if the full content is too long.
- "page_datetime": The creation datetime of the page, exactly as found in the text. If not found, use "N/A".
- "is_summary": A boolean (true/false) indicating if 'page_body_text' is a summary (true) or the full content (false).

DO NOT include any conversational text, explanations, or code examples. ONLY output the JSON object.

Now, parse the following page content, focusing on the page titled "{{target_page_title}}":

---PAGE_CONTENT_START---
{{page_content}}
---PAGE_CONTENT_END---
"""
