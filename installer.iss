; Inno Setup 6.3+ script, compiled by build.ps1 after the PyInstaller build.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "iField Data Processing"
#define AppExe "iField Data Processing.exe"

[Setup]
; Never change AppId: it lets a new version upgrade the installed one instead of installing side by side.
AppId={{40E9C4EC-6F1D-44C5-B592-117E1D232E47}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=app\gui\app.ico
OutputDir=dist
OutputBaseFilename=iFieldDataProcessing-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Installs for the current user without admin rights; admins can choose "all users" in the dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Close a running copy before upgrading it.
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\iFieldDataProcessing\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// The application drives IBM SPSS Data Collection through COM; warn early when it is missing.
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not RegKeyExists(HKEY_CLASSES_ROOT, 'MDM.Document') or not RegKeyExists(HKEY_CLASSES_ROOT, 'DMOM.Job') then
    Result := SuppressibleMsgBox(
      'IBM SPSS Data Collection does not seem to be installed on this computer.' + #13#10#13#10 +
      'iField Data Processing needs it to read and write MDD/DDF files. ' +
      'You can install the application now and Data Collection later.' + #13#10#13#10 +
      'Continue the installation?',
      mbConfirmation, MB_YESNO, IDYES) = IDYES;
end;
