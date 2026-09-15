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




--------------------------------------------------------------------------------------------------


# Identification method update

The previous classifier mainly compared general layout measurements, including ink density, row and column distribution, and page balance. This sometimes caused dense Page 3 pages to be identified as Page 1, or handwritten Page 2 pages to be identified as Page 3.

The updated method still uses Pillow and does not require OpenCV. It first checks for continuous table lines as the main Page 1 pattern. It then checks for repeated small marks with regular horizontal spacing, similar to dotted leaders, as the main Page 3 pattern. If neither fixed printed pattern is detected, the image is treated as the handwritten Page 2 format. OCR-based keyword identification may be added later after the team confirms which OCR model will be used.

# Known exception: Box Hill pages 84–86

Box Hill pages 1973-0002-00001-00001_00084.png to 1973-0002-00001-00001_00086.png appear consecutively in the original archive and are expected to belong to the same survey bundle. However, pages 84 and 85 use older or different printed layouts that do not match the standard Page 1 and Page 2 formats used by the other records. Page 86 still matches the usual dotted-list Page 3 format.

For the current review, pages 84 and 85 should be treated as Additional pages instead of being forced into the standard Page 1 or Page 2 categories. They should still remain associated with page 86 as one bundle based on the original archive order. This exception is documented for later discussion and has not yet been added as a special rule in the classifier. The other pages reviewed in the current datasets are being identified correctly.








----------------------------------------------------------------------------------------------------------------------------------------
### Page identification and bundling

The current implementation uses image features with Pillow and does not require an OCR model. Each image is classified independently. Page 1 is identified using table lines, Page 3 using dotted layout patterns, and Page 2 using handwriting-like strokes.

Recent fixes improve the distinction between sparse handwritten notes and blank sheets. Handwriting detection uses a higher-resolution image and local contrast, with an additional rotated analysis for sideways notes. Filters reduce false detections caused by paper texture, irregular dotted bleed-through, small print fragments, punch holes, and creases near the paper edges.

Images are processed in natural filename order within each scan folder. Each Page 1 starts a new bundle, which continues until the next Page 1. Blank and additional pages remain in the current bundle. Pages before the first Page 1 have no bundle ID. Repeated Page 2 or Page 3 pages keep their page type and bundle ID, with `is_additional` set to `true`.

Run `python main.py` using the input folders configured in `INPUT_FOLDERS`. The output contains `survey_output.json` and four image folders: `main`, `notes`, `coded`, and `additional`. Original image filenames are preserved, and bundle IDs are recorded in JSON. `additional_count` includes both additional pages and repeated pages flagged within bundles.

The latest changes were checked against six supplied scans and synthetic image and bundling tests. Classification remains heuristic, so these checks do not establish accuracy across the full dataset.
