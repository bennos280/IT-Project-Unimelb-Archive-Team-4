##Every sample page in source/<kind>/ must be identified as its folder
import sys
from pathlib import Path
import pypdfium2 as pdfium
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "pipeline"))
from identify import ROOT, main

def test_main_pages():
    shutil.rmtree("data",ignore_errors=True)    # delete data folder
    main_output_folder = ROOT / "data"/ "pages"/"main_pages"/ "main"   # folder that identify.py outputs tests to
    main_pdf = ROOT / "tests" /"test_page_identification" /"test_cases" / "main_pages.pdf"   # folder that main pages test cases are

    # count the number of pages in the actual test case
    pdf = pdfium.PdfDocument(str(main_pdf))
    expected_count = len(pdf)

    # call identify.py
    main([str(main_pdf)])

    actual_count = len(list(main_output_folder.glob("*.jpg")))
    assert expected_count == actual_count

def test_coded_pages():
    shutil.rmtree("data",ignore_errors=True)    # delete data folder
    coded_output_folder = ROOT / "data"/ "pages"/"coded_pages"/ "coded"   # folder that identify.py outputs tests to
    coded_pdf = ROOT / "tests" /"test_page_identification" /"test_cases" / "coded_pages.pdf"   # folder that main pages test cases are

    # count the number of pages in the actual test case
    pdf = pdfium.PdfDocument(str(coded_pdf))
    expected_count = len(pdf)

    # call identify.py
    main([str(coded_pdf)])

    actual_count = len(list(coded_output_folder.glob("*.jpg")))
    assert expected_count == actual_count

def test_notes_pages():
    shutil.rmtree("data",ignore_errors=True)    # delete data folder
    text_output_folder = ROOT / "data"/ "pages"/"notes_pages"/ "notes"   # folder that identify.py outputs tests to
    text_pdf = ROOT / "tests" /"test_page_identification" /"test_cases" / "notes_pages.pdf"   # folder that main pages test cases are

    # count the number of pages in the actual test case
    pdf = pdfium.PdfDocument(str(text_pdf))
    expected_count = len(pdf)

    # call identify.py
    main([str(text_pdf)])

    actual_count = len(list(text_output_folder.glob("*.jpg")))
    assert expected_count == actual_count


def test_other_pages():
    shutil.rmtree("data",ignore_errors=True)    # delete data folder
    other_output_folder = ROOT / "data"/ "pages"/"other_pages"/ "other"   # folder that identify.py outputs tests to
    other_pdf = ROOT / "tests" /"test_page_identification" /"test_cases" / "other_pages.pdf"   # folder that main pages test cases are

    # count the number of pages in the actual test case
    pdf = pdfium.PdfDocument(str(other_pdf))
    expected_count = len(pdf)

    # call identify.py
    main([str(other_pdf)])

    actual_count = len(list(other_output_folder.glob("*.jpg")))
    assert expected_count == actual_count