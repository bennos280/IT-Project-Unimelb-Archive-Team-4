import fitz
from pathlib import Path

pdf_path = Path("1973-0002-00002-00001.PDF")
output_folder = Path("split_brighton_01")

output_folder.mkdir(exist_ok=True)

pdf = fitz.open(pdf_path)

for i, page in enumerate(pdf, start=1):
    pix = page.get_pixmap(dpi=200, alpha=False)

    output_name = f"{pdf_path.stem}_{i:05d}.png"
    output_path = output_folder / output_name

    pix.save(output_path)

    print(f"Saved: {output_name}")

pdf.close()

print(f"\nDone. {i} pages converted.")