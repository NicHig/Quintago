# PuzzleFile v1 Schema (normative)

```json
{
  "schema_version": "puzzlefile.v1",
  "meta": {
    "id": "0001",
    "title": "My Puzzle",
    "subtitle": "Optional",
    "author": "You",
    "date": "YYYY-MM-DD",
    "difficulty": "Optional",
    "subtitle": "Optional",
    "instructions": "Optional markdown string shown in the app",
    "givens": [
      {"cell": "1,1", "letter": "A"}
    ]
  },
  "entries": {
    "h1": { "clue": "string", "initial": "(admin-only)", "answer": "APPLE" },
    "h2": { "clue": "string", "initial": "(admin-only)", "answer": "BERRY" },
    "v1": { "clue": "string", "initial": "(admin-only)", "answer": "ALPHA" },
    "v2": { "clue": "string", "initial": "(admin-only)", "answer": "ELDER" },
    "hw": { "clue": "string", "initial": "(admin-only)",  "answer": "PLDY" }
  }
}