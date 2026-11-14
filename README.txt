VoiceRoute web version
======================

Folder layout:
  voiceroute_web/
    app.py            <- Flask server (run this)
    setup_db.py       <- your database setup file (unchanged)
    requirements.txt
    templates/
      index.html      <- the web page (must stay inside the templates folder)

How to run (VS Code terminal):
  1. Start MySQL in XAMPP.
  2. pip install -r requirements.txt
  3. python setup_db.py          (only the first time, or to reset the data)
  4. python app.py
  5. Open http://127.0.0.1:5000 in Google Chrome and allow the microphone.

Notes:
  - Voice needs Chrome or Edge and an internet connection (browser speech recognition).
  - In other browsers you can still type the commands.
