
Export/update templates from a database
-----------------------------------------

Using the BQI tool, you can export some/all modules translations. It can
even locate the original source folders and put them there, which is very
convenient if you want to push them back through git.

There are some thins to know, however:
  1. you are advised NOT to export languages, but only the templates.
    Reason is, language catalogs also contain translator's comments, fuzzy
    strings and *copyright* statements, which need to be preserved.
  2. you shall only export from a *clean* database. A production one may
    have extra strings or modifications you wouldn't want to end up in those
    source files.
  3. a loaded database may not have all modules, which is just a minor issue

The command, for all modules, is:

    BQI> translation export --sourcedirs --all


Create a translation folder
-----------------------------

Some translation programs may not recognize the "addons/<module>/i18n/<lang>.po"
pattern as a selector for files to translate.
Instead, we have the more common one:
    project_path/<lang>/<module>.po

Which means, we have to move our files...
... or, just symlink them to such a virtual structure.

The script that does that is:
   f3-build_transdir.sh

Note, that any translation programs that actually move the .po files to take
a backup will spoil the party.


Update translations from templates
-----------------------------------

You are advised NOT to export languages directly from db, but only export
the templates and then sync language catalogs with them.

Command is (eg. for "el" language):
    f3-update_translations.sh -l el -C


