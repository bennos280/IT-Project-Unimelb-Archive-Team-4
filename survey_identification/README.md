Survey Page Identification

This code identifies survey images as Page 1, Page 2 or Page 3, keeps their original order, assigns bundle IDs, and copies them into the corresponding folders.

1. Source data

The Box Hill images come from 1973-0002-00001-00001.pdf and are stored in split_boxhill_00/ after conversion.

The Brighton images come from 1973-0002-00002-00001.pdf and are stored in split_brighton_01/ after conversion.

The PDFs were downloaded from the official archive website and converted into separate PNG images with split-pdf.py.

Each output filename keeps the original PDF reference and adds a five-digit page number, for example:

1973-0002-00001-00001_00001.png
1973-0002-00001-00001_00002.png
1973-0002-00001-00001_00100.png

The page number follows the original PDF and website order. Because it is zero-padded, natural filename sorting preserves the correct order.

2. Page identification

Each image is identified independently from its visual layout. The filename and neighbouring pages are not used to decide whether it is Page 1, Page 2 or Page 3.

page_1 / main: the main survey form with a printed table layout.

page_2 / notes: mainly handwritten notes with large blank areas.

page_3 / coded: coded or summary content arranged in columns.

additional_page / additional: an image whose page format cannot currently be identified.

The classifier uses Pillow to measure visual layout features such as table lines, content distribution and ink density. Identifying a page from printed keywords such as Address would require OCR. Because the team has not yet confirmed the final OCR method, this version uses layout-based identification instead.

3. Bundle logic

Box Hill and Brighton are processed independently, so a bundle does not cross between the two areas. A newly identified Page 1 starts a new bundle, and the following images remain in that bundle until the next Page 1 appears.

The bundle logic does not rename the exported images. Bundle membership is stored only in survey_output.json, where each image_id is linked to its corresponding bundle_id.

4. Additional-page handling

Additional records a page's special status without replacing a known page type. A repeated Page 2 or Page 3 remains in the notes or coded folder and is marked as Additional only in JSON. A Page 2 or Page 3 found before the first Page 1 is handled in the same way but has no bundle ID. Only an image whose format cannot be identified is copied to the additional folder. Every source image is still exported to an image folder.

5. Current input and output

This version currently processes split_boxhill_00/ and split_brighton_01/. It creates survey_output.json and copies the classified images into output/classified/main/, output/classified/notes/, output/classified/coded/ and output/classified/additional/.

The images keep their original filenames. The JSON records each image's ID, source area, predicted page type, bundle ID, Additional status and exported location. It also records the total image count and page counts so the output can be checked for completeness.