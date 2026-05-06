from pypdf import PdfReader

reader = PdfReader("core/static/core/pdf/mv82_template.pdf")
fields = reader.get_fields()

if fields:
    for name, field in fields.items():
        print(f"Field: {name}, Type: {field.get('/FT', 'Unknown')}")
else:
    print("No form fields found.")
