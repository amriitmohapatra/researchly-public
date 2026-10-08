; Inno Setup script for the standalone Researchly Windows installer.
; Built by build_installer.bat (which prepares dist\Researchly with the
; bundled Python runtime, spaCy model, LanguageTool and private JRE).
;
; Design decisions:
; - PER-USER install ({localappdata}\Programs) — no admin prompt, which
;   the smoke checklist flags as a real-world blocker for the `keyboard`
;   library's hotkeys anyway. PrivilegesRequired=lowest keeps UAC out.
; - No autostart by default; an optional task adds a Startup shortcut.
; - Uninstaller is automatic (Inno provides it); user data in
;   %USERPROFILE%\.researchly (config, dictionary, telemetry) is
;   deliberately NOT removed on uninstall — it is the user's, and it is
;   shared with any other Researchly surface on the machine.

#define AppName "Researchly"
#define AppVersion "0.8"
#define AppPublisher "Researchly (local personal build)"
#define AppExeName "Researchly.exe"

[Setup]
AppId={{7E1C9A44-52C3-4C6E-9B1D-4F0A8E2C6D31}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=Researchly-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
; the bundle is large (spaCy model + LanguageTool + JRE)
DiskSpanning=no

[Tasks]
Name: "startup"; Description: "Start Researchly automatically when I sign in"; \
  Flags: unchecked

[Files]
Source: "dist\Researchly\*"; DestDir: "{app}"; \
  Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
  Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller leaves nothing outside {app}; user data in ~/.researchly is
; kept on purpose (shared with the Word add-in / CLI).
Type: filesandordirs; Name: "{app}"
