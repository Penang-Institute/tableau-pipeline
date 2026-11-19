# Fixing the Tableau "Could not start Hyper" Error (Error Code: AC0843EA)

**Who this is for:** Anyone opening the Penang Institute Tableau workbooks on a
Windows laptop and hitting the **"Bad Connection / Could not start Hyper"** error.

**Time to fix:** About 2 minutes. No admin rights needed. No files to copy.

---

## 1. What the error looks like

When you open a workbook you get a pop-up:

> **Unable to complete action**
> Bad Connection: Tableau could not connect to the data source.
> **Error Code: AC0843EA**
> Could not start Hyper: Failed to start a new Hyper instance…

It looks like a data problem, but it is **not**. The workbook and the data are fine.

---

## 2. Why it happens (the simple version)

Tableau has a built-in engine called **Hyper** that loads the data behind every
chart. Hyper needs a folder on your computer to do its work in — this folder is
called the **Tableau Repository**.

On the affected laptop, the Tableau Repository was set to a **Google Drive folder**:

```
G:\Shared drives\Tableau\My Tableau Repository
```

Google Drive is a **cloud / online drive**, not a real folder on the laptop.
Hyper cannot run from an online drive — it needs a **real local folder on the
C: drive**. Because it could not write its files to the Google Drive location,
Hyper failed to start, and Tableau showed the error.

> **In one line:** Tableau was trying to run its engine from Google Drive. It must
> run from the local **C:** drive instead.

---

## 3. The fix (do this once)

You are **not** moving or copying any files. You are just telling Tableau to use a
local folder. Tableau will create a fresh folder there automatically.

### Step 1 — Close Tableau completely
Save your work, then close **all** Tableau Desktop windows. (If unsure, restart
the laptop to be safe.)

### Step 2 — Re-open Tableau, then open the menu
At the very top of Tableau, click:

```
Help  →  Settings and Performance  →  Manage Repository Location…
```

*(On some versions this is **File → Repository Location** or
**Choose Repository Location…** — it's the same thing.)*

### Step 3 — Choose a local folder
A "browse for folder" window opens.

- If you see a **"Restore Default"** button → click it. ✅ (Easiest option.)
- Otherwise, browse to:
  ```
  C:\Users\<your-windows-username>\Documents
  ```
  …select the **Documents** folder, and click **OK**.
  (Tableau will add "My Tableau Repository" inside it for you.)

> ✅ **Correct location:** `C:\Users\<your-name>\Documents\My Tableau Repository`
> ❌ **Never use:** anything starting with `G:\Shared drives\...` (Google Drive),
> OneDrive, Dropbox, or a network drive `\\...`

### Step 4 — Restart Tableau
Close Tableau one more time and open it again. Now open your workbook — it should
load with no error.

---

## 4. Important: where files should live

After the fix, keep these two things separate:

| Thing | Where it should live | Notes |
|-------|----------------------|-------|
| **Tableau Repository** (the engine's work folder) | **Local C: drive** | Set once in Step 3. Tableau creates it for you — nothing to copy. |
| **The workbook** (`.twbx` file) | **Google Drive is fine** | You can still open it directly from `G:\Shared drives\...`. Sharing via Google Drive is OK. |

> 👉 You may **open the workbook from Google Drive**. Only the **Repository** must
> be on the C: drive. Once Step 3 is done, opening from Google Drive works fine.

---

## 5. Quick checklist

- [ ] Closed Tableau completely
- [ ] Help → Settings and Performance → Manage Repository Location
- [ ] Set location to **C:\Users\\<your-name>\Documents** (or clicked "Restore Default")
- [ ] **NOT** a Google Drive `G:\` / OneDrive / network path
- [ ] Restarted Tableau
- [ ] Opened the workbook — no error 🎉

---

## 6. If it still doesn't work

1. Make sure the location you picked is on **C:** and is **not** inside any
   Google Drive / OneDrive / Dropbox folder.
2. Open **Task Manager** (Ctrl+Shift+Esc), look for **`hyperd.exe`**, and end it
   if it's still running, then re-open Tableau.
3. If the error persists, take a screenshot of the error and send it to Subash.

---

## 7. Frequently asked

**Q: Do I need to copy the "My Tableau Repository" folder from Google Drive to my laptop?**
No. Tableau creates a brand-new empty Repository on the C: drive by itself when
you set the location. There is nothing to copy.

**Q: Will I lose my dashboard or data?**
No. Your dashboard and data are inside the **workbook file (`.twbx`)**, which is
separate from the Repository and is not touched by this fix.

**Q: Can I still share the workbook on Google Drive?**
Yes. Sharing the `.twbx` file on Google Drive is fine. Just don't set the
*Repository* to a Google Drive folder.

---

*Penang Institute · tableau-pipeline · prepared by Subashanan Nair*
