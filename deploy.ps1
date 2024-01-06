param(
    [Parameter(Mandatory)][string]$sshPassword
)

function ssh {
    param($command)
    &"c:\program files\putty\plink.exe" -ssh -batch admin@ventilation.domotica.local -pw $sshPassword $command
}

$target = "\\ventilation.domotica.local\root\opt\ventilation\"

#ssh "sudo systemctl stop ventilation.service"

Remove-Item "$target*" -Recurse -Force -Exclude @( "config.json" )

$exclude = @('.*','__*', "deploy.ps1", "workspace.code-workspace", "config.json")
Copy-Item ./* $target -exclude $exclude

ssh "sudo chmod 777 /opt/ventilation/VentilationService.py"
#ssh "sudo systemctl start ventilation.service"
