; UCAD Assistant Installer — Inno Setup
; Build: iscc setup.iss

#define MyAppName "UCAD Assistant"
#define MyAppVersion "1.0.2"
#define MyAppPublisher "USAYEED LLC"
#define MyAppURL "https://github.com/AbdullahUsayeed/UCAD"
#define MyAppExeName "UCAD Launcher.exe"

[Setup]
AppId={{B4F7C3A1-2E8D-4F6A-9B0C-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={localappdata}\UCAD Assistant
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=UCAD_Assistant_{#MyAppVersion}_Setup
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableDirPage=no
UninstallDisplayIcon={app}\Launcher\{#MyAppExeName}
SetupIconFile=..\Resources\icons\ai_companion.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Full installation"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "launcher"; Description: "UCAD Launcher (required)"; Types: full custom; Flags: fixed
Name: "plugin"; Description: "AICompanion FreeCAD Mod"; Types: full custom; Flags: fixed
Name: "shortcut_desktop"; Description: "Desktop shortcut"; Types: full custom
Name: "shortcut_startmenu"; Description: "Start Menu folder"; Types: full custom
Name: "freecad_download"; Description: "Download FreeCAD (if not installed)"; Types: full

[Files]
; Launcher
Source: "..\dist\UCAD Launcher\*"; DestDir: "{app}\Launcher"; Flags: recursesubdirs createallsubdirs; Components: launcher
; Plugin (Mod) — will be referenced by -M flag, not copied into FreeCAD
; Uses pre-obfuscated source (run scripts\protect_source.py first)
Source: "..\build\protected_mod\*"; DestDir: "{app}\Runtime\AICompanion"; Flags: recursesubdirs createallsubdirs; Components: plugin
; Config defaults
Source: "..\installer\default_config.json"; DestDir: "{app}\Config"; Flags: onlyifdoesntexist

[Icons]
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\Launcher\{#MyAppExeName}"; WorkingDir: "{app}"; Components: shortcut_desktop
Name: "{group}\{#MyAppName}"; Filename: "{app}\Launcher\{#MyAppExeName}"; WorkingDir: "{app}"; Components: shortcut_startmenu
Name: "{group}\Diagnostics"; Filename: "{app}\Launcher\{#MyAppExeName}"; Parameters: "--diagnostics"; WorkingDir: "{app}"; Components: shortcut_startmenu
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Components: shortcut_startmenu

[Run]
; Create runtime data directory structure
Filename: "{cmd}"; Parameters: "/c mkdir ""{app}\RuntimeData"" 2>nul & mkdir ""{app}\Logs"" 2>nul & mkdir ""{app}\Cache"" 2>nul & mkdir ""{app}\Secrets"" 2>nul"; Flags: runhidden
; Launch UCAD Launcher after install
Filename: "{app}\Launcher\{#MyAppExeName}"; Description: "Launch UCAD Assistant"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Clean up user data (optional, asked during uninstall)
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{app}\RuntimeData"" 2>nul"; Flags: runhidden
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{app}\Logs"" 2>nul"; Flags: runhidden

[Code]
// ── FreeCAD Detection ──────────────────────────────────────
var
  FreeCADNeedsDownload: Boolean;
  DownloadPage: TDownloadWizardPage;
  FreeCADPath: string;

#define FreeCADMinVer         "1.1.0"
#define FreeCADDownloadVer    "1.1.1"
#define FreeCADDownloadFile   "FreeCAD_1.1.1-Windows-x86_64-py311.7z"
#define FreeCADDownloadUrl    "https://github.com/FreeCAD/FreeCAD/releases/download/1.1.1/FreeCAD_1.1.1-Windows-x86_64-py311.7z"

function FindFreeCADInRegistry: string;
var
  InstallPath: string;
begin
  Result := '';
  if RegQueryStringValue(HKLM, 'SOFTWARE\FreeCAD', 'InstallPath', InstallPath) or
     RegQueryStringValue(HKCU, 'SOFTWARE\FreeCAD', 'InstallPath', InstallPath) then
  begin
    if FileExists(InstallPath + '\bin\FreeCAD.exe') then
      Result := InstallPath + '\bin\FreeCAD.exe';
  end;
end;

function FindFreeCADInProgramFiles: string;
var
  FindRec: TFindRec;
begin
  Result := '';
  if FindFirst(ExpandConstant('{pf}\FreeCAD *\bin\FreeCAD.exe'), FindRec) then
  begin
    Result := ExpandConstant('{pf}') + '\FreeCAD ' + FindRec.Name + '\bin\FreeCAD.exe';
    FindClose(FindRec);
  end;
end;

function FindFreeCADInLocalAppData: string;
var
  FindRec: TFindRec;
begin
  Result := '';
  if FindFirst(ExpandConstant('{localappdata}\Programs\FreeCAD *\bin\FreeCAD.exe'), FindRec) then
  begin
    Result := ExpandConstant('{localappdata}\Programs\FreeCAD ') + FindRec.Name + '\bin\FreeCAD.exe';
    FindClose(FindRec);
  end;
end;

function FindFreeCAD: string;
begin
  Result := FindFreeCADInRegistry;
  if Result = '' then
    Result := FindFreeCADInProgramFiles;
  if Result = '' then
    Result := FindFreeCADInLocalAppData;
end;

// ── Version checking ───────────────────────────────────────

function CompareVersion(v1, v2: string): Integer;
var
  p1, p2: Integer;
  n1, n2: Integer;
  rem1, rem2: string;
begin
  Result := 0;
  p1 := Pos('.', v1);
  p2 := Pos('.', v2);
  if p1 > 0 then n1 := StrToInt(Copy(v1, 1, p1 - 1)) else n1 := StrToInt(v1);
  if p2 > 0 then n2 := StrToInt(Copy(v2, 1, p2 - 1)) else n2 := StrToInt(v2);
  if n1 < n2 then Result := -1
  else if n1 > n2 then Result := 1
  else if (p1 > 0) and (p2 > 0) then
    Result := CompareVersion(Copy(v1, p1 + 1, Length(v1)), Copy(v2, p2 + 1, Length(v2)))
  else if p1 > 0 then Result := 1
  else if p2 > 0 then Result := -1;
end;

function IsFreeCADVersionRecent(fcExe: string): Boolean;
var
  verStr: string;
  major, minor, build: Cardinal;
begin
  Result := False;
  if GetVersionNumbers(fcExe, major, minor, build) then
  begin
    verStr := Format('%d.%d.%d', [major, minor, build]);
    Result := CompareVersion(verStr, '{#FreeCADMinVer}') >= 0;
  end;
end;

// ── Wizard init ────────────────────────────────────────────

procedure InitializeWizard;
var
  fcExe: string;
begin
  FreeCADNeedsDownload := False;
  fcExe := FindFreeCAD;

  if fcExe = '' then
    FreeCADNeedsDownload := True
  else if not IsFreeCADVersionRecent(fcExe) then
    FreeCADNeedsDownload := True;

  DownloadPage := CreateDownloadPage('Downloading FreeCAD', 'Please wait while FreeCAD is downloaded...', @OnDownloadProgress);
end;

procedure OnDownloadProgress(const Url, FileName: string; const Progress, ProgressMax: Int64);
var
  Percent: Integer;
begin
  if ProgressMax > 0 then
    Percent := Round(Progress / ProgressMax * 100)
  else
    Percent := 0;
  DownloadPage.SetProgress(Percent);
end;

// ── FreeCAD download ───────────────────────────────────────

function DownloadFreeCAD: Boolean;
begin
  DownloadPage.Clear;
  DownloadPage.Add('{#FreeCADDownloadUrl}', '{#FreeCADDownloadFile}', '');
  DownloadPage.Show;

  try
    DownloadPage.Download;
    Result := True;
  except
    Result := False;
    SuppressibleMsgBox('Failed to download FreeCAD. Please check your internet connection and try again.',
      mbError, MB_OK, IDOK);
  end;

  DownloadPage.Hide;
end;

function ExtractFreeCAD: Boolean;
var
  SevenZipPath: string;
  ArchivePath: string;
  ExtractDir: string;
  ResultCode: Integer;
begin
  Result := False;
  ArchivePath := ExpandConstant('{tmp}\{#FreeCADDownloadFile}');
  ExtractDir := ExpandConstant('{app}\Runtime\FreeCAD');

  SevenZipPath := '7z.exe';
  if not FileExists(SevenZipPath) then
    SevenZipPath := ExpandConstant('{sys}\7z.exe');
  if not FileExists(SevenZipPath) then
    SevenZipPath := ExpandConstant('{pf}\7-Zip\7z.exe');

  if FileExists(SevenZipPath) then
  begin
    if Exec(SevenZipPath, Format('x "{0}" -o"{1}" -y', [ArchivePath, ExtractDir]),
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    begin
      Result := True;
    end;
  end
  else
  begin
    if Exec(ExpandConstant('{cmd}'), Format('/c powershell -Command "Expand-Archive -Path ''{0}'' -DestinationPath ''{1}'' -Force"', [ArchivePath, ExtractDir]),
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      Result := True;
    end;
  end;

  var NestedDir := ExtractDir + '\{#FreeCADDownloadFile}';
  StringChangeEx(NestedDir, '.7z', '', True);
  if DirExists(NestedDir) then
  begin
    Exec(ExpandConstant('{cmd}'), Format('/c move /y "{0}\*" "{1}"', [NestedDir, ExtractDir]),
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{cmd}'), Format('/c rmdir "{0}"', [NestedDir]),
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

// ── Pre-install hook: download FreeCAD if needed ───────────

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if FreeCADNeedsDownload then
  begin
    if not DownloadFreeCAD then
      Result := 'Failed to download FreeCAD. Please check your internet connection.';
  end;

  if not DirExists(ExpandConstant('{app}\Runtime\AICompanion')) then
    CreateDir(ExpandConstant('{app}\Runtime\AICompanion'));
end;

// ── Post-install: extract FreeCAD if downloaded ────────────

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if FileExists(ExpandConstant('{tmp}\{#FreeCADDownloadFile}')) then
    begin
      ExtractFreeCAD;
    end;
  end;
end;

// ── Uninstall: ask about user data ─────────────────────────

function InitializeUninstall: Boolean;
begin
  Result := SuppressibleMsgBox(
    'Remove all UCAD Assistant data including settings, cache, and downloaded FreeCAD?'#13#10#13#10 +
    'Choose YES to remove everything.'#13#10 +
    'Choose NO to keep settings for future installations.',
    mbConfirmation, MB_YESNO, IDNO) = IDYES;
end;
