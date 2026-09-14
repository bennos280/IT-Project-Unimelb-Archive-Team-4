# Prest survey digitisation (Team 4)

## Setup

1. Python 3.12
2. `pip install -r requirements.txt`
3. Claude Code CLI, signed in: `claude auth login`
4. Copy `.env.example` to `.env`
5. Survey PDFs go in `data/<unit>/` (not in git): https://archives.library.unimelb.edu.au/nodes/view/499420

## How to run

Split a PDF into page images, sorted by kind (`main`, `coded`, `notes`, `other`):

    python pipeline/identify.py data/216444/1256580_1973-0002-00033.pdf

Output: `data/pages/216444/<kind>/216444_p000.jpg ...` and `data/pages/216444/pages.json`.

Transcribe one page (the folder name picks the template):

    python pipeline/transcribe.py source/coded/216412_p003.jpg

Output: `answers/<model>-<effort>/216412_p003.json`.

Score answers against the hand-typed truth:

    python pipeline/score.py --pages

## Tests

    python pipeline/test_identify.py

Every page in `source/<kind>/` must be identified as its folder.

## Notes

Prompt = `pipeline/prompt.txt` + the template for the page kind. Tweak, rerun, compare.
New answer key: copy the template to `truth/<kind>/<page>.json` and fill it in from the image.
