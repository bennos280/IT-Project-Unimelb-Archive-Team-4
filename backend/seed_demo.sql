-- US7 demo converted for US8. Run ONLY against a NEW empty database.
-- Preserves source page IDs and values. No saved edits are seeded.
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
BEGIN;
INSERT INTO bundles (bundle_id,source_pdf) VALUES ('216417','Demo JSON fixture; not an original PDF');
INSERT INTO surveys (survey_id,bundle_id) VALUES ('216417_1','216417');
INSERT INTO categories (category) VALUES ('coded');
INSERT INTO categories (category) VALUES ('main');
INSERT INTO categories (category) VALUES ('notes');
INSERT INTO flags (flag_type) VALUES ('uncertain');
INSERT INTO reviewers (reviewer_id,name) VALUES ('1','Demo reviewer');
INSERT INTO pages (page_id,import_path,survey_id,bundle_id,category,revision_no) VALUES ('216417/p0','/us7-demo/216417_main.jpg','216417_1','216417','main','0');
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','address','5 Raeburn Cres.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','municipality','Brunswick.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','number_of_families_in_dwelling','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','number','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','type_of_dwelling','D',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','structural_material','B.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','number_of_storeys','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','probable_age','14 yrs.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','yard_or_uncultivated_space',NULL,NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','cultivated_garden','lawn + flower beds',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','weekly_value_fruit_and_vegetables_grown','A few',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','weekly_value_fruit_and_vegetables_sold','no',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','other_commercial_activities_on_premises','[?]','uncertain');
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','date_of_interview','12/9/42.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','signature_of_investigator','P. Counihan',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','tenure','T.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','weekly_rent_or_instalments','£1.15.0.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','furnished_or_unfurnished','Unfurnished',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','length_of_residence','2 yrs.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','archive_reference','03570/3808',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','industry_of_head_code','324',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','occupation_of_head_code','2722',NULL);
INSERT INTO residents (page_id,resident_no) VALUES ('216417/p0','0');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','relationship','Head',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','age','47',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','earning_status','B.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','unearned_income_weekly_amount',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','unearned_income_source',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','industry',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','craft','Commission driver',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','regularity_of_work','Yes.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','employer','Goodman + Sons.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','employers_address','E. Brunswick.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','weekly_cost_transport','By truck (kept at home).',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','residential_preference','convenient',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','earnings_last_week','£8.0.0 (net.)',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','full_time_earnings_excluding_overtime','" av.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','weekly_contribution_to_board','£3.10.0',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','weekly_payments_to_relatives_living_elsewhere','—',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','prewar_occupation','Dairy Farmer.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','prewar_normal_weekly_earnings','£5.0.0',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','prewar_place_of_work_if_outside_melbourne','/',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','0','prewar_occupational_preference','/',NULL);
INSERT INTO residents (page_id,resident_no) VALUES ('216417/p0','1');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','relationship','wife',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','age','44',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','earning_status','H',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','unearned_income_weekly_amount',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','unearned_income_source',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','industry',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','craft',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','regularity_of_work',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','employer',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','employers_address',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','weekly_cost_transport',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','residential_preference','—',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','earnings_last_week','1 wk''s wages £4.12.0.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','full_time_earnings_excluding_overtime','wkly gives £3.10.0 M',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','weekly_contribution_to_board','1 [?] + 2 [?] = £22 (pm?)','uncertain');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','weekly_payments_to_relatives_living_elsewhere',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','prewar_occupation','Same.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','prewar_normal_weekly_earnings','/',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','prewar_place_of_work_if_outside_melbourne','/',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','1','prewar_occupational_preference','/',NULL);
INSERT INTO residents (page_id,resident_no) VALUES ('216417/p0','2');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','relationship','son',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','age','21.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','earning_status','M.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','unearned_income_weekly_amount',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','unearned_income_source',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','industry','A.M.F.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','craft','private',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','regularity_of_work',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','employer',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','employers_address','Queensland.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','weekly_cost_transport',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','residential_preference','—',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','earnings_last_week','nil',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','full_time_earnings_excluding_overtime',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','weekly_contribution_to_board',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','weekly_payments_to_relatives_living_elsewhere',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','prewar_occupation','Textile worker.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','prewar_normal_weekly_earnings','£2.10.0',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','prewar_place_of_work_if_outside_melbourne','/',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','2','prewar_occupational_preference','/',NULL);
INSERT INTO residents (page_id,resident_no) VALUES ('216417/p0','3');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','relationship','daughter',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','age','18',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','earning_status','M.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','unearned_income_weekly_amount',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','unearned_income_source',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','industry','A.W.A.S.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','craft','private',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','regularity_of_work',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','employer',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','employers_address','Toorak.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','weekly_cost_transport',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','residential_preference','→',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','earnings_last_week','[?]','uncertain');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','full_time_earnings_excluding_overtime',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','weekly_contribution_to_board',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','weekly_payments_to_relatives_living_elsewhere',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','prewar_occupation','Textile worker.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','prewar_normal_weekly_earnings','£1.15.0',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','prewar_place_of_work_if_outside_melbourne','/',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','3','prewar_occupational_preference','/',NULL);
INSERT INTO residents (page_id,resident_no) VALUES ('216417/p0','4');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','relationship','daughter son',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','age','16.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','earning_status','B.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','unearned_income_weekly_amount',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','unearned_income_source',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','industry','Textile.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','craft','Coming [?]','uncertain');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','regularity_of_work','yes.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','employer','Peebles [?]','uncertain');
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','employers_address','Brunswick mill (bike)',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','weekly_cost_transport','nil (bike)',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','residential_preference',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','earnings_last_week','£1.7.6.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','full_time_earnings_excluding_overtime','-',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','weekly_contribution_to_board','15/.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','weekly_payments_to_relatives_living_elsewhere','-',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','prewar_occupation','School.',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','prewar_normal_weekly_earnings',NULL,NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','prewar_place_of_work_if_outside_melbourne','/',NULL);
INSERT INTO resident_fields (page_id,resident_no,resident_field_title,text_raw,flag_type) VALUES ('216417/p0','4','prewar_occupational_preference',NULL,NULL);
INSERT INTO other_children (page_id,child_no,residence,text_raw,flag_type) VALUES ('216417/p0','0','died','1',NULL);
INSERT INTO other_children (page_id,child_no,residence,text_raw,flag_type) VALUES ('216417/p0','1','died','1',NULL);
INSERT INTO other_children (page_id,child_no,residence,text_raw,flag_type) VALUES ('216417/p0','2','living_elsewhere','-',NULL);
INSERT INTO other_children (page_id,child_no,residence,text_raw,flag_type) VALUES ('216417/p0','3','living_elsewhere','-',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','rooms.number_of_separate_bedrooms','3.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','rooms.number_of_living_rooms','2 (includes kitchen)',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','rooms.state_if_used_as_bedrooms',NULL,NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','rooms.rooms_not_in_daily_use','2.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','rooms.sleepouts','B yes.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','bath.location','Bathroom inside.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','bath.shared',NULL,NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','bath.hot_water_service','chip h.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','wc.internal_or_external','External',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','wc.shared','Sep.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','wash_house','Sep.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','kitchen.shared','—',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','kitchen.ever_used_as_bedroom','—',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','kitchen.meals_can_be_taken_there','Yes.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','kitchen.sink_and_water_tap','X in alcove near kitchen',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','kitchen.hot_water_service',NULL,NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','kitchen.cooking_facilities','Gas (T), fire (L).',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','kitchen.food_storage','Pantry + Cabinet + coolgardie safe.',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p0','kitchen.facilities_for_cooking_and_water_supply_in_other_rooms',NULL,NULL);
INSERT INTO pages (page_id,import_path,survey_id,bundle_id,category,revision_no) VALUES ('216417/p1','/us7-demo/216417_notes.jpg','216417_1','216417','notes','0');
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p1','text','Interviewed wife + head.
:- very friendly.
House not done up since tenants
came in:   in good order.
Some cultivation.
Block = 50'' x 130''   ( narrows slightly
                            at back).
Garage + drive.',NULL);
INSERT INTO pages (page_id,import_path,survey_id,bundle_id,category,revision_no) VALUES ('216417/p2','/us7-demo/216417_coded.jpg','216417_1','216417','coded','0');
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','municipality','02',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_of_dwelling','352',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_of_household','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','type_of_family','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','total_resident_members','2',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_under_5','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_5_to_10','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_over_10_m','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_over_10_f','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','military_service','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','boarders','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','participating_members','2',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','adult_m_breadwinners','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','adult_f_breadwinners','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','juvenile_breadwinners_under_21','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','children_under_14','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','retired_and_indep_persons','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','home_duties','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','other','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','normal_household_income','101',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','weekly_rent','20',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','total_available_income','081',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','earnings_of_head','101',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','heads_unearned_income','00',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','main_source_heads_unearned_income','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','subsidiary_source_heads_income','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','industry_of_head','4161',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','occupation_of_head','25.99',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','grade_of_occupation_of_head','2',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','place_of_work','18',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','age_of_head','45',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','sex_of_head','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','regularity_of_work','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','prewar_occupation','6',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','removal','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','type_of_dwelling','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','structural_material','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','age_of_house','10',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','garden','3',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','state_of_repair','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','tenure','3',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','length_of_residence','06',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','total_number_of_rooms','5',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_of_bedrooms','3',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_of_living_rooms','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','whether_used_as_bedrooms','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','rooms_not_in_daily_use','2',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','number_of_sleepouts','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','bathroom','4',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','wc','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','washhouse','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','kitchen','2',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','sink_and_water_service','2',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','cooking_facilities','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','food_storage','1',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','rooms_shared','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','persons_sharing','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','children_other_than_those_at_home','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','children_of_h_or_wife_living','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','children_of_h_or_wife_dead','0',NULL);
INSERT INTO fields (page_id,field_title,text_raw,flag_type) VALUES ('216417/p2','children_of_h_or_wife_total','0',NULL);
COMMIT;
