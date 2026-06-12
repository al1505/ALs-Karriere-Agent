# SETUP-TODO — Manuelle Schritte für Alois

Einmalige Konfigurationsschritte, die nicht automatisiert werden können
(erfordern physischen Zugang / Admin-Rechte am Office-Server).

---

## 1. PDF-Worker am Office-Server (192.168.15.10) — PFLICHT für B3

**Ziel:** Word-COM-basierte DOCX → PDF Konvertierung ohne LibreOffice.
Der NUC legt Job-Dateien ab, der Office-Server konvertiert lokal (kein SMB-Hop,
Karriere-Share liegt physisch am Server).

### Schritt 1: PowerShell-Script anlegen

Pfad: `D:\ALs\Karriere-PDF-Worker\pdf_worker.ps1`

```powershell
# pdf_worker.ps1 — Karriere PDF-Worker (Job-Queue)
# Läuft alle 60s via Scheduled Task oder als kontinuierlicher Loop

param([string]$BewerbungenBase = "D:\ALs\Karriere\CV\Bewerbungen")

$ErrorActionPreference = "Stop"

function Convert-DocxToPdf {
    param([string]$DocxPath, [string]$OutputDir)

    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0

    try {
        $doc = $word.Documents.Open($DocxPath, $false, $true)
        $pdfPath = Join-Path $OutputDir ([System.IO.Path]::GetFileNameWithoutExtension($DocxPath) + ".pdf")
        # wdFormatPDF = 17
        $doc.SaveAs([ref]$pdfPath, [ref]17)
        $doc.Close($false)
        return $pdfPath
    } finally {
        $word.Quit()
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
    }
}

# Scan for job files
$jobs = Get-ChildItem -Path $BewerbungenBase -Recurse -Filter "*.job.json" -ErrorAction SilentlyContinue

foreach ($jobFile in $jobs) {
    $jobDir = $jobFile.DirectoryName
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($jobFile.Name) -replace '\.job$', ''
    $doneFile = Join-Path $jobDir "$stem.done.json"
    $errFile  = Join-Path $jobDir "$stem.error.json"

    # Skip already processed
    if ((Test-Path $doneFile) -or (Test-Path $errFile)) { continue }

    try {
        $job = Get-Content $jobFile.FullName | ConvertFrom-Json
        $docxPath = $job.docx_path
        $outputDir = Split-Path $docxPath -Parent

        if (-not (Test-Path $docxPath)) {
            throw "DOCX not found: $docxPath"
        }

        # Mark as converting
        $job.status = "converting"
        $job | ConvertTo-Json | Set-Content $jobFile.FullName -Encoding UTF8

        $pdfPath = Convert-DocxToPdf -DocxPath $docxPath -OutputDir $outputDir

        # Write done marker
        @{ job_id = $job.job_id; pdf_path = $pdfPath; done_at = (Get-Date -Format "o") } |
            ConvertTo-Json | Set-Content $doneFile -Encoding UTF8

        # Remove job file
        Remove-Item $jobFile.FullName -Force

        Write-Host "Converted: $docxPath -> $pdfPath"

    } catch {
        @{ job_id = ($job.job_id ?? "unknown"); error = $_.Exception.Message; failed_at = (Get-Date -Format "o") } |
            ConvertTo-Json | Set-Content $errFile -Encoding UTF8
        Write-Host "ERROR: $_"
    }
}
```

### Schritt 2: Scheduled Task anlegen

1. **Task-Scheduler öffnen** (`taskschd.msc`)
2. **Neue Task erstellen** → "Unabhängig von Benutzeranmeldung ausführen"
3. **Einstellungen:**
   - Name: `Karriere PDF-Worker`
   - Benutzer: `SYSTEM` oder dein lokales Admin-Konto
   - Trigger: Alle 60 Sekunden (`Repeat: every 1 minute, indefinitely`)
   - Aktion: `powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "D:\ALs\Karriere-PDF-Worker\pdf_worker.ps1"`
   - Häkchen: „Mit höchsten Privilegien ausführen"

4. **Test:**
   ```
   # Manuell testen (PowerShell als Admin):
   & "D:\ALs\Karriere-PDF-Worker\pdf_worker.ps1" -BewerbungenBase "D:\ALs\Karriere\CV\Bewerbungen"
   ```

### Schritt 3: DCOM-Identity (falls Word non-interactiv nicht startet)

Wenn Word.Application im Task-Scheduler hängt:

1. `dcomcnfg.exe` → Component Services → Computer → My Computer → DCOM Config
2. **Microsoft Word**: Properties → Identity → "This user" → dein lokales Konto + Passwort
3. Reboot nicht nötig, aber Word schließen vor dem Test

### Pfad-Mapping NUC ↔ Office-Server

| NUC-Pfad | Office-Server-Pfad |
|---|---|
| `/home/al/CV/Bewerbungen/…` | `D:\ALs\Karriere\CV\Bewerbungen\…` |

Der NUC schreibt `.pdf-jobs/job.json` via CIFS in den BW-Ordner.
Der Office-Server liest dieselbe Datei lokal unter `D:\ALs\Karriere\CV\Bewerbungen\…`.

> **Hinweis:** Der Bewerbungs-Share muss unter beiden Pfaden das selbe Verzeichnis sein.
> Derzeit: CIFS-Mount am NUC unter `/home/al/CV/Bewerbungen` → `\\192.168.15.10\Karriere\CV\Bewerbungen`
> Am Office-Server physisch: `D:\ALs\Karriere\CV\Bewerbungen`

---

## 2. Port-Dokumentation

Port 7601 in interne Port-Listen eintragen (`Karriere-Agent`).

---

## 3. Word-COM AutoLogon-Test

```powershell
# Am Office-Server testen (als SYSTEM via PSExec oder Scheduled Task):
$w = New-Object -ComObject Word.Application
$w.Quit()
Write-Host "Word COM OK"
```

Falls Fehler: DCOM-Identity laut Schritt 1.3 konfigurieren.

---

*Erstellt: 2026-06-12 | Projekt: ALs-Karriere-Agent v6*
