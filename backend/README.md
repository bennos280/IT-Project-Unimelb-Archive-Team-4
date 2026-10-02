## Files
| | |
|---|---|
wilfprestsurvey.db|the database
create.sql|contains sql commands to create all db tables
drop.sql|contains sql commands to drop all db tables
loader.py|wip
main.py|contains backend api functions to store/retrieve data from db 
database.py| db connection and engine setup
models.py| sqlalchemy classes to correspond to db tables
UI_groupings.py|stores dictionaries, used in main.py


## Schemas
### Database schema
Follows the schema in this diagram
https://drive.google.com/file/d/1lI1dQj07qq2964taoN52lEnq9KpuVIVU/view?usp=sharing

### API (main.py)
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
```bash
wip
```

## Run backend server
Run server from root directory:
```bash
uv run uvicorn backend.main:app --reload
```

## Acknowledgments
sections of main.py, models.py, database.py, test_backend_api.py created with use of generative AI