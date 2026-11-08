; Установщик CodeClass (Inno Setup 6). Собирается скриптом build_exe.ps1.
; Ставится без прав администратора в профиль пользователя.
; Данные (база, настройки) лежат в %APPDATA%\CodeClass и при удалении программы сохраняются.

#define AppVersion "1.0.0"

[Setup]
AppId={{5B8E3C2A-6F1D-4C7B-9E0A-C0DEC1A55001}
AppName=CodeClass
AppVersion={#AppVersion}
AppPublisher=CodeClass
DefaultDirName={localappdata}\Programs\CodeClass
DefaultGroupName=CodeClass
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=CodeClass-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\CodeClass.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\CodeClass\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CodeClass"; Filename: "{app}\CodeClass.exe"
Name: "{group}\Удалить CodeClass"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CodeClass"; Filename: "{app}\CodeClass.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CodeClass.exe"; Description: "Запустить CodeClass"; Flags: nowait postinstall skipifsilent
