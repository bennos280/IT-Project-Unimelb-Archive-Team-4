import json
import sqlite3
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = (ROOT / "backend/wilfprestsurvey.db").resolve()
DATA_DICT = (ROOT / "data_dict.json").resolve()
CODED_CAT = "coded"

#keys in manifest json
M_INPUT = "input"
M_PAGES = "pages"
M_PAGE_PATH = "path"
M_PAGE_LABEL = "label"
M_PAGE_TRANSCRIPT = "transcript"
#keys in page json
ENGINE = "engine"
MODEL = "model"
EFFORT = "effort"
SECONDS = "seconds"
RESIDENTS = "residents"
ANNOTATIONS = "annotations"
ANN_RAW = "raw"
ANN_LOCATION = "location"
OTHER_CHILDREN = "other_children"
CHILD_DIED = "died"
CHILD_ELSEWHERE = "living_elsewhere"

#clears database, reads everything in output folder and inserts into db
def insert_outputs():
    #clear database
    reset_db()

    #get folder of output
    output = Path(os.getenv('OUTPUT'))
    output_dir = (ROOT / output).resolve()

    #import all runs in output to database
    files = output_dir.rglob('*manifest.json')
    for f in files:
        insert_bundle(f)

#if database file doesn't exist, creates database
#if it does exist, deletes everything, remakes new empty tables
def reset_db():
    con = sqlite3.connect(DB, autocommit=True)
    cur = con.cursor()

    #get create and drop sql commands
    create_fp = Path(__file__).parent / "create.sql"
    drop_fp = Path(__file__).parent / "drop.sql"
    with open(create_fp, 'r', encoding='utf-8') as f:
        create = f.read()
    with open(drop_fp, 'r', encoding='utf-8') as f:
        drop = f.read()

    #execute commands
    cur.executescript(drop)
    cur.execute("PRAGMA foreign_keys = ON;")
    cur.executescript(create)
    con.close()

