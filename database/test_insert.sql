INSERT INTO bundles (bundle_id, source_pdf) VALUES('testid', 'testsource');
INSERT INTO surveys (bundle_id) VALUES('testid');
INSERT INTO models VALUES('testmodel');
INSERT INTO categories VALUES('main');
INSERT INTO pages (page_id, import_path, survey_id, bundle_id, category, model) 
    VALUES('testpage', 'path', 1, 'testid', 'main', 'testmodel');
INSERT INTO fields (page_id, field_title) VALUES('testpage', 'testfield');