
$target = "\\ventilation.domotica.local\root\opt\ventilation\"

ssh admin@ventilation.domotica.local 'sudo systemctl stop ventilation.service'

rm "$target*" -Recurse -Force

$exclude = @('.*','__*', "deploy.ps1", "workspace.code-workspace")
Copy-Item ./* $target -exclude $exclude

ssh admin@ventilation.domotica.local 'sudo chmod 777 /opt/ventilation/VentilationService.py'
ssh admin@ventilation.domotica.local 'sudo systemctl start ventilation.service'
