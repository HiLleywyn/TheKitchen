# Design notes

## The constraint that shaped everything

The product brief had one non-negotiable: never present estimated ABV or
inferred batch state as a measurement. That is not a UI problem, and it is not
solvable by careful wording in a prompt. A language model asked to "report the
ABV" will happily produce a number with no memory of where it came from. So the
distinction lives in the data model, and the model is only ever handed values
that already know what they are.

`provenance.Value` is frozen, requires a `method` for anything claiming to be
measured or calculated, and its `recast` method only permits weakening a claim.
There is no code path that turns an estimate into a measurement. Tests assert
that, including one that tries to do it.

## Stack

Python 3.11, FastAPI, SQLite, vanilla JS. Chosen for the boring reasons:

- **SQLite** because this is one person's brewing log. A single file is easier to
  back up, inspect and move than a database server, and it is genuinely durable.
- **FastAPI** because the eventual assistant needs a tool-calling surface, and
  typed request models plus auto-generated OpenAPI make that surface explicit.
- **No build step** because a hobby project that needs `npm install` before you
  can log a gravity reading will not get used at 11pm on brew day.
- **No ORM** because the schema is nine tables and the queries are legible.

Rejected alternatives: a full Django app (too much ceremony for one user), a
Notion/Airtable base (no control over provenance), and a pure LLM-with-memory
design (fabricates numbers, which is the exact failure mode we are avoiding).

## Append-only readings

`readings` has triggers that abort `UPDATE` and `DELETE`. A wrong reading is
corrected by adding another one with `supersedes_id` set. This is the same
reasoning as double-entry bookkeeping: the history of what you believed is
worth more than a tidy table.

## Inference is labelled as inference

`batch_summary` returns a status with a `kind` and a plain-language `reason`.
"Stable, likely ready to package" is `inferred`, and the reason says why: the
last two gravities agree within 0.001 and the newest is at least three days old.
A status the brewer typed is `user_supplied`, which outranks inference.

The summary also refuses to invent things. One gravity reading produces no ABV,
just a caveat saying ABV needs two. A first reading taken long after the batch
started gets a caveat noting it may not be the true original gravity.

## The assistant layer

`tools.py` is the entire surface an LLM would get: nine deterministic functions,
each returning a provenance-tagged result. No model is wired in yet, on purpose.
The tool contract is the part that has to be right, and it is testable without
a model or an API key. When a model is added, it chooses tools and narrates
results; it does not do arithmetic and it does not decide what counts as a
measurement.

## Not built, and why

- **Auth and multi-user.** One user. Adding accounts now would mean designing
  permissions before knowing whether the friend wants sharing at all.
- **Water chemistry and carbonation.** Real brewing features, but they need
  reference data with sources, which is the next chunk of work rather than a
  quick addition.
- **Sync.** A single SQLite file on one machine is the correct answer until it
  demonstrably is not.