#insert all pages from a manifest.json into db
def insert_bundle(manifest:Path):
    con = sqlite3.connect(DB, autocommit=True)
    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    with open(manifest, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    #insert bundle
    bundle_id = None
    if data.get(M_PAGES):
        #splice out 'bundle_id' from
        #.../data/bundle_id.pdf"
        bundle_id = data[M_INPUT].rsplit("/",1)[1].split(".")[0]
        cur.execute("""INSERT OR IGNORE INTO bundles(bundle_id, source_pdf) 
            VALUES(?, ?)""", (bundle_id, data[M_INPUT]))
    else:
        print("Bundle has no pages.")
        return
    
    #insert pages
    for mkey, mval in data.items():
        if mkey == M_PAGES:
            for p in mval:
                page_fp = None #path of page json
                img_fp = None #path of image
                categ = None
                blank = False

                for key, value in p.items():
                    if key == M_PAGE_LABEL:
                        if value == "blank":
                            blank = True
                        categ = value
                    elif key == M_PAGE_PATH:
                        img_fp = value
                    elif key == M_PAGE_TRANSCRIPT and img_fp is not None:
                        #.../output/bundle_id/pages/whatever_00001.png
                        #transcribe/whatever_00001.json
                        page_fp = img_fp.rsplit("pages/", 1)[0] + value
                    else:
                        pass

                if blank and img_fp is not None and bundle_id is not None:
                    insert_blank_page(img_fp, "survey_id", bundle_id, con)
                elif page_fp is not None and img_fp is not None and categ is not None and bundle_id is not None:
                    insert_page(page_fp, img_fp, categ, "survey_id", bundle_id, con)
                else:
                    print(f"Incomplete page info cannot insert page.")
    con.close()

def insert_blank_page(img_fp:str, survey_id:str, bundle_id:str, con):
    #.../pages/page_id.png
    page_id = img_fp.rsplit("/", 1)[1].split(".")[0]

    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    #insert survey if not already in db
    cur.execute("INSERT OR IGNORE INTO surveys(survey_id, bundle_id) VALUES(?, ?)", (survey_id, bundle_id))
    #insert page category if not already in db
    cur.execute("INSERT OR IGNORE INTO categories VALUES('blank')")

    #insert page
    res = cur.execute("SELECT page_id FROM pages WHERE page_id=?", (page_id,))
    if res.fetchone() is not None:
        print(f"page {page_id} already in database!")
        return
    else:
        cur.execute("""
            INSERT INTO pages(page_id, import_path, survey_id, bundle_id, category)
            VALUES(?, ?, ?, ?, ?);
        """, (page_id, img_fp, survey_id, bundle_id, 'blank'))

#insert a single page into db
#will ignore if pageid is already in db
#if coded page, decoded values are pulled from the data_dict.json and put into database
def insert_page(page_fp:str, img_fp:str, category:str, survey_id:str, bundle_id:str, con):
    page_id = page_fp.rsplit("/", 1)[1].split(".")[0]

    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    #insert survey if not already in db
    cur.execute("INSERT OR IGNORE INTO surveys(survey_id, bundle_id) VALUES(?, ?)", (survey_id, bundle_id))
    #insert page category if not already in db
    cur.execute("INSERT OR IGNORE INTO categories VALUES(?)", (category,))

    #insert page
    res = cur.execute("SELECT page_id FROM pages WHERE page_id=?", (page_id,))
    if res.fetchone() is not None:
        print(f"page {page_id} already in database!")
        return
    else:
        cur.execute("""
            INSERT INTO pages(page_id, import_path, survey_id, bundle_id, category)
            VALUES(?, ?, ?, ?, ?);
        """, (page_id, img_fp, survey_id, bundle_id, category))

    #do flags first!!

    with open(page_fp, 'r', encoding='utf-8') as file:
        data = json.load(file)

    #insert page data abt the ai model and runtime stuff
    cur.execute("""
        UPDATE pages SET engine = ?, model = ?, effort = ?, runtime = ?
        WHERE page_id = ?;
    """, (data[ENGINE], data[MODEL], data[EFFORT], data[SECONDS], page_id))

    #insert fields
    for key, value in data.items():

        #insert residents and resident fields
        if key == RESIDENTS:
            resident_no = 1
            for resident in value:
                cur.execute("""
                    INSERT INTO residents(page_id, resident_no)
                    VALUES(?, ?);
                """, (page_id, resident_no))
                for title, raw in resident.items():
                    cur.execute("""
                        INSERT INTO resident_fields(page_id, resident_no, resident_field_title, text_raw)
                        VALUES(?, ?, ?, ?);
                    """, (page_id, resident_no, title, raw))
                resident_no += 1

        #insert annotations
        elif key == ANNOTATIONS:
            annotation_no = 1
            for annotation in value:
                cur.execute("""
                    INSERT INTO annotations(page_id, annotation_no, text_raw, location)
                    VALUES(?, ?, ?, ?);
                """, (page_id, annotation_no, annotation[ANN_RAW], annotation[ANN_LOCATION]))
                annotation_no += 1

        #insert other children
        elif key == OTHER_CHILDREN:
            child_no = 1
            #"other_children": {
            #    "died": [],
            #    "living_elsewhere": []
            for location, children in value.items():
                if location == CHILD_DIED and children:
                    for child in children:
                        cur.execute("""
                            INSERT INTO other_children(page_id, child_no, text_raw, location)
                            VALUES(?, ?, ?, ?);
                        """, (page_id, child_no, child, CHILD_DIED))
                        child_no += 1
                elif location == CHILD_ELSEWHERE and children:
                        cur.execute("""
                            INSERT INTO other_children(page_id, child_no, text_raw, location)
                            VALUES(?, ?, ?, ?);
                        """, (page_id, child_no, child, CHILD_ELSEWHERE))
                        child_no += 1

        #insert regular field
        elif key != ENGINE and key != MODEL and key != EFFORT and key != SECONDS:
            insert_field(page_id, f"{key}", value, con, category==CODED_CAT)

#if a field is nested, recursively joins titles together with . (eg kitchen.shared)
def insert_field(page_id, title:str, raw, con, coded:bool):
    cur = con.cursor()

    if isinstance(raw, dict):
        #recurse for each subfield
        for subtitle, subraw in raw.items():
            insert_field(page_id, title + "." + f"{subtitle}", subraw, con, coded)
    else:
        #hit lowest level

        decoded = None
        #get decoded value if page is coded, otherwise just leave as None
        if coded and raw is not None:
            with open(DATA_DICT, 'r', encoding='utf-8') as file:
                coded_dict = json.load(file)

                cfield = coded_dict["pages"]["3"]["fields"].get(title)
                if cfield is not None:
                    poss_vals = cfield["possible_values"]
                    if poss_vals != "N/A":
                        for num, text in poss_vals.items():
                            if (int(raw) == int(num)) or (len(num.split("-")) > 1 and num.split("-")[0] <= int(raw) and num.split[1] >= int(raw)):
                                decoded = text

        #insert field
        cur.execute("""
            INSERT INTO fields(page_id, field_title, text_raw, decoded_value)
            VALUES(?, ?, ?, ?);
        """, (page_id, title, raw, decoded))


insert_outputs()