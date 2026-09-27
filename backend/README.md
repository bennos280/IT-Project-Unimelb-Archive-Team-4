## Files
| | |
|---|---|
wilfprestsurvey.db|the database
create.sql|contains sql commands to create all db tables
drop.sql|contains sql commands to drop all db tables
loader.py|
models.py|
main.py|

## Database schema
Follows the schema in this diagram
https://drive.google.com/file/d/1lI1dQj07qq2964taoN52lEnq9KpuVIVU/view?usp=sharing

## Import data into database

SQLite installation is *not required* to run functions from loader.py as it is installed if python is installed.

WIP: not joined to pipeline

Call the functions from loader.py:


`reset_db()` - deletes everything, remakes new empty tables


`dump_into_db()` - takes in path of manifest file, inserts all pages into db
- WIP: doesn't insert surveys (because grouping US isn't merged to main yet)
- WIP: doesn't insert flags


## Run backend server
Install libraries:
`pip install fastapi uvicorn sqlalchemy pydantic`
Run server:
`uvicorn main:app --reload`

## Acknowledgments
main.py, models.py, database.py created with use of generative AI