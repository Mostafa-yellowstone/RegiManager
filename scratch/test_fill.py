from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject

reader = PdfReader("core/static/core/pdf/mv82_template.pdf")
writer = PdfWriter()
writer.append_pages_from_reader(reader)

# Force AcroForm copy
if "/AcroForm" in reader.trailer["/Root"]:
    writer.root_object.update({
        NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]
    })

fields = {
    "NAME OF PRIMARY REGISTRANT Last First Middle or Business Name": "TEST NAME",
    "VEHICLE IDENTIFICATION NUMBER": "1234567890ABCDEFG"
}

for page in writer.pages:
    writer.update_page_form_field_values(page, fields)

with open("scratch/test_filled.pdf", "wb") as f:
    writer.write(f)

# Now check if the fields in the NEW PDF have values
reader2 = PdfReader("scratch/test_filled.pdf")
fields2 = reader2.get_fields()
if fields2:
    for name, field in fields2.items():
        val = field.get("/V", "BLANK")
        if val != "BLANK":
            print(f"Field {name} HAS VALUE: {val}")
else:
    print("No fields in generated PDF.")
