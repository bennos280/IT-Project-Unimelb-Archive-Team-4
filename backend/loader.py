import json
import sqlite3
import os
from dotenv import load_dotenv
from pathlib import Path

DB = "wilfprestsurvey.db"
CODED_DICT = "../data_dict.json" #location of dict relative to this file
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

#name of folders
#.../output/bundle_id/pages/whatever_00001.png 
load_dotenv()
os.getenv('OUTPUT') #!!!!!!!!!!fix this 
DIR_OUTPUT = os.getenv("OUTPUT").rpartition("/")[2] #partition for absolute path
DIR_PAGES = "pages"

#deletes everything, remakes new empty tables
def reset_db():
    con = sqlite3.connect(DB, autocommit=True)
    cur = con.cursor()

    with open('create.sql', 'r', encoding='utf-8') as f:
        create = f.read()
    with open('drop.sql', 'r', encoding='utf-8') as f:
        drop = f.read()

    cur.executescript(drop)
    cur.execute("PRAGMA foreign_keys = ON;")
    cur.executescript(create)
    con.close()

#insert all pages from a manifest.json into db
def dump_into_db(manifest_path):
    con = sqlite3.connect(DB, autocommit=True)
    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    with open(manifest_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    #insert bundle
    bundle_id = None
    if data.get(M_PAGES):
        #.../output/bundle_id/pages/whatever_00001.png
        bundle_id = data[M_PAGES][0][M_PAGE_PATH].rsplit(DIR_OUTPUT + "/", 1)[1].split("/")[0]
        cur.execute("""INSERT OR IGNORE INTO bundles(bundle_id, source_pdf) 
            VALUES(?, ?)""", (bundle_id, data[M_INPUT]))
    else:
        print("Bundle has no pages.")
        return
    
    #insert pages
    for mkey, mval in data.items():
        if mkey == M_PAGES:
            for p in mval:
                page = None #path of page json
                img = None #path of image
                categ = None

                for key, value in p.items():
                    if key == M_PAGE_LABEL:
                        categ = value
                    elif key == M_PAGE_PATH:
                        img = value
                    elif key == M_PAGE_TRANSCRIPT and img is not None:
                        #.../output/bundle_id/pages/whatever_00001.png
                        #transcribe/whatever_00001.json
                        page = img.rsplit(DIR_PAGES + "/", 1)[0] + value
                    else:
                        pass
                    
                if page is not None and img is not None and categ is not None and bundle_id is not None:
                    insert_page(page, img, categ, "idk", bundle_id, con)
                else:
                    print("Incomplete page info cannot insert page.")
                    #print(page) right now a blank page isn't being inserted into db bc this is null
                    #print(img)
                    #print(categ)
                    #print(bundle_id)
    con.close()


#insert a single page into db
#will ignore if pageid is already in db
#if coded page, decoded values are pulled from the data_dict.json and put into database
def insert_page(page_p:str, src_img_p:str, category:str, survey_id:str, bundle_id:str, con):
    page_id = page_p.rsplit("/", 1)[1].split(".")[0]

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
        """, (page_id, src_img_p, survey_id, bundle_id, category))

    #do flags first!!

    with open(page_p, 'r', encoding='utf-8') as file:
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
#
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
             with open(CODED_DICT, 'r', encoding='utf-8') as file:
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

def main():
    print('???')
    reset_db()
    print(DIR_OUTPUT.glob)
    for file_path in DIR_OUTPUT.rglob('*manifest.json'):
        print(file_path)
        if file_path.is_file():
            print(str(file_path))
            dump_into_db(str(file_path))

main()