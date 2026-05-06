from pypdf import PdfReader
import os

pdf_path = "core/static/core/pdf/dtf802_template.pdf"
reader = PdfReader(pdf_path)
fields = reader.get_fields()

if fields:
    for name, field in fields.items():
        print(f"'{name}': '',")
else:
    print("No interactive fields found.")
