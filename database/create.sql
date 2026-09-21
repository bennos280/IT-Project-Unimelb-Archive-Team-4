PRAGMA foreign_keys=1;

CREATE TABLE bundles (
    bundle_id TEXT PRIMARY KEY,
    source_pdf TEXT NOT NULL,
    import_status INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE surveys (
    survey_id INTEGER PRIMARY KEY,
    bundle_id TEXT NOT NULL REFERENCES bundles(bundle_id)
);

CREATE TABLE categories (category TEXT PRIMARY KEY);

CREATE TABLE models (model TEXT PRIMARY KEY);

CREATE TABLE pages (
    page_id TEXT PRIMARY KEY,
    import_path TEXT NOT NULL,
    img BLOB,
    survey_id INTEGER REFERENCES surveys(survey_id),
    bundle_id TEXT NOT NULL REFERENCES bundles(bundle_id),
    category TEXT NOT NULL REFERENCES categories(category),
    model TEXT NOT NULL REFERENCES models(model)
);

CREATE TABLE fields (
    page_id TEXT NOT NULL REFERENCES pages(page_id),
    field_title TEXT NOT NULL,
    text_raw TEXT,
    coded_value TEXT,
    flag_type TEXT REFERENCES flags(flag_type),
    CONSTRAINT pk PRIMARY KEY (page_id, field_title)
);

CREATE TABLE annotations (
    page_id TEXT NOT NULL REFERENCES pages(page_id),
    annotation_no INTEGER NOT NULL,
    text_raw TEXT,
    location TEXT,
    flag_type TEXT REFERENCES flags(flag_type),
    CONSTRAINT pk PRIMARY KEY (page_id, annotation_no)
);

CREATE TABLE other_children (
    page_id TEXT NOT NULL REFERENCES pages(page_id),
    child_no INTEGER NOT NULL,
    residence TEXT CHECK (residence in ('died', 'living_elsewhere')),
    text_raw TEXT,
    flag_type TEXT REFERENCES flags(flag_type),
    CONSTRAINT pk PRIMARY KEY (page_id, child_no)
);

CREATE TABLE residents (
    page_id TEXT NOT NULL REFERENCES pages(page_id),
    resident_no INTEGER NOT NULL,
    CONSTRAINT pk PRIMARY KEY (page_id, resident_no)
);

CREATE TABLE resident_fields(
    page_id TEXT NOT NULL REFERENCES pages(page_id),
    resident_no TEXT NOT NULL REFERENCES residents(resident_no),
    resident_field_title TEXT NOT NULL,
    text_raw TEXT,
    flag_type TEXT REFERENCES flags(flag_type),
    CONSTRAINT pk PRIMARY KEY (page_id, resident_no, resident_field_title)
);

CREATE TABLE flags (flag_type TEXT PRIMARY KEY);

CREATE TABLE edits (
    edit_id INTEGER PRIMARY KEY,
    edit_text TEXT,
    user TEXT,
    time NUMERIC,
    page_id TEXT NOT NULL,
    field_title TEXT,
    resident_field_title TEXT,
    resident_no INTEGER,
    child_no INTEGER,
    annotation_no INTEGER,
    CONSTRAINT pk 
        UNIQUE (page_id, field_title)
        UNIQUE (page_id, resident_field_title, resident_no)
        UNIQUE (page_id, child_no)
        UNIQUE (page_id, annotation_no)
        CHECK ((field_title IS NOT NULL) OR 
            ((resident_field_title IS NOT NULL) AND (resident_no IS NOT NULL)) OR
            (child_no IS NOT NULL) OR
            (annotation_no IS NOT NULL))
);