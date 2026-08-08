; UCAD Assistant Installer — Inno Setup
; Build: iscc setup.iss

#define MyAppName "UCAD Assistant"
#define MyAppVersion "1.1.0"
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
; Plugin (Mod) — referenced by -M flag, not copied into FreeCAD
; Ships plain open-source source (LGPL). If a staged mod exists at build\mod_stage, use it.
Source: "..\build\mod_stage\*"; DestDir: "{app}\Runtime\AICompanion"; Flags: recursesubdirs createallsubdirs; Components: plugin
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
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{app}\RuntimeData"" 2>nul"; Flags: runhidden; RunOnceId: CleanRuntimeData
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{app}\Logs"" 2>nul"; Flags: runhidden; RunOnceId: CleanLogs

[Code]
// ── FreeCAD Detection ──────────────────────────────────────
var
  FreeCADPage: TInputOptionWizardPage;
  DownloadPage: TDownloadWizardPage;

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

// ── Download progress ──────────────────────────────────────

procedure CurDownloadProgress(const Url, FileName: string; const Progress, ProgressMax: Int64);
begin
  DownloadPage.SetProgress(Progress, ProgressMax);
end;

// ── Wizard Page: FreeCAD Detection ─────────────────────────

procedure InitializeWizard;
var
  fcExe: string;
begin
  // In silent mode, skip FreeCAD detection UI entirely
  if not WizardSilent then
  begin
    fcExe := FindFreeCAD;
    if fcExe = '' then
    begin
      // FreeCAD not found — offer to download
      FreeCADPage := CreateInputOptionPage(
        wpSelectComponents,
        'FreeCAD Detection',
        'FreeCAD was not found on your system.',
        'UCAD Assistant requires FreeCAD 1.0 or later.'#13#10 +
        'You can download it automatically during installation.',
        True, False
      );
      FreeCADPage.Add('Download FreeCAD 1.1.1 (~400 MB) — RECOMMENDED');
      FreeCADPage.Add('I will install FreeCAD manually');
      FreeCADPage.SelectedValueIndex := 0;
    end;
  end;

  // Download page
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

// ── FreeCAD download ───────────────────────────────────────

function DownloadFreeCAD: Boolean;
var
  Url: string;
begin
  Url := 'https://github.com/FreeCAD/FreeCAD/releases/download/1.1.1/FreeCAD_1.1.1-Windows-x86_64-py311.7z';

  DownloadPage.Clear;
  DownloadPage.Add(Url, 'FreeCAD_1.1.1-Windows-x86_64-py311.7z', '');
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
  NestedDir: string;
  ResultCode: Integer;
begin
  Result := False;
  ArchivePath := ExpandConstant('{tmp}\FreeCAD_1.1.1-Windows-x86_64-py311.7z');
  ExtractDir := ExpandConstant('{app}\Runtime\FreeCAD');
  CreateDir(ExtractDir);

  // Find 7-Zip: check common locations + PATH
  SevenZipPath := '7z.exe';
  if not FileExists(SevenZipPath) then
    SevenZipPath := ExpandConstant('{sys}\7z.exe');
  if not FileExists(SevenZipPath) then
    SevenZipPath := ExpandConstant('{pf}\7-Zip\7z.exe');
  if not FileExists(SevenZipPath) then
    SevenZipPath := 'C:\Program Files\7-Zip\7z.exe';
  if not FileExists(SevenZipPath) then
    SevenZipPath := 'C:\Program Files (x86)\7-Zip\7z.exe';
  if not FileExists(SevenZipPath) then
    SevenZipPath := ExpandConstant('{localappdata}\Programs\7-Zip\7z.exe');

  if FileExists(SevenZipPath) then
  begin
    if Exec(SevenZipPath, Format('x "{0}" -o"{1}" -y', [ArchivePath, ExtractDir]),
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    begin
      Result := True;
    end
    else
    begin
      SuppressibleMsgBox(
        'Failed to extract FreeCAD archive.'#13#10 +
        Format('7-Zip exit code: %d', [ResultCode]) + #13#10 + #13#10 +
        'You can extract it manually from:'#13#10 + ArchivePath,
        mbError, MB_OK, IDOK);
    end;
  end
  else
  begin
    // 7-Zip not installed — leave archive in place for manual extraction
    SuppressibleMsgBox(
      '7-Zip not found. FreeCAD archive was downloaded but could not be extracted.'#13#10#13#10 +
      'Install 7-Zip (https://7-zip.org) and extract manually:'#13#10 +
      ArchivePath,
      mbInformation, MB_OK, IDOK);
  end;

  // Handle nested directory in .7z
  NestedDir := ExtractDir + '\FreeCAD_1.1.1_Windows-x86_64-py311';
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
  Result := '';

  if FindFreeCAD = '' then
  begin
    // In silent mode, skip FreeCAD download — launcher handles it on first launch
    if WizardSilent then
    begin
      Log('Silent mode: FreeCAD not found. Skipping download (launcher will prompt user).');
    end
    else if FreeCADPage.SelectedValueIndex = 0 then
    begin
      if not DownloadFreeCAD then
      begin
        // Non-fatal: warn but let install continue
        SuppressibleMsgBox(
          'Failed to download FreeCAD. Please check your internet connection.'#13#10#13#10 +
          'You can download it manually from https://www.freecad.org/download'#13#10 +
          'and configure FreeCAD path in UCAD Launcher settings after installation.',
          mbInformation, MB_OK, IDOK);
      end;
    end;
  end;

  // Ensure runtime directory exists for the Mod path
  if not DirExists(ExpandConstant('{app}\Runtime\AICompanion')) then
    CreateDir(ExpandConstant('{app}\Runtime\AICompanion'));
end;

// ── Post-install: extract FreeCAD if downloaded ────────────

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // If FreeCAD was downloaded, extract it
    if FileExists(ExpandConstant('{tmp}\FreeCAD_1.1.1-Windows-x86_64-py311.7z')) then
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
