# Web viewer and power logger

Edit on one PC, view and log from anywhere. The desktop app stays the only
editor: the web pages show the layouts (2D drawing, lab sheet) and let anyone on
the lab network log power and add beam pictures to the same power log
(`<layout>.logbook.sqlite`) the desktop app uses.

- Layout `.json` files are never written by the web server.
- Readings and pictures go through the same `Logbook` code as the desktop, so
  they are the same entries. Opening or viewing never writes to a log; a log
  that doesn't exist yet is created by the first reading.
- The desktop app picks up readings logged on the web within a few seconds,
  and the web pages pick up desktop edits and readings within a few seconds too.
- Everything lives in this `web/` folder. Delete the folder to remove it. The
  desktop app then hides its Web access menu item. Its only other link to the
  web is a small timer that refreshes the power labels when the log changes.

## Start it

**It starts with the desktop app.** When you open the app (`py -3.13 run.py ...`),
the web pages are served in the background. The right end of the menu bar shows
the address other PCs should open, e.g. `● Web: http://18.62.x.x:8000`. Click it
to open the address, or select it to copy.

The dot tells you the state:
- green: serving
- grey: off, or already served by another window or `start_web.bat`
- red: unavailable (hover over it for why)

- **Turning it off or on:** File > **Web access (share on network)**. The app
  remembers your choice next time.
- **When the app closes:** the web pages stop. They are only available while the
  desktop app is open, unless you run the server on its own (below) or start it
  at login.
- **"Web: already running at …":** another window of the app, or `start_web.bat`,
  is already serving that port. That's fine; nothing more is needed.
- **"Web: unavailable":** FastAPI or uvicorn isn't installed. Hover over it for
  the pip command. The app itself works as normal.
- **Folders listed:** exactly the folders in `web/config.json`, in that order,
  empty ones too (they say "No layouts yet").

**Running the server on its own,** without the desktop app (for example on a PC
nobody edits on):

```
py -3.13 web\server.py
```

or double-click `web\start_web.bat`. Stop it with Ctrl+C or by closing its window.

Either way, open http://localhost:8000 on that PC, or http://<that PC's address>:8000
from any other PC, tablet or phone on the network.

## Settings: `web/config.json`

Copy `web/config.example.json` to `web/config.json` and edit it. Without that file
the pages show `examples` and only this PC can reach them. To share with the lab:

```json
{
  "folders": ["../layouts"],
  "password": "pick-your-own",
  "host": "0.0.0.0",
  "port": 8000
}
```

- `folders`: the folders whose layouts are listed, in this order, relative to
  this `web` folder (an absolute path such as `"D:/Lab/layouts"` also works). Only
  `.json` files saved by the app are listed.
- `password`: the shared lab password asked once per browser. Set one before you
  use `0.0.0.0`; empty (`""`) means no password.
- `host`: `0.0.0.0` means "reachable from other PCs". Use `127.0.0.1` to allow
  this PC only.
- `port`: change this if 8000 is taken. If you change it, also change the
  firewall rule below.

You can also give another settings file: `py -3.13 web\server.py D:\somewhere\config.json`.

## Moving it to the lab desktop

1. Copy the whole project folder (`Optical Layout Designer`, with `optolayout`,
   `component_library`, `web`, and your layout folders) to the lab PC. All paths
   are relative, so it can go anywhere.
2. Install Python 3.13 from python.org (tick "Add python.exe to PATH" and keep the
   `py` launcher).
3. In a terminal in the project folder:
   ```
   py -3.13 -m pip install -r requirements.txt -r web\requirements.txt
   ```
4. Allow other PCs to reach the port. In PowerShell **run as administrator**:
   ```
   New-NetFirewallRule -DisplayName "Optical Layout web (8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Domain,Private,Public -RemoteAddress LocalSubnet
   ```
   (the same with netsh:
   `netsh advfirewall firewall add rule name="Optical Layout web (8000)" dir=in action=allow protocol=TCP localport=8000 remoteip=localsubnet`)
   `LocalSubnet` keeps it to PCs on the same lab network.
5. Find the PC's address: run `ipconfig` and read the "IPv4 Address" of the
   network adapter in use (for example `18.62.x.x` or `10.x.x.x`). The PC's
   name often works too: `http://<computer name>:8000`.
6. Open the desktop app. The web starts with it; see "Start it". Then open
   `http://<address>:8000` from another PC. If it doesn't load:
   - check the firewall rule;
   - check that both PCs are on the same network (some campus networks block
     PC-to-PC traffic; a lab or wired subnet usually doesn't).
7. Optional: if the web pages should be up even when nobody has the app open,
   start the server alone automatically when you log in. Press Win+R, type
   `shell:startup`, and put a shortcut to `web\start_web.bat` there. Or use Task
   Scheduler:
   ```
   schtasks /create /tn "Optical Layout web" /sc onlogon /tr "\"C:\path\to\Optical Layout Designer\web\start_web.bat\""
   ```

### Where the files should live

Run the web server and the desktop app on the **same PC**, on the same folder.
Both write to the power log, and SQLite handles that safely on one PC.

Other PCs should use the web pages, not the desktop app on a synced or shared
copy. Two PCs writing to one `.sqlite` file through OneDrive or a network share
can lose or conflict readings. If the folder is in OneDrive, that is fine for
backup, but log only on the lab PC (directly or through its web pages).

## Pages

- **Home**: the layouts in the configured folders.
- **Layout**: the 2D board, drawn exactly like the desktop export. Hover a power
  point for its name, last power, date and change since the previous reading;
  click it to open its log. Use the mouse wheel or pinch to zoom, drag to pan,
  Fit to reset. (3D is only in the desktop app.)
- **Point log**: latest reading, power-over-time plot, all readings, and beam
  pictures.
  - Add a reading: power, unit, meter and notes. The time is set automatically,
    the same as on the desktop.
  - Add a picture: from a file, or **Take photo** with a phone or tablet camera.
- **Lab sheet**: the desktop lab sheet with the points saved in the layout
  ticked. Print it, or **Copy for OneNote/Excel**. Choosing other points here
  doesn't change the layout file.

## Tests

```
py -3.13 tests\test_web.py
```

The tests use copies of the example layouts; they never touch your logs.
