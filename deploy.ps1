param(
    [Parameter(Mandatory)][string]$sshPassword
)

function ssh {
    param($command)
    &"c:\program files\putty\plink.exe" -ssh -batch admin@ventilation.domotica.local -pw $sshPassword $command
}

$target = "\\ventilation.domotica.local\root\opt\ventilation\"

ssh "sudo systemctl stop ventilation.service"

rm "$target*" -Recurse -Force

$exclude = @('.*','__*', "deploy.ps1", "workspace.code-workspace")
Copy-Item ./* $target -exclude $exclude

ssh "sudo chmod 777 /opt/ventilation/VentilationService.py"
ssh "sudo systemctl start ventilation.service"
