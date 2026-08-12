; UCAD Assistant Installer — Inno Setup
; Build: iscc setup.iss
;
; What this installer does:
;   1. Detects an existing FreeCAD installation (registry, Program Files, LocalAppData).
;   2. Installs the UCAD Assistant Mod directly into FreeCAD's user Mod directory
;      (e.g. %APPDATA%\FreeCAD\v1-1\Mod\UCAD) so the workbench appears when FreeCAD
;      is opened normally — no launcher required.
;   3. If FreeCAD is NOT installed, offers to download + extract a portable FreeCAD
;      into {app}\Runtime\FreeCAD and installs the Mod into its Mod directory.
;   4. Optionally installs the UCAD Launcher (convenience: manage config, API keys,
;      and launch FreeCAD with the workbench active).
;
; The Mod is installed via Inno's native [Files] mechanism with a {code:} DestDir,
; which reliably handles the thousands of vendored dependency files.

#define MyAppName "UCAD Assistant"
#define MyAppVersion "1.1.1"
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
Name: "plugin"; Description: "UCAD Mod for FreeCAD (required)"; Types: full custom; Flags: fixed
Name: "launcher"; Description: "UCAD Launcher (optional — manage API keys & launch)"; Types: full custom
Name: "shortcut_desktop"; Description: "Desktop shortcut"; Types: full custom
Name: "shortcut_startmenu"; Description: "Start Menu folder"; Types: full custom
Name: "freecad_download"; Description: "Download FreeCAD (if not installed)"; Types: full

[Files]
; Mod — installed directly into FreeCAD's detected Mod dir via {code:} DestDir.
Source: "..\build\mod_stage\*"; DestDir: "{code:GetFreeCADModDest}\UCAD"; Flags: recursesubdirs createallsubdirs; Components: plugin
; Vendored deps (dot-prefixed, so add explicitly to guarantee inclusion)
Source: "..\build\mod_stage\.python-deps\*"; DestDir: "{code:GetFreeCADModDest}\UCAD\.python-deps"; Flags: recursesubdirs createallsubdirs; Components: plugin
; Launcher
Source: "..\dist\UCAD Launcher\*"; DestDir: "{app}\Launcher"; Flags: recursesubdirs createallsubdirs; Components: launcher
; Config defaults
Source: "..\installer\default_config.json"; DestDir: "{app}\Config"; Flags: onlyifdoesntexist

