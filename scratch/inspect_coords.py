from pypdf import PdfReader

reader = PdfReader("core/static/core/pdf/mv82_template.pdf")
for page_num, page in enumerate(reader.pages):
    if "/Annots" in page:
        for annot in page["/Annots"]:
            obj = annot.get_object()
            if "/T" in obj:
                field_name = obj["/T"]
                rect = obj["/Rect"]
                # Rect is [x1, y1, x2, y2]
                print(f"Page {page_num+1} | Field: {field_name} | Rect: {rect}")
