========================================
  DOCUMENT ROUTER - CONFIGURATION GUIDE
========================================

This folder contains all the settings for how documents
are classified and routed. You can edit these files
with any text editor (Notepad, VS Code, etc).

Restart the server after making changes.


FOLDER STRUCTURE
----------------

config/
├── routes.txt              --> Which pipeline each document type uses
├── prompt.txt              --> The instruction sent to the AI for classification
│
├── filename_hints/         --> Keywords to look for in file names
│   ├── LOSS_RUN.txt
│   ├── ACORD.txt
│   ├── POLICY.txt
│   ├── SOI.txt
│   ├── SOV.txt
│   ├── BINDER.txt
│   └── QUOTE.txt
│
└── keyword_hints/          --> Phrases to look for inside the document text
    ├── LOSS_RUN.txt
    ├── ACORD.txt
    ├── POLICY.txt
    ├── SOI.txt
    ├── SOV.txt
    ├── BINDER.txt
    └── QUOTE.txt


HOW TO EDIT
-----------

1. To CHANGE KEYWORDS:
   Open any .txt file in filename_hints/ or keyword_hints/
   Add or remove keywords — one per line.
   Lines starting with # are ignored (comments).

2. To CHANGE WHICH PIPELINE a document type uses:
   Open routes.txt
   Change OCR or LLM next to the document type.

3. To ADD A NEW DOCUMENT TYPE:
   - Add a new line in routes.txt (e.g. ENDORSEMENT = LLM)
   - Create filename_hints/ENDORSEMENT.txt with filename keywords
   - Create keyword_hints/ENDORSEMENT.txt with text keywords

4. To REMOVE A DOCUMENT TYPE:
   - Delete the line from routes.txt
   - Delete the corresponding .txt files from filename_hints/ and keyword_hints/

5. To CHANGE THE AI PROMPT:
   Open prompt.txt and edit the text.
