PRAGMA foreign_keys=1;

CREATE TABLE bundles (
    bundle_id TEXT PRIMARY KEY,
    source_pdf TEXT NOT NULL,
    import_status INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE surveys (
    survey_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL REFERENCES bundles(bundle_id) ON DELETE CASCADE
);

CREATE TABLE categories (category TEXT PRIMARY KEY);

CREATE TABLE pages (
    page_id TEXT PRIMARY KEY,
    import_path TEXT NOT NULL,
    img BLOB,
    engine TEXT,
    model TEXT,
    effort TEXT,
    runtime NUMERIC,
    revision_no INTEGER DEFAULT 0,
    survey_id TEXT REFERENCES surveys(survey_id) ON DELETE CASCADE,
    bundle_id TEXT NOT NULL REFERENCES bundles(bundle_id) ON DELETE CASCADE,
    category TEXT NOT NULL REFERENCES categories(category)
);

CREATE TABLE fields (
    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    field_title TEXT NOT NULL,
    text_raw TEXT,
    decoded_value TEXT,
    flag_type TEXT REFERENCES flags(flag_type),
    CONSTRAINT pk PRIMARY KEY (page_id, field_title)
);

CREATE TABLE annotations (
    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    annotation_no INTEGER NOT NULL,
    text_raw TEXT,
    location TEXT,
    flag_type TEXT REFERENCES flags(flag_type),
    CONSTRAINT pk PRIMARY KEY (page_id, annotation_no)
);

CREATE TABLE other_children (
    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    child_no INTEGER NOT NULL,
    residence TEXT,
    text_raw TEXT,
    flag_type TEXT REFERENCES flags(flag_type),
    CONSTRAINT pk PRIMARY KEY (page_id, child_no)
);

CREATE TABLE residents (
    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    resident_no INTEGER NOT NULL,
    CONSTRAINT pk PRIMARY KEY (page_id, resident_no)
);

CREATE TABLE resident_fields(
    page_id TEXT NOT NULL,
    resident_no INTEGER NOT NULL,
    resident_field_title TEXT NOT NULL,
    text_raw TEXT,
    flag_type TEXT REFERENCES flags(flag_type),
    CONSTRAINT pk PRIMARY KEY (page_id, resident_no, resident_field_title),
    CONSTRAINT fk 
        FOREIGN KEY (page_id, resident_no) 
        REFERENCES residents(page_id, resident_no)
        ON DELETE CASCADE
);

CREATE TABLE flags (flag_type TEXT PRIMARY KEY);

CREATE TABLE reviewers (
    reviewer_id INTEGER PRIMARY KEY,
    name TEXT
);

CREATE TABLE edits (
    edit_id INTEGER PRIMARY KEY,
    edit_text TEXT,
    reviewer_id INTEGER,
    time NUMERIC,
    page_id TEXT NOT NULL,
    field_title TEXT,
    resident_field_title TEXT,
    resident_no INTEGER,
    child_no INTEGER,
    annotation_no INTEGER,
    CONSTRAINT fk_reviewer FOREIGN KEY(reviewer_id) REFERENCES reviewers(reviewer_id),
    CONSTRAINT fk_field FOREIGN KEY (page_id, field_title) REFERENCES fields(page_id, field_title) ON DELETE CASCADE,
    CONSTRAINT fk_resident_field FOREIGN KEY (page_id, resident_field_title, resident_no) REFERENCES resident_fields(page_id, resident_field_title, resident_no) ON DELETE CASCADE,
    CONSTRAINT fk_child FOREIGN KEY (page_id, child_no) REFERENCES other_children(page_id, child_no) ON DELETE CASCADE,
    CONSTRAINT fk_annotation FOREIGN KEY (page_id, annotation_no) REFERENCES annotations(page_id, annotation_no) ON DELETE CASCADE,
--    CONSTRAINT uq_field UNIQUE (page_id, field_title),
--    CONSTRAINT uq_resident_field UNIQUE (page_id, resident_field_title, resident_no),
--    CONSTRAINT uq_child UNIQUE (page_id, annotation_no),
--    CONSTRAINT uq_annotation UNIQUE (page_id, child_no),
    CONSTRAINT exclusivity
        CHECK (
            (
                field_title IS NOT NULL 
                AND resident_field_title IS NULL AND resident_no IS NULL 
                AND child_no IS NULL 
                AND annotation_no IS NULL
            ) OR (
                field_title IS NULL 
                AND resident_field_title IS NOT NULL AND resident_no IS NOT NULL 
                AND child_no IS NULL 
                AND annotation_no IS NULL
            ) OR (
                field_title IS NULL 
                AND resident_field_title IS NULL AND resident_no IS NULL 
                AND child_no IS NOT NULL 
                AND annotation_no IS NULL
            ) OR (
                field_title IS NULL 
                AND resident_field_title IS NULL AND resident_no IS NULL 
                AND child_no IS NULL 
                AND annotation_no IS NOT NULL
            )
        )
);