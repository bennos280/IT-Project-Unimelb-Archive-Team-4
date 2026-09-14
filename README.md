# Prest survey digitisation (Team 4)

Needs Python 3.12, `pip install -r requirements.txt`, and the Claude Code CLI signed in (`claude auth login`). Copy `.env.example` to `.env`.

    python pipeline/preprocess.py source --output source-pre        # optional: deskew, contrast, binarise; same filenames
    python pipeline/transcribe.py source/coded/216412_p003.jpg     # -> answers/<model>-<effort>/
    python pipeline/score.py --pages                               # answers vs truth

Prompt = `prompt.txt` + the template for whichever folder the image is in. Tweak, rerun, compare.
New answer key: copy the template to `truth/<kind>/<page>.json` and fill it in from the image.
Survey PDFs go in `data/` (not in git): https://archives.library.unimelb.edu.au/nodes/view/499420