; Inno Setup script for Cadence.
;
; Produces a normal Windows installer: per-user by default so it needs no admin
; prompt, a Start Menu entry, an uninstaller registered in Add/Remove Programs, and
; an optional desktop shortcut. Compile with:
;
;     iscc packaging\cadence.iss /DAppVersion=0.3.0 /DArch=x64
;
; build.py passes those defines, so there is only one place the version lives.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Arch
  #define Arch "x64"
#endif

#define AppName       "Cadence"
#define AppPublisher  "KayTwoOne"
#define AppURL        "https://github.com/KayTwoOne/Cadence"
#define AppExe        "Cadence.exe"

[Setup]
AppId={{9E2C4B71-5B7A-4E0B-9E3E-4A2C0E4D1C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}

; Per-user install: no UAC prompt, and the updater can replace files without
; elevation. Someone who wants it for every account can pick that at runtime.
PrivilegesRequiredOverridesAllowed=dialog commandline
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

OutputDir=..\dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}-{#Arch}
SetupIconFile=..\cadence.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
LicenseFile=..\LICENSE

#if Arch == "x64"
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#elif Arch == "arm64"
ArchitecturesAllowed=arm64
ArchitecturesInstallIn64BitMode=arm64
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
  GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";      DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\LICENSE";        DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";            Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";      Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings live beside the exe; leaving them behind after an uninstall is litter.
Type: filesandordirs; Name: "{localappdata}\Cadence"
