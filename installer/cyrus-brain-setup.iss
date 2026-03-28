; Cyrus Brain — Inno Setup Script
; Builds a single setup.exe that installs Brain + Hook + Service + Companion Extension

#define MyAppName "Cyrus Brain"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.3"
#endif
#define MyAppPublisher "Dyad Apps"
#define MyAppURL "https://github.com/Dyad-Apps/cyrus"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={userappdata}\.cyrus\brain
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=cyrus-brain-setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=lowest
SetupIconFile=compiler:SetupClassicIcon.ico
UninstallDisplayIcon={app}\cyrus-brain.ico
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Brain core files
Source: "..\cyrus_brain.py";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\cyrus_hook.py";           DestDir: "{app}"; Flags: ignoreversion
Source: "..\cyrus_brain_service.py";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-brain.txt";  DestDir: "{app}"; Flags: ignoreversion

; Post-install script
Source: "post-install.ps1";           DestDir: "{app}"; Flags: ignoreversion

; Companion extension
Source: "..\cyrus-companion\*.vsix";  DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Run]
; Post-install: create venv, install deps, configure hooks, register service, install extension
Filename: "powershell.exe"; \
  Parameters: "-ExecutionPolicy Bypass -File ""{app}\post-install.ps1"" -InstallDir ""{app}"""; \
  StatusMsg: "Setting up Python environment and registering service..."; \
  Flags: runhidden waituntilterminated

[UninstallRun]
; Stop and remove Windows service before uninstall
Filename: "powershell.exe"; \
  Parameters: "-ExecutionPolicy Bypass -Command ""& '{app}\venv\Scripts\python.exe' '{app}\cyrus_brain_service.py' remove 2>&1 | Out-Null"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "RemoveCyrusTask"

[Dirs]
Name: "{app}\venv"; Flags: uninsalwaysuninstall

[Icons]
Name: "{group}\Start Cyrus Brain"; Filename: "{app}\start-brain.bat"
Name: "{group}\Uninstall Cyrus Brain"; Filename: "{uninstallexe}"