[Icons]
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\Launcher\{#MyAppExeName}"; WorkingDir: "{app}"; Components: shortcut_desktop AND launcher
Name: "{group}\{#MyAppName}"; Filename: "{app}\Launcher\{#MyAppExeName}"; WorkingDir: "{app}"; Components: shortcut_startmenu AND launcher
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Components: shortcut_startmenu

[Run]
; Create runtime data directory structure (launcher scratch)
Filename: "{cmd}"; Parameters: "/c mkdir ""{app}\RuntimeData"" 2>nul & mkdir ""{app}\Logs"" 2>nul & mkdir ""{app}\Cache"" 2>nul & mkdir ""{app}\Secrets"" 2>nul"; Flags: runhidden
; Launch UCAD Launcher after install (if selected)
Filename: "{app}\Launcher\{#MyAppExeName}"; Description: "Launch UCAD Assistant"; Flags: postinstall nowait skipifsilent; Components: launcher

[UninstallRun]
; Clean up user data (optional, asked during uninstall)
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{app}\RuntimeData"" 2>nul"; Flags: runhidden; RunOnceId: CleanRuntimeData
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{app}\Logs"" 2>nul"; Flags: runhidden; RunOnceId: CleanLogs

[Code]
// ── FreeCAD Detection ──────────────────────────────────────
var
  FreeCADPage: TInputOptionWizardPage;
  DownloadPage: TDownloadWizardPage;
  FreeCADExe: string;
  FreeCADModDir: string;

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
  Pattern: string;
  Pf: string;
begin
  Result := '';
  // Use 64-bit Program Files explicitly (avoids 32-bit setup redirection).
  Pf := ExpandConstant('{pf64}');
  if Pf = '' then
    Pf := ExpandConstant('{pf}');

  // Explicit known versions first (most reliable)
  if FileExists(Pf + '\FreeCAD 1.1\bin\FreeCAD.exe') then
  begin
    Result := Pf + '\FreeCAD 1.1\bin\FreeCAD.exe';
    Exit;
  end;
  if FileExists(Pf + '\FreeCAD 1.0\bin\FreeCAD.exe') then
  begin
    Result := Pf + '\FreeCAD 1.0\bin\FreeCAD.exe';
    Exit;
  end;
  // Generic wildcard fallback
  Pattern := Pf + '\FreeCAD*\bin\FreeCAD.exe';
  if FindFirst(Pattern, FindRec) then
  begin
    Result := Pf + '\' + FindRec.Name + '\bin\FreeCAD.exe';
    FindClose(FindRec);
  end;
end;

function FindFreeCADInLocalAppData: string;
var
  FindRec: TFindRec;
  Lap: string;
begin
  Result := '';
  Lap := ExpandConstant('{localappdata}\Programs');
  if FindFirst(Lap + '\FreeCAD*\bin\FreeCAD.exe', FindRec) then
  begin
    Result := Lap + '\' + FindRec.Name + '\bin\FreeCAD.exe';
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

// ── FreeCAD user Mod directory ─────────────────────────────
// FreeCAD >= 1.0 stores user addons under %APPDATA%\FreeCAD\v<major>-<minor>\Mod.
function GetFreeCADModDir(fcExe: string): string;
var
  AppData: string;
  VerDir: string;
  VerStr: string;
  Major, Minor: string;
  DotPos: Integer;
begin
  Result := '';
  AppData := ExpandConstant('{userappdata}\FreeCAD');
  // Derive version from install folder name, e.g. "FreeCAD 1.1" -> "v1-1".
  VerDir := ExtractFileName(ExtractFileDir(ExtractFileDir(fcExe)));
  DotPos := Pos('.', VerDir);
  if DotPos > 0 then
  begin
    VerStr := Copy(VerDir, DotPos - 1, 5); // e.g. "1.1"
    Major := Copy(VerStr, 1, Pos('.', VerStr) - 1);
    Minor := Copy(VerStr, Pos('.', VerStr) + 1, 1);
    VerDir := 'v' + Major + '-' + Minor;
    Result := AppData + '\' + VerDir + '\Mod';
    Exit;
  end;
  // Fallback: unversioned Mod dir (legacy FreeCAD < 1.0)
  Result := AppData + '\Mod';
end;

// {code:} target — the FreeCAD Mod dir (without the \UCAD suffix).
// Falls back to {app}\Runtime if no FreeCAD was found (launcher can still use it).
function GetFreeCADModDest(Param: string): string;
begin
  if FreeCADModDir <> '' then
    Result := FreeCADModDir
  else
    Result := ExpandConstant('{app}\Runtime');
end;

// ── Download / extract FreeCAD (portable) ──────────────────

procedure CurDownloadProgress(const Url, FileName: string; const Progress, ProgressMax: Int64);
begin
  DownloadPage.SetProgress(Progress, ProgressMax);
end;

procedure InitializeWizard;
var
  fcExe: string;
begin
  fcExe := FindFreeCAD;
  if fcExe <> '' then
  begin
    FreeCADExe := fcExe;
    FreeCADModDir := GetFreeCADModDir(fcExe);
  end;

  if not WizardSilent then
  begin
    if fcExe = '' then
    begin
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

  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

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
    // 7-Zip not found — try Windows tar (supports .7z on Win11+)
    if Exec(ExpandConstant('{sys}\tar.exe'),
        Format(' -xf "{0}" -C "{1}"', [ArchivePath, ExtractDir]),
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    begin
      Result := True;
    end
    else
    begin
      SuppressibleMsgBox(
        'FreeCAD archive could not be extracted.'#13#10#13#10 +
        'Install 7-Zip (https://7-zip.org) and extract manually:'#13#10 +
        ArchivePath,
        mbInformation, MB_OK, IDOK);
    end;
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

// ── Pre-install hook: detect/download/extract FreeCAD so that FreeCADModDir
//    is resolved BEFORE the [Files] section runs (files install after this). ──

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';

  // Detect FreeCAD now (may have been installed between wizard init and install)
  if FreeCADExe = '' then
    FreeCADExe := FindFreeCAD;

  if FreeCADExe = '' then
  begin
    // FreeCAD not installed yet
    if WizardSilent then
    begin
      Log('Silent mode: FreeCAD not found. Skipping download (user will configure later).');
    end
    else if (FreeCADPage <> nil) and (FreeCADPage.SelectedValueIndex = 0) then
    begin
      if not DownloadFreeCAD then
      begin
        SuppressibleMsgBox(
          'Failed to download FreeCAD. Please check your internet connection.'#13#10#13#10 +
          'You can download it manually from https://www.freecad.org/download'#13#10 +
          'and install the Mod via UCAD Launcher afterwards.',
          mbInformation, MB_OK, IDOK);
      end
      else if ExtractFreeCAD then
      begin
        // Portable FreeCAD extracted into {app}\Runtime\FreeCAD — use its Mod dir
        FreeCADExe := ExpandConstant('{app}\Runtime\FreeCAD\bin\FreeCAD.exe');
        FreeCADModDir := ExpandConstant('{app}\Runtime\FreeCAD\Mod');
        Log('UCAD: portable FreeCAD extracted; Mod dir=' + FreeCADModDir);
      end;
    end;
  end;

  // If a FreeCAD is known now, resolve the Mod dir
  if (FreeCADModDir = '') and (FreeCADExe <> '') then
  begin
    FreeCADModDir := GetFreeCADModDir(FreeCADExe);
    Log('UCAD: FreeCAD=' + FreeCADExe);
    Log('UCAD: Mod dir=' + FreeCADModDir);
  end;

  // Ensure runtime directory exists for the Mod staging
  if not DirExists(ExpandConstant('{app}\Runtime\AICompanion')) then
    CreateDir(ExpandConstant('{app}\Runtime\AICompanion'));
end;

// ── Post-install: no-op (Mod already installed by [Files]) ──

procedure CurStepChanged(CurStep: TSetupStep);
begin
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
