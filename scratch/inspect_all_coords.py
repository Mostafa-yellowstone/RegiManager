from pypdf import PdfReader

reader = PdfReader("core/static/core/pdf/mv82_template.pdf")
fields = reader.get_fields()
for name, field in fields.items():
    # Try to find the annotation object
    if "/Kids" in field:
        for kid in field["/Kids"]:
            obj = kid.get_object()
            if "/Rect" in obj:
                print(f"Field: {name} | Rect: {obj['/Rect']}")
    elif "/Rect" in field:
        print(f"Field: {name} | Rect: {field['/Rect']}")
