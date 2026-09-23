database file - wilfprestsurvey.db


SQLite installation is *not required* to run the following functions from loader.py:


reset_db() - deletes everything, remakes new empty tables


dump_into_db() - takes in path of manifest file, inserts all pages into db
- WIP: doesn't insert surveys (because grouping US isn't merged to main yet)
- WIP: doesn't insert flags


WIP: not joined to pipeline