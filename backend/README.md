## Files
| | |
|---|---|
db/wilfprestsurvey.db|the database
db/create.sql|Contains sql commands to create all db tables
db/drop.sql|Contains sql commands to drop all db tables
db/loader.py|Imports transcribed data in output folder into database. If there is no database file it will create one automatically. (currently every time you run this file it will reset db to match only what is in output folder.)
api/main.py|Contains backend api functions to store/retrieve data from db 
db/database.py| db connection and engine setup
db/models.py| sqlalchemy classes to correspond to db tables
api/sections.py|stores dictionaries, used in api/main.py


## Schemas
### Database schema
Follows the schema in this diagram
https://drive.google.com/file/d/1lI1dQj07qq2964taoN52lEnq9KpuVIVU/view?usp=sharing

NOTES:
- A child in other_children is identified by (page_no, child_no). child_no doesn't correspond to column that the child is in, it is just an identifier, so child_no is different for each field on a given page.

### API (api/main.py)
get_survey return value eg.
```
{
  "id": "216417",
  "title": "Wilfred Prest Survey",
  "pages": [
    {
      "id": "216412_00004",
      "type": "main",
      "imageUrl": "/us7-demo/216417_main.jpg",
      "fields": [
        {
          "id": "address",
          "label": "Address",
          "group": "Address",
          "value": "5 Raeburn Cres."
        },
        {
          "id": "residents.0.relationship",
          "label": "Relationship",
          "group": "Residents 0",
          "value": "Head"
        },
      ]
    }
  ]
}
```

get_reviewers return value eg.
```
[
    {
        "reviewer_id": "123",
        "name": "L"
    },
]
```


## Import data into database
From root:
```bash
uv run --env-file .env backend/db/loader.py
```

## Run backend server
Run server from root directory:
```bash
uv run uvicorn backend.api.main:app --reload
```

## Acknowledgments
sections of api/main.py, db/models.py, db/database.py, test_backend_api.py created with use of generative AI