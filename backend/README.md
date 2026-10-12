## Files

|                    |                                                                                                                                                                                                                           |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| wilfprestsurvey.db | the database                                                                                                                                                                                                              |
| create.sql         | Contains sql commands to create all db tables                                                                                                                                                                             |
| drop.sql           | Contains sql commands to drop all db tables                                                                                                                                                                               |
| loader.py          | Imports transcribed data in output folder into database. If there is no database file it will create one automatically. (currently every time you run this file it will reset db to match only what is in output folder.) |
| main.py            | Contains backend api functions to store/retrieve data from db                                                                                                                                                             |
| database.py        | db connection and engine setup                                                                                                                                                                                            |
| models.py          | sqlalchemy classes to correspond to db tables                                                                                                                                                                             |
| UI_groupings.py    | stores dictionaries, used in main.py                                                                                                                                                                                      |

## Schemas

### Database schema

Follows the schema in this diagram
https://drive.google.com/file/d/1lI1dQj07qq2964taoN52lEnq9KpuVIVU/view?usp=sharing

NOTES:

- A child in other_children is identified by (page_no, child_no). child_no doesn't correspond to column that the child is in, it is just an identifier, so child_no is different for each field on a given page.

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

From root:

```bash
uv run --env-file .env backend/loader.py
```

## Run backend server

Run server from root directory:

```bash
uv run uvicorn backend.main:app --reload
```

## Acknowledgments

sections of main.py, models.py, database.py, test_backend_api.py created with use of generative AI

## US7 database connection

This branch runs against `backend/us7-demo.sqlite`, configured in `database.py`.
The imported `wilfprestsurvey.db` is not selected automatically.
