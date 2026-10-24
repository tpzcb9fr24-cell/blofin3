#define AppName "BloFin Live Observer"
#define AppVersion "0.3.1"
#define AppExe "BloFinObserver.exe"
[Setup]
AppId={{D8A37A12-8F25-45E9-91E4-10B3D25F2A6E}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\BloFinObserver
DefaultGroupName={#AppName}
OutputDir=..\installer-output
#ifdef UpdateOnly
OutputBaseFilename=BloFinObserver-Update
#else
OutputBaseFilename=BloFinObserver-Setup
#endif
Compression=lzma2/fast
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
[Files]
#ifdef UpdateOnly
Source: "..\dist-update\BloFinObserver\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "..\dist\BloFinObserver\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif
[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

#ifdef UpdateOnly
[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if (not FileExists(ExpandConstant('{app}\_internal\model-assets\kronos\model.safetensors'))) or
     (not FileExists(ExpandConstant('{app}\_internal\model-assets\tokenizer\model.safetensors'))) or
     (not FileExists(ExpandConstant('{app}\_internal\model-assets\timesfm\model.safetensors'))) then
    Result := 'The original BloFin Observer model files were not found. Choose the existing installation folder, or use the full BloFinObserver-Setup installer.';
end;
#endif
