from pypdf import PdfReader, PdfWriter

reader = PdfReader("core/static/core/pdf/mv82_template.pdf")
writer = PdfWriter()
writer.append_pages_from_reader(reader)

fields = writer.get_fields()
if fields:
    for name, field in fields.items():
        print(f"Writer Field: {name}")
else:
    print("No fields in writer after append.")
