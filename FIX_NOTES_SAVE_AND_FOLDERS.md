# Notes Save + Folder Fix

This build fixes the note creation/save flow while preserving the existing Note Editor design.

## Fixed
- First/new note now saves through `POST /notes`.
- Existing notes update through `PUT /notes/{id}`.
- Save errors are shown instead of pretending the note was saved locally.
- Folder dropdown uses backend folder IDs, not folder names as IDs.
- Folder name and folder ID are stored together in note content.
- `Folders -> Create Note` passes the folder ID into the Note Editor.
- Creating a folder inside Note Editor immediately selects the new folder.
- Existing folder selection is restored when editing a note.
- `?edit=<note_id>` and the existing `?id=<note_id>` edit routes are supported.
- New-note `type` and `folder` query parameters are preserved.

## Run
1. Start the backend from `backend`:
   `python -m venv venv`
   `venv\\Scripts\\Activate.ps1`
   `pip install -r requirements.txt`
   `uvicorn main:app --reload`
2. Open the frontend through a local web server rather than `file://`.
3. Log in.
4. Create a folder from **Folders**.
5. Click **Create Note** on that folder.
6. Confirm the Folder dropdown shows the folder name.
7. Enter a title/content and click **Save**.
8. Return to Notes Board and open the folder. The note should be there.
