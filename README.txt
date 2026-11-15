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


Deploying to Render
===================
1. Make an online MySQL database (free options: Aiven or TiDB Cloud).
   Render itself does not offer MySQL.
2. On your computer, load the tables into that online database once.
   In the VS Code terminal (PowerShell):
     $env:DB_HOST="your-host"
     $env:DB_PORT="your-port"
     $env:DB_USER="your-user"
     $env:DB_PASSWORD="your-password"
     $env:DB_NAME="your-database-name"
     python setup_db.py
3. Push this folder to GitHub (app.py must be in the repo root, or set Root Directory).
4. Render -> New -> Web Service, then:
     Build Command: pip install -r requirements.txt
     Start Command: gunicorn app:app
5. In Render -> Environment, add DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
   with the same values as step 2. Then deploy.
